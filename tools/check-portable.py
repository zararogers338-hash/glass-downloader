"""Windows release smoke test using the distributed EXE as the only installed app file."""
import asyncio
import hashlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

from aiohttp import ClientSession, web
import psutil


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def run(binary, work, default_launch=False):
    exe = work / binary.name
    shutil.copyfile(binary, exe)
    port, debug_port = (17846 if default_launch else free_port()), free_port()
    if default_launch:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1",port))
    origin = f"http://127.0.0.1:{port}"
    data, dest = work/"state", work/"downloads"
    env = {**os.environ, "PATH": str(Path(os.environ["SystemRoot"])/"System32"),
           "WEBVIEW2_USER_DATA_FOLDER": str(work/"webview-profile"),
           "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": f"--remote-debugging-port={debug_port} --remote-debugging-address=127.0.0.1"}
    for k in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(k, None)
    cmd = [str(exe), "--port", str(port), "--data", str(data), "--output", str(dest)]
    if default_launch:
        env["GLASS_DATA_DIR"]=str(data)
        env["GLASS_DOWNLOAD_DIR"]=str(dest)
        cmd=[str(exe)]
    version = subprocess.check_output([str(exe),"--version"],cwd=work,env=env,timeout=45).decode().strip()
    yt = subprocess.check_output([str(exe),"--yt-worker","--version"],cwd=work,env=env,timeout=45).decode().strip()
    assert version and yt
    payload = bytes(range(256))*16384

    async def file(req):
        return web.Response(body=payload, content_type="application/octet-stream")

    fixture = web.Application()
    fixture.router.add_get("/fixture.bin", file)
    runner = web.AppRunner(fixture)
    await runner.setup()
    file_port = free_port()
    await web.TCPSite(runner,"127.0.0.1",file_port).start()
    proc = subprocess.Popen(cmd,cwd=work,env=env)
    try:
        async with ClientSession(trust_env=False) as client:
            async with asyncio.timeout(65):
                while True:
                    if proc.poll() is not None: raise RuntimeError("Desktop process exited early")
                    try:
                        async with client.get(f"http://127.0.0.1:{debug_port}/json/list") as reply:
                            pages = await reply.json()
                        page = next((p for p in pages if p.get("type")=="page" and p.get("url","").startswith(origin+"/")),None)
                        if page:break
                    except (OSError, RuntimeError, ValueError):
                        pass
                    await asyncio.sleep(.2)
            token = (data/"api-token").read_text("ascii").strip()
            headers = {"Authorization":"Bearer "+token}
            async with client.ws_connect(page["webSocketDebuggerUrl"]) as cdp:
                i=0
                async def evaluate(js):
                    nonlocal i
                    i+=1
                    await cdp.send_json({"id":i,"method":"Runtime.evaluate","params":{"expression":js,"returnByValue":True}})
                    async with asyncio.timeout(8):
                        while True:
                            msg=await cdp.receive_json()
                            if msg.get("id")==i:
                                return msg.get("result",{}).get("result",{}).get("value")
                async with asyncio.timeout(30):
                    while not await evaluate("document.querySelector('h1')?.textContent === '通用下载' && document.querySelector('footer')?.innerText.includes('已连接')"):
                        await asyncio.sleep(.2)
                assert await evaluate("document.querySelectorAll('.sidechannels button').length")==13
                async with client.get(origin+"/api/v1/config",headers=headers) as response:
                    config=await response.json()
                scenes=set()
                for channel in config["channels"]:
                    async with client.get(origin+"/scenes/"+channel["id"]+"/wallpaper") as response:
                        assert response.status==200 and (await response.read())[8:12]==b"WEBP"
                    scenes.add(channel["scene"])
                assert len(scenes)==12
                # Submit through the visible UI, using a real DOM input event.
                await evaluate(f"""(()=>{{const input=document.querySelector('#resource-entry input');input.value='http://127.0.0.1:{file_port}/fixture.bin';input.dispatchEvent(new Event('input',{{bubbles:true}}));document.querySelector('#resource-entry').requestSubmit();}})()""")
                async with asyncio.timeout(30):
                    while True:
                        async with client.get(origin+"/api/v1/jobs",headers=headers) as reply:
                            jobs=await reply.json()
                        if jobs and jobs[0]["state"]=="failed":raise RuntimeError(jobs[0]["error"])
                        if jobs and jobs[0]["state"]=="completed":break
                        await asyncio.sleep(.15)
                assert Path(jobs[0]["path"]).read_bytes()==payload
                assert jobs[0]["sha256"]==hashlib.sha256(payload).hexdigest()
                again=await asyncio.create_subprocess_exec(*cmd,cwd=work,env=env)
                assert await asyncio.wait_for(again.wait(),30)==0
            # Close ONLY the test Tauri window, identified by the test process tree.
            import ctypes
            from ctypes import wintypes
            user32=ctypes.windll.user32
            user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
            user32.IsWindowVisible.argtypes=[wintypes.HWND]
            user32.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
            user32.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
            pids={p.pid for p in psutil.Process(proc.pid).children(recursive=True) if p.name().lower()=="glass-downloader.exe"}
            closed=[]
            @ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
            def close(hwnd,_):
                pid=wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
                title=ctypes.create_unicode_buffer(160)
                user32.GetWindowTextW(hwnd,title,len(title))
                if pid.value in pids and user32.IsWindowVisible(hwnd) and title.value=="泊岸 · 下载工作台":
                    user32.PostMessageW(hwnd,0x0010,0,0)
                    closed.append(hwnd)
                return True
            user32.EnumWindows(close,0)
            assert closed, "Native window missing"
            assert await asyncio.to_thread(proc.wait,45)==0
            print("PASS",version,"native window + UI download + SHA-256 + 12 scenes + second launch + clean exit; yt-dlp",yt)
    finally:
        if proc.poll() is None:
            subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            proc.wait(timeout=15)
        await runner.cleanup()


if __name__=="__main__":
    binary=Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="glass-exe-",ignore_cleanup_errors=True) as tmp:
        asyncio.run(run(binary,Path(tmp),"--default" in sys.argv[2:]))

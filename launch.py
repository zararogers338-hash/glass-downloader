"""Start the local service and, optionally, its desktop window."""
import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from aiohttp import web
from core.catalog import ROOT
from core.server import create_app

def show_window(url):
    native=ROOT/"src-tauri/target/release/glass-downloader.exe"
    if native.is_file() and os.name=="nt":
        subprocess.Popen([str(native)],env={**os.environ,"GLASS_START_URL":url});return
    if os.name=="nt":
        for base in ("PROGRAMFILES(X86)","PROGRAMFILES","LOCALAPPDATA"):
            edge=Path(os.environ.get(base,"."))/"Microsoft/Edge/Application/msedge.exe"
            if edge.is_file():
                subprocess.Popen([str(edge),"--app="+url]);return
    webbrowser.open(url)

async def run(args):
    import socket
    args.data.mkdir(parents=True,exist_ok=True)
    # Reserve port before opening task storage; a second launcher reuses the first.
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    if os.name=="nt":sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    try:sock.bind(("127.0.0.1",args.port))
    except OSError:
        sock.close()
        if not args.headless:
            from urllib.request import build_opener, ProxyHandler
            import hmac, secrets
            token=(args.data/"api-token").read_text("ascii").strip()
            url=f"http://127.0.0.1:{args.port}"
            import json
            challenge=secrets.token_hex(32)
            with build_opener(ProxyHandler({})).open(url+"/instance?challenge="+challenge,timeout=2) as response:
                proof=json.load(response).get("proof","")
            if hmac.compare_digest(proof,hmac.digest(token.encode(),("instance:"+challenge).encode(),"sha256").hex()):
                show_window(url+"/#token="+token);return
        raise
    sock.listen(128);sock.setblocking(False)
    port=sock.getsockname()[1]
    app,token=create_app(args.data,args.output,port)
    runner=web.AppRunner(app,access_log=None);await runner.setup()
    try:
        await web.SockSite(runner,sock).start()
        url=f"http://127.0.0.1:{port}"
        print(f"Glass Downloader listening at {url}",flush=True)
        if not args.headless:show_window(url+"/#token="+token)
        await asyncio.Event().wait()
    finally:await runner.cleanup()

if __name__=="__main__":
    default=Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME") or Path.home()/".local/state")/"GlassDownloader"
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--data",type=Path,default=default)
    p.add_argument("--output",type=Path,default=Path.home()/"Downloads"/"GlassDownloader");p.add_argument("--port",type=int,default=17846)
    p.add_argument("--headless",action="store_true");a=p.parse_args();a.data=a.data.resolve();a.output=a.output.resolve()
    if not (ROOT/"dist/index.html").is_file():sys.exit("Build the UI first: npm install && npm run build")
    try:asyncio.run(run(a))
    except KeyboardInterrupt:pass


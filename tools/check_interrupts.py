"""Test interruption against controlled origins, never the user's queue or output."""
import asyncio
import hashlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from aiohttp import web, ClientSession
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.catalog import components
from core.queue import Queue
from core.server import create_app
from aiohttp.test_utils import unused_port

DATA=b"glass-"*1024*1024
SHA=hashlib.sha256(DATA).hexdigest()


async def until(fn):
    async with asyncio.timeout(12):
        while not fn():
            await asyncio.sleep(.02)


async def run(root):
    reads=[]
    async def content(req):
        requested=req.headers.get("Range")
        ranged=requested and req.path!="/stream"
        first,last=map(int,requested[6:].split("-")) if ranged else (0,len(DATA)-1)
        reads.append((req.path,first,last))
        headers={"Content-Length":str(last-first+1),"Content-Type":"application/octet-stream","ETag":'"demo"'}
        if ranged:headers["Content-Range"]=f"bytes {first}-{last}/{len(DATA)}"
        rep=web.StreamResponse(status=206 if ranged else 200,headers=headers)
        await rep.prepare(req)
        try:
            for i in range(first,last+1,65536):
                await rep.write(DATA[i:min(last+1,i+65536)])
                if last-first>1:await asyncio.sleep(.013)
        except (ConnectionError,asyncio.CancelledError):
            pass
        return rep

    origin=web.Application();origin.router.add_get("/{name}",content)
    runner=web.AppRunner(origin);await runner.setup()
    port=unused_port();await web.TCPSite(runner,"127.0.0.1",port).start()
    url=f"http://127.0.0.1:{port}"
    try:
        for engine in ["http","curl","httpx"]:
            if not components()[engine]:raise RuntimeError("Missing test core: "+engine)
            home=root/engine;out=home/"out";q=Queue(home,out)
            try:
                q.configure({"connections":2,"parallel_tasks":1})
                job=q.add(dict(url=url+"/file",channel="general",prefer_engine=engine,expected_sha256=SHA))
                await until(lambda:job["done"]>150000)
                queued=q.add(dict(url=url+"/queued",channel="general",prefer_engine=engine))
                await q.action(queued["id"],"cancel");assert queued["state"]=="cancelled"
                await asyncio.gather(q.action(job["id"],"pause"),q.action(job["id"],"pause"))
                paused=job["done"];assert 0<paused<len(DATA) and job["state"]=="paused"
                await asyncio.sleep(.06);assert job["done"]==paused
                await q.close();q=Queue(home,out)
                job=q.jobs[job["id"]];assert job["state"]=="paused"
                pos=len(reads);await q.action(job["id"],"resume")
                await asyncio.wait_for(q.work[job["id"]],15)
                assert job["state"]=="completed" and job["sha256"]==SHA,(engine,job["error"])
                assert any(start>0 and start%(len(DATA)//2) for _,start,end in reads[pos:])
                target=q.add(dict(url=url+"/stream",channel="general",prefer_engine=engine))
                await until(lambda:target["done"]>65536)
                folder=q.directory(target);sentinel=folder/"keep.txt";sentinel.write_text("keep")
                await q.action(target["id"],"cancel");await q.action(target["id"],"cancel")
                assert target["state"]=="cancelled" and not (folder/".parts").exists() and sentinel.exists()
                try:await q.action(target["id"],"resume")
                except ValueError:pass
                else:raise AssertionError("cancelled job resumed")
                print("PASS",engine,"queued cancel, active pause, restart, validated resume, active cancel",flush=True)
            finally:await q.close()
        home=root/"restore";out=home/"out";q=Queue(home,out)
        try:
            q.configure({"resume_on_start":True,"connections":1})
            manual=q.add({"url":url+"/manual"});await q.action(manual["id"],"pause")
            hot=q.add({"url":url+"/hot"})
            await until(lambda:hot["done"]>65536)
            await q.close();q=Queue(home,out);q.restore()
            assert q.jobs[manual["id"]]["state"]=="paused" and q.jobs[hot["id"]]["state"]=="queued"
            await q.action(hot["id"],"cancel")
            print("PASS auto-restore excludes manually paused jobs")
            if components()["aria2"]:
                a=q.add({"url":url+"/aria","prefer_engine":"aria2","expected_sha256":SHA})
                await asyncio.wait_for(q.work[a["id"]],20)
                assert a["state"]=="completed" and Path(a["path"]).read_bytes()==DATA,a["error"]
                part=q.add({"url":url+"/aborted-external","prefer_engine":"aria2"})
                await until(lambda:any(p=="/aborted-external" for p,_,_ in reads))
                await q.action(part["id"],"cancel")
                assert part["state"]=="cancelled" and not (q.directory(part)/".parts").exists()
                print("PASS aria2 local transfer, checksum, external process cancel")
        finally:await q.close()
        # A stopped resolver must never enqueue its result.
        service_port=unused_port();address=f"http://127.0.0.1:{service_port}"
        app,token=create_app(root/"resolve-db",root/"resolve-out",service_port)
        srv=web.AppRunner(app);await srv.setup();await web.TCPSite(srv,"127.0.0.1",service_port).start()
        started=asyncio.Event()
        async def slow(*args):
            started.set()
            await asyncio.sleep(30)
            return {"url":url+"/late"},None
        try:
            async with ClientSession(headers={"Authorization":"Bearer "+token}) as client:
                with patch("core.server.resolve_input",slow):
                    op="a"*32
                    add=asyncio.ensure_future(client.post(address+"/api/v1/jobs",json={"url":"org/model","submission_id":op}))
                    await asyncio.wait_for(started.wait(),3)
                    stop=await client.post(address+"/api/v1/submissions/"+op+"/stop");assert stop.status==200
                    assert (await asyncio.wait_for(add,2)).status==409
                    assert not await (await client.get(address+"/api/v1/jobs")).json()
                    print("PASS interrupt resolution before enqueue")
        finally:await srv.cleanup()
    finally:await runner.cleanup()

if __name__=="__main__":
    with tempfile.TemporaryDirectory() as tmp:asyncio.run(run(Path(tmp)))


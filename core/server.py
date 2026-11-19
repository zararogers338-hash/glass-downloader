import asyncio
import hmac
import os
import re
import secrets
import time
from pathlib import Path
import psutil
from aiohttp import web, WSMsgType
from .catalog import ROOT, CHANNELS, components, make_plan
from .queue import Queue
from .resolver import ChooseRepo, resolve_input
from .bili_media import inspect_formats

def create_app(home, output, port):
    home.mkdir(exist_ok=True,parents=True)
    token_path=home/"api-token"
    if not token_path.exists():
        fd=os.open(token_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w",encoding="ascii") as f:f.write(secrets.token_urlsafe(32))
    token=token_path.read_text("ascii").strip()
    if len(token)<24:raise RuntimeError("本地 API 凭据无效")
    authority=f"127.0.0.1:{port}"
    allowed={authority,f"localhost:{port}"}
    def authorized(value):
        return hmac.compare_digest(value.encode(),("Bearer "+token).encode())

    @web.middleware
    async def boundary(req,handler):
        if req.host not in allowed:return web.json_response({"error":"Host 不匹配"},status=403)
        if req.headers.get("Origin") not in {None,*("http://"+a for a in allowed)}:
            return web.json_response({"error":"Origin 不匹配"},status=403)
        if req.path.startswith("/api/") and not authorized(req.headers.get("Authorization","")):
            return web.json_response({"error":"需要本机访问令牌"},status=401)
        try:return await handler(req)
        except ChooseRepo as e:return web.json_response({"error":str(e),"choices":e.choices},status=409)
        except (ValueError,TypeError) as e:return web.json_response({"error":str(e)},status=400)
        except KeyError:return web.json_response({"error":"记录不存在"},status=404)

    app=web.Application(middlewares=[boundary],client_max_size=32768)
    queue=Queue(home,output)
    sockets=set()
    host_stats={"cpu":None,"memory":None,"disk_write":None,"disk_free":None,"gpu":None}
    async def tick(app):
        previous=psutil.disk_io_counters();when=time.monotonic();psutil.cpu_percent()
        while True:
            await asyncio.sleep(.75)
            queue.sample()
            cur=psutil.disk_io_counters();now=time.monotonic()
            host_stats.update(cpu=psutil.cpu_percent(),memory=psutil.virtual_memory().percent,
                disk_free=psutil.disk_usage(str(output)).free,
                disk_write=max(0,int((cur.write_bytes-previous.write_bytes)/(now-when))) if previous and cur else None)
            previous=cur;when=now
            if sockets:
                import json
                payload=json.dumps(snapshot(),separators=(",",":"))
                async def deliver(ws):
                    try:await asyncio.wait_for(ws.send_str(payload),1.5)
                    except (TimeoutError,ConnectionError,RuntimeError): sockets.discard(ws)
                await asyncio.gather(*(deliver(ws) for ws in list(sockets)))
    def snapshot():
        return {"jobs":list(reversed(queue.jobs.values())),"system":host_stats,
                "settings":queue.settings,"output":queue.settings["download_dir"],"components":inventory,"version":"0.1.0"}
    inventory=components()
    resolving={}
    submissions={}
    def expire_submissions():
        now=time.monotonic()
        for key,(expires,_) in list(submissions.items()):
            if now>=expires:submissions.pop(key,None)
    async def life(app):
        queue.restore()
        task=asyncio.create_task(tick(app));yield
        task.cancel();await asyncio.gather(task,return_exceptions=True);await queue.close()
    app.cleanup_ctx.append(life)
    async def shutdown(app):
        for task in resolving.values():task.cancel()
        await asyncio.gather(*list(resolving.values()),return_exceptions=True)
        await asyncio.gather(*(ws.close(code=1001) for ws in list(sockets)),return_exceptions=True)
    app.on_shutdown.append(shutdown)
    async def index(req):return web.FileResponse(ROOT/"dist/index.html",headers={"Cache-Control":"no-store",
        "Content-Security-Policy":"default-src 'self'; img-src 'self' blob: data:; media-src blob: 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' ws://127.0.0.1:"+str(port)+" ws://localhost:"+str(port)+"; frame-ancestors 'none'; object-src 'none'; base-uri 'none'",
        "Referrer-Policy":"no-referrer","X-Content-Type-Options":"nosniff"})
    async def scene(req):
        ch=CHANNELS[req.match_info["channel"]];size=req.match_info["size"]
        if size not in {"preview","wallpaper"}:raise web.HTTPNotFound()
        file=ROOT/"scene-packs"/ch["scene"]/(size+".webp")
        if not file.is_file():raise web.HTTPNotFound()
        return web.FileResponse(file)
    async def identify(req):
        challenge=req.query.get("challenge","")
        if not re.fullmatch("[a-f0-9]{64}",challenge):
            raise ValueError("Invalid instance challenge")
        proof=hmac.digest(token.encode(),"instance:".encode()+challenge.encode(),"sha256").hex()
        return web.json_response({"proof":proof},headers={"Cache-Control":"no-store"})
    async def config(req):return web.json_response({"channels":list(CHANNELS.values()),"token_file":str(token_path)})
    async def state(req):return web.json_response(snapshot())
    async def jobs(req):return web.json_response(list(reversed(queue.jobs.values())))
    async def job(req):return web.json_response(queue.jobs[req.match_info["id"]])
    async def payload(req):
        if req.content_type!="application/json":raise ValueError("需要 application/json")
        body=await req.json()
        if not isinstance(body,dict):raise ValueError("需要 JSON 对象")
        return body
    async def plan(req):
        normalized,spec=await resolve_input(await payload(req),queue.settings)
        result=make_plan(normalized,queue.settings)
        if spec:result.update(repo=spec["repo"],revision=spec["revision"],file_count=len(spec["files"]),total=spec["total"])
        return web.json_response(result)
    media_slots=asyncio.Semaphore(3)
    async def formats(req):
        data=await payload(req)
        async with media_slots:
            return web.json_response(await inspect_formats(str(data.get("url","")),queue.settings))
    async def add(req):
        data=await payload(req)
        key=data.get("idempotency_key")
        if key:
            match=next((j for j in queue.jobs.values() if j.get("key")==key),None)
            if match:return web.json_response(match)
        op=data.get("submission_id")
        expire_submissions()
        if op is not None:
            if not isinstance(op,str) or not re.fullmatch("[a-f0-9-]{32,36}",op):raise ValueError("无效的提交编号")
            if op in resolving or op in submissions:raise ValueError("这次提交已处理或已停止")
        task=asyncio.create_task(resolve_input(data,queue.settings))
        if op:resolving[op]=task
        try:
            normalized,spec=await task
            if op in submissions:raise ValueError("解析已中断")
            normalized["original_input"]=str(data.get("url") or data.get("input") or "")
            job=queue.add(normalized,spec)
            if op:submissions[op]=(time.monotonic()+120,job["id"] if job.get("submission_id")==op else None)
            return web.json_response(job,status=201)
        except asyncio.CancelledError:
            if op in submissions:return web.json_response({"error":"解析已中断"},status=409)
            raise
        finally:
            if op:resolving.pop(op,None)
    async def stop_submission(req):
        op=req.match_info["op"];expire_submissions()
        _,jid=submissions.get(op,(0,None))
        submissions[op]=(time.monotonic()+120,None)
        if task:=resolving.get(op):task.cancel()
        if jid and jid in queue.jobs and queue.jobs[jid]["state"] not in {"completed","cancelled"}:
            await queue.action(jid,"cancel")
        return web.json_response({"ok":True})
    async def action(req):
        await queue.action(req.match_info["id"],req.match_info["action"]);return web.json_response({"ok":True})
    async def settings(req):
        queue.configure(await payload(req));return web.json_response(queue.settings)
    async def reveal(req):
        import subprocess,sys
        j=queue.jobs[req.match_info["id"]]
        folder=queue.directory(j)
        if not folder.is_dir():raise ValueError("任务目录尚未创建")
        if os.name=="nt":os.startfile(str(folder))
        else:subprocess.Popen(["open" if sys.platform=="darwin" else "xdg-open",str(folder)])
        return web.json_response({"ok":True})
    async def rescan(req):
        inventory.update(components());return web.json_response(inventory)
    async def events(req):
        ws=web.WebSocketResponse(heartbeat=25,max_msg_size=4096)
        await ws.prepare(req)
        try:
            msg=await asyncio.wait_for(ws.receive(),4)
            if msg.type!=WSMsgType.TEXT or not authorized("Bearer "+msg.data):
                await ws.close(code=1008);return ws
            sockets.add(ws);await ws.send_json(snapshot())
            async for _ in ws: pass
        except TimeoutError:await ws.close(code=1008)
        finally:sockets.discard(ws)
        return ws
    app.add_routes([web.get("/",index),web.get("/instance",identify),web.static("/assets",ROOT/"dist/assets"),
        web.get("/scenes/{channel}/{size}",scene),web.get("/events",events),
        web.get("/api/v1/config",config),web.get("/api/v1/state",state),web.post("/api/v1/plan",plan),web.post("/api/v1/bilibili/formats",formats),
        web.get("/api/v1/jobs",jobs),web.get("/api/v1/jobs/{id}",job),web.post("/api/v1/jobs",add),
        web.post("/api/v1/jobs/{id}/{action:pause|resume|cancel|remove|delete}",action),web.post("/api/v1/jobs/{id}/folder",reveal),web.patch("/api/v1/settings",settings),
        web.post("/api/v1/submissions/{op:[a-f0-9-]+}/stop",stop_submission),
        web.post("/api/v1/components/rescan",rescan)])
    return app,token


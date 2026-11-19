import asyncio
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .catalog import ROOT, CHANNELS, ENGINE_INFO, FILE_ENGINES, ROUTES, engines_for, executable, make_plan
from .bili_media import media_args, normalize_media, yt_command
from .processes import owned_process
from .transfer import retry_http, finalize, safe_filename

SPEEDS=json.loads((ROOT/"speed-profiles.json").read_text("utf8"))

def capped(*limits):
    return min((n for n in limits if n),default=0)


class Queue:
    def __init__(self, home, output):
        self.home=home
        home.mkdir(parents=True, exist_ok=True)
        self.output=output
        self.output.mkdir(parents=True, exist_ok=True)
        self.db=sqlite3.connect(home/"tasks.sqlite3")
        self.db.executescript("""PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY, data TEXT NOT NULL);""")
        self.jobs={}
        for key,raw in self.db.execute("SELECT id,data FROM jobs ORDER BY rowid"):
            job=json.loads(raw)
            if job["state"] in {"running","verifying","queued"}:
                job.update(state="paused",stopped_reason="shutdown")
            if job["state"]=="pausing":job.update(state="paused",stopped_reason="user")
            if job["state"]=="cancelling":
                self.finish_cancel(job)
            job["speed"]=0
            self.jobs[key]=job
        row=self.db.execute("SELECT data FROM config WHERE id=1").fetchone()
        self.settings={"connections":4,"parallel_tasks":3,"retries":2,"resume_on_start":False,"download_dir":str(output),"mihomo_port":7890,"tor_port":9050,"upload_kib":128,"download_kib":0,
                       "profiles":{},"default_route":"direct","speed_profile":"high", **(json.loads(row[0]) if row else {})}
        self.work={}
        self.occupied=0
        self.wakeup=asyncio.Event()
        self.samples={}
        self.children={}
        self.locks={}
        self.last_checkpoint=0

    def save(self,job):
        self.db.execute("INSERT OR REPLACE INTO jobs VALUES(?,?)",(job["id"],json.dumps(job,ensure_ascii=False)))
        self.db.commit()

    def configure(self, data):
        updated=self.settings.copy()
        for k,v in data.items():
            if k=="profiles":
                if not isinstance(v,dict) or not set(v).issubset(CHANNELS):raise ValueError("未知频道")
                for cid,profile in v.items():
                    allowed=engines_for(cid)
                    if not isinstance(profile,dict) or set(profile)-{"engine","route","source"} or profile.get("engine") not in {*allowed,None}:
                        raise ValueError("核心与频道不兼容")
                    if profile.get("route") not in {*ROUTES,None} or (cid=="magnet" and profile.get("route") not in {"direct",None}) or (cid=="tor" and profile.get("route") not in {"tor",None}):
                        raise ValueError("频道不支持这条线路")
                    eng=profile.get("engine") or CHANNELS[cid]["engine"]
                    if profile.get("route") and profile["route"] not in ENGINE_INFO[eng]["routes"]:
                        raise ValueError(f"{eng} 不支持所选线路")
                    if profile.get("source") not in ({"original","hf-mirror",None} if cid=="huggingface" else {"original",None}):
                        raise ValueError("未知下载源")
            elif k=="download_dir":
                if not isinstance(v,str) or not Path(v).is_absolute():raise ValueError("请填写绝对下载目录")
                path=Path(v).resolve()
                if path==Path(path.anchor):raise ValueError("请选择磁盘上的子目录")
                v=str(path)
            elif k in {"parallel_tasks","retries"}:
                low,high=(1,16) if k=="parallel_tasks" else (0,5)
                if type(v) is not int or not low<=v<=high:raise ValueError("并发或重试次数超出范围")
            elif k=="speed_profile":
                if v not in SPEEDS:raise ValueError("未知速度档位")
            elif k=="default_route":
                if v not in {"direct","mihomo"}:raise ValueError("默认出口不合法")
            elif k=="resume_on_start":
                if type(v) is not bool:raise ValueError("恢复队列选项需要布尔值")
            elif k in {"upload_kib","download_kib"}:
                if type(v) is not int or not 0<=v<=1048576:raise ValueError("带宽限制超出范围")
            elif k not in updated or type(v) is not int or not 1<=v<=(8 if k=="connections" else 65535):
                raise ValueError("设置值不合法")
            updated[k]=v
        try:Path(updated["download_dir"]).mkdir(parents=True,exist_ok=True)
        except OSError as e:raise ValueError("无法创建下载目录") from e
        self.db.execute("INSERT OR REPLACE INTO config VALUES(1,?)",(json.dumps(updated),))
        self.db.commit(); self.settings=updated;self.wakeup.set()

    @asynccontextmanager
    async def slot(self):
        while self.occupied>=self.settings["parallel_tasks"]:
            self.wakeup.clear()
            await self.wakeup.wait()
        self.occupied+=1
        try:yield
        finally:
            self.occupied-=1;self.wakeup.set()

    def directory(self,j):
        return Path(j.get("output_base",self.output))/j["id"]

    def transfer_settings(self,j):
        net=j.get("network",self.settings).copy()
        task_cap=net.get("download_kib",0)
        net["live_download_kib"]=lambda:capped(task_cap,SPEEDS[self.settings["speed_profile"]]["down"])
        net["download_kib"]=net["live_download_kib"]()
        return net

    def discard_cache(self,job):
        # Only this app's per-job staging tree is disposable. Legacy delegates
        # wrote directly to the output directory, so leave those files alone.
        cache=self.directory(job)/".parts"
        if cache.exists():shutil.rmtree(cache)

    def finish_cancel(self,job):
        try:self.discard_cache(job)
        except OSError:job.update(state="cancelled",speed=0,error="传输已停止，部分暂存文件被占用")
        else:job.update(state="cancelled",speed=0,error="")
        job.update(segments=[],stopped_reason="user")

    def restore(self):
        for job in self.jobs.values():
            if self.settings["resume_on_start"] and job["state"]=="paused" and job.get("stopped_reason")=="shutdown":
                self.start(job)

    def add(self,data,snapshot=None):
        key=data.get("idempotency_key")
        if key and (not isinstance(key,str) or len(key)>150): raise ValueError("幂等键过长")
        if key:
            for old in self.jobs.values():
                if old.get("key")==key:return old
        plan=make_plan(data,self.settings)
        if not plan.pop("ready"): raise ValueError("所选引擎尚未安装，请查看组件页面")
        expect=str(data.get("expected_sha256","")).lower()
        if expect and (not re.fullmatch("[a-f0-9]{64}",expect) or plan["engine"] in {"yt-dlp","BBDown"} or plan["url"].startswith("magnet:")):
            raise ValueError("仅普通文件任务支持预期 SHA-256（64 位十六进制）")
        if expect and snapshot:raise ValueError("整仓使用逐文件哈希校验")
        media=normalize_media(data.get("media"),plan["engine"]) if plan["channel"]=="bilibili" else None
        if data.get("media") and media is None:raise ValueError("该频道不支持媒体选项")
        for old in self.jobs.values():
            if (old["state"] in {"queued","running","verifying"} and
                all(old.get(k)==plan.get(k) for k in ("url","channel","route","engine")) and
                (media is None or old.get("media",{"mode":"video","quality":"auto"})==media) and
                old.get("expected_sha256","")==expect and old.get("revision")==((snapshot or {}).get("revision"))):
                return old
        k=secrets.token_hex(8)
        job=dict(**plan,id=k,key=key,name=safe_filename(unquote(Path(urlsplit(plan["url"]).path).name) or CHANNELS[plan["channel"]]["name"]),
                 state="queued",done=0,total=None,speed=0,segments=[],created=time.time(),error="",sha256="",expected_sha256=expect,path="")
        job["network"]={field:self.settings[field] for field in ("connections","mihomo_port","tor_port","retries","download_kib")}
        job["output_base"]=self.settings["download_dir"]
        job["submission_id"]=data.get("submission_id")
        job["staged_delegate"]=True
        if media is not None:job["media"]=media
        if snapshot:
            job.update(name=snapshot["repo"],revision=snapshot["revision"],file_count=len(snapshot["files"]),files_done=0,total=snapshot["total"])
            self.db.execute("INSERT INTO snapshots VALUES(?,?)",(k,json.dumps(snapshot)))
        job["input"]=data.get("original_input",job["url"])
        self.jobs[k]=job; self.start(job)
        return job

    def start(self,job):
        job.update(state="queued",error="",speed=0,stopped_reason="")
        self.save(job)
        self.work[job["id"]]=asyncio.create_task(self.run(job))

    async def delegate(self,j,out):
        engine=j["engine"]
        stage=out/".parts"/"engine" if j.get("staged_delegate") else out
        stage.mkdir(parents=True,exist_ok=True);dest=str(stage)
        net=self.transfer_settings(j)
        if engine=="aria2":
            cmd=[executable("aria2c") or "aria2c","--no-conf=true","--enable-rpc=false","--seed-time=0","--follow-torrent=false",
                 "--follow-metalink=false","--auto-file-renaming=false","--continue=true","--dir="+dest]
            if j["url"].startswith("magnet:"):
                cmd.append("--max-upload-limit="+str(capped(j.get("upload_kib",128),SPEEDS[self.settings["speed_profile"]]["up"]))+"K")
            elif j["expected_sha256"]:
                cmd+=["--check-integrity=true","--checksum=sha-256="+j["expected_sha256"]]
            if j["route"]=="mihomo":cmd+=["--all-proxy=http://127.0.0.1:"+str(net["mihomo_port"])]
            if net.get("download_kib"):cmd+=["--max-download-limit="+str(net["download_kib"])+"K"]
        elif engine=="BBDown":
            part=parse_qs(urlsplit(j["url"]).query).get("p",["1"])[0]
            if not part.isdecimal():raise ValueError("分 P 编号无效")
            cmd=[executable("BBDown") or "BBDown",j["url"],"--work-dir",dest,"--select-page",part,
                 "--file-pattern","<bvid>-P<pNumber>","--multi-file-pattern","<bvid>-P<pNumber>",
                 "--force-replace-host","false","--skip-cover","--skip-subtitle"]
            if ffmpeg:=executable("ffmpeg"):cmd+=["--ffmpeg-path",ffmpeg]
            if net.get("download_kib"):
                if not executable("aria2c"):raise ValueError("BBDown 限速需要 aria2c")
                cmd+=["--use-aria2c","--aria2c-path",executable("aria2c"),"--aria2c-args","--max-download-limit="+str(net["download_kib"])+"K"]
        else:
            proxy="http://127.0.0.1:"+str(net["mihomo_port"]) if j["route"]=="mihomo" else ""
            cmd=yt_command()+["--ignore-config","--no-playlist","--windows-filenames","--no-progress","--proxy",proxy,
                 "--retries",str(net.get("retries",2)),"--paths",dest,"-o","%(title).120B [%(id)s].%(ext)s"]
            if ffmpeg:=executable("ffmpeg"):cmd+=["--ffmpeg-location",str(Path(ffmpeg).parent)]
            if j["channel"]=="bilibili":cmd+=["--http-chunk-size","4M"]
            if net.get("download_kib"):cmd+=["--limit-rate",str(net["download_kib"])+"K"]
        if j["channel"]=="bilibili":cmd+=media_args(j.get("media",{"mode":"video","quality":"auto"}),engine)
        if engine!="BBDown":cmd+=["--",j["url"]]
        reason=""
        async with owned_process(cmd,cwd=dest,stderr=asyncio.subprocess.STDOUT,stdout=asyncio.subprocess.PIPE,tree=True,direct=j["route"]=="direct") as proc:
            while data:=await proc.stdout.read(8192):
                detail=data.decode("utf8","replace").lower()
                if found:=re.search(r"(?:http (?:error )?|status=|status code[^\d]{0,10})([45]\d\d)",detail):reason="HTTP "+found[1]
                elif "ffmpeg" in detail and "not found" in detail:reason="缺少 ffmpeg"
                elif "login" in detail or "log in" in detail:reason="资源要求登录"
            code=await proc.wait()
        if code:raise ValueError(f"{engine} 获取资源失败（{reason or code}）。请检查链接、线路或资源访问条件")
        files=[p.relative_to(stage) for p in stage.rglob("*") if p.is_file()]
        if not files:raise ValueError("引擎未生成文件")
        if engine=="BBDown":
            audio=j.get("media",{}).get("mode")=="audio"
            extensions={".m4a",".mp3",".flac",".aac",".opus",".wav",".mka",".ac3",".eac3"} if audio else {".mkv",".flv",".mp4",".mov"}
            if not any(p.suffix.lower() in extensions for p in files):
                raise ValueError("BBDown 未生成所选媒体文件，请检查视频权限及 ffmpeg")
        published=out
        if stage!=out:
            published=out/"files";stage.rename(published)
            stage.parent.rmdir()
        j.update(path=str(published/files[0] if len(files)==1 else published),done=sum((published/p).stat().st_size for p in files))
        if len(files)==1:j["name"]=files[0].name
        j["total"]=j["done"]
        if engine=="aria2" and j.get("expected_sha256"): j["sha256"]=j["expected_sha256"]

    async def fetch_snapshot(self, job, out):
        row=self.db.execute("SELECT data FROM snapshots WHERE id=?",(job["id"],)).fetchone()
        spec=json.loads(row[0])
        cache=out/".parts";cache.mkdir(exist_ok=True)
        staging=cache/"snapshot";staging.mkdir(exist_ok=True)
        destination=out/safe_filename(spec["repo"].replace("/","--"))
        if destination.is_dir() and not any(staging.iterdir()):
            # A completed directory was published before the status commit.
            if all((destination/e["path"]).is_file() for e in spec["files"]):
                job.update(path=str(destination),files_done=len(spec["files"]),
                           done=sum((destination/e["path"]).stat().st_size for e in spec["files"]))
                job["total"]=job["done"];return
        complete=0
        for i,entry in enumerate(spec["files"]):
            dest=staging/entry["path"]
            job.update(files_done=i,current_file=entry["path"],done=complete,segments=[])
            if not dest.is_file():
                dest.parent.mkdir(parents=True,exist_ok=True)
                temp=cache/f"transfer-{i}";temp.mkdir(exist_ok=True)
                prefix=spec["base"]+(entry["revision"]+"/" if "revision" in entry else "")
                child=dict(engine=job["engine"],route=job["route"],url=prefix+quote(entry["path"],safe="/"),done=0,segments=[],
                           expected_sha256=entry["sha256"])
                self.children[job["id"]]=(complete,child)
                try:
                    parts=await retry_http(child,temp,self.transfer_settings(job))
                    if entry["size"] is not None and entry["size"]!=child["done"]:raise ValueError("仓库文件大小不匹配")
                    child["name"]=dest.name
                    await finalize(child,parts,temp,dest.parent)
                    shutil.rmtree(temp,ignore_errors=True)
                finally:
                    job.update(done=complete+child["done"],segments=child["segments"],segment_total=child.get("total"),
                               resumable=child.get("resumable"),protocol=child.get("protocol"))
                    self.children.pop(job["id"],None)
            complete+=dest.stat().st_size
            job.update(files_done=i+1,done=complete)
        staging.rename(destination)
        shutil.rmtree(cache,ignore_errors=True)
        job.update(path=str(destination),total=complete,segments=[],current_file="",segment_total=None)

    async def run(self,j):
        k=j["id"]
        try:
            async with self.slot():
                j["state"]="running";self.save(j)
                out=self.directory(j);out.mkdir(parents=True,exist_ok=True)
                if "revision" in j:await self.fetch_snapshot(j,out)
                elif j["engine"] in FILE_ENGINES:
                    cache=out/".parts";cache.mkdir(exist_ok=True)
                    parts=await retry_http(j,cache,self.transfer_settings(j))
                    j["state"]="verifying"
                    await finalize(j,parts,cache,out)
                    shutil.rmtree(cache,ignore_errors=True)
                else:await self.delegate(j,out)
                j["state"]="completed"
        except asyncio.CancelledError:
            if j["state"] not in {"pausing","cancelling"}:j["state"]="paused"
        except Exception as e:
            j.update(state="failed",error=str(e)[:300] or type(e).__name__)
        finally:
            j["speed"]=0
            self.samples.pop(k,None)
            self.save(j)

    async def action(self,k,action):
        lock=self.locks.setdefault(k,asyncio.Lock())
        async with lock:
            return await self._action(k,action)

    async def _action(self,k,action):
        j=self.jobs[k]
        if action=="delete":
            if j["state"] not in {"completed","cancelled"}:
                await self._action(k,"cancel")
            await self._action(k,"remove")
            return
        if (action,j["state"]) in {("pause","paused"),("cancel","cancelled")}:return
        if action in {"pause","cancel"} and j["state"] in ({"queued","running","verifying"} if action=="pause" else {"queued","running","verifying","paused","failed","cancelling"}):
            j["state"]="pausing" if action=="pause" else "cancelling"
            self.save(j)
            task=self.work.get(k)
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task,return_exceptions=True)
            if action=="cancel":
                self.finish_cancel(j)
            else:j.update(state="paused",speed=0,stopped_reason="user")
            self.save(j)
        elif action=="resume" and j["state"] in {"paused","failed"}: self.start(j)
        elif action=="remove" and j["state"] in {"completed","cancelled","paused","failed"}:
            self.db.execute("DELETE FROM snapshots WHERE id=?",(k,))
            self.db.execute("DELETE FROM jobs WHERE id=?",(k,));self.db.commit()
            self.jobs.pop(k);self.work.pop(k,None);self.locks.pop(k,None)
            shutil.rmtree(self.directory(j)/".parts",ignore_errors=True)
        else:raise ValueError("当前任务状态不支持这个操作")

    def sample(self):
        now=time.monotonic()
        for j in self.jobs.values():
            if j["state"]!="running":continue
            if j["id"] in self.children:
                completed,child=self.children[j["id"]]
                j["done"]=completed+child["done"];j["segments"]=child["segments"];j["segment_total"]=child.get("total")
            if j["engine"] not in FILE_ENGINES:
                try:j["done"]=sum(p.stat().st_size for p in self.directory(j).rglob("*") if p.is_file() and p.suffix!=".aria2") if j["engine"]=="yt-dlp" else j["done"]
                except OSError:pass
            key=j["id"]; counts=[s["done"] for s in j["segments"]]
            old=self.samples.get(key,(now,j["done"],counts))
            delta=max(.001,now-old[0])
            j["speed"]=max(0,int((j["done"]-old[1])/delta))
            for s,prior in zip(j["segments"],old[2]):
                s["speed"]=max(0,int((s["done"]-prior)/delta))
            self.samples[key]=(now,j["done"],counts)
            if now-self.last_checkpoint>=3:self.save(j)
        if now-self.last_checkpoint>=3:self.last_checkpoint=now

    async def close(self):
        for k,t in self.work.items():
            if not t.done() and not t.cancelling():
                self.jobs[k]["stopped_reason"]="shutdown"
                t.cancel()
        await asyncio.gather(*self.work.values(),return_exceptions=True)
        for j in self.jobs.values():
            if j["state"]=="queued":j["state"]="paused";self.save(j)
        self.db.close()


"""HTTP adapter. Resume only validated byte ranges of the same representation."""
import asyncio
import hashlib
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit
import aiohttp
from contextlib import AsyncExitStack, asynccontextmanager, nullcontext
from yarl import URL
from .streams import file_transport, transport


def safe_filename(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:150]
    if not name or name.split(".")[0].upper() in {"CON","PRN","AUX","NUL",*(f"COM{i}" for i in range(10)),*(f"LPT{i}" for i in range(10))}:
        name = "download-" + (name or "file")
    return name


class StatusError(ValueError):
    def __init__(self, status):
        self.status=status
        super().__init__(f"服务器响应 HTTP {status}")


async def fetch_http(job, cache, settings):
    url=job["url"]
    async with file_transport(job.get("engine","http"),job["route"],settings) as get, AsyncExitStack() as probe_stack:
        @asynccontextmanager
        async def request(extra):
            target=URL(url)
            for _ in range(11):
                if target.scheme not in {"http","https"} or not target.host or target.user is not None or (job["route"]!="tor" and target.host.rstrip(".").endswith(".onion")):
                    raise ValueError("线路不允许此重定向")
                async with get(target,extra) as rep:
                    if rep.status not in {301,302,303,307,308}:
                        yield rep
                        return
                    location=rep.headers.get("Location")
                    if not location:raise ValueError("重定向缺少地址")
                    target=target.join(URL(location))
            raise ValueError("重定向次数过多")

        probe=await probe_stack.enter_async_context(request({"Range":"bytes=0-0"}))
        if probe.status in {400,405,416}:
            await probe_stack.aclose()
            probe=await probe_stack.enter_async_context(request({}))
        if probe.status not in {200,206}:raise StatusError(probe.status)
        if probe.headers.get("Content-Type","").split(";")[0].lower()=="text/html":
            raise ValueError("该地址返回网页，请选择文件直链或视频频道")
        from aiohttp.multipart import parse_content_disposition,content_disposition_filename
        _,params=parse_content_disposition(probe.headers.get("Content-Disposition","").rstrip("; "))
        job["name"]=safe_filename(content_disposition_filename(params) or unquote(Path(probe.url.path).name) or "download.bin")
        job["protocol"]=probe.protocol
        match=re.fullmatch(r"bytes 0-0/(\d+)",probe.headers.get("Content-Range",""))
        tag=probe.headers.get("ETag","")
        ranged=bool(probe.status==206 and match and len(tag)>2 and tag.startswith('"') and tag.endswith('"'))
        raw_length=probe.headers.get("Content-Length")
        size=int(match[1]) if probe.status==206 and match else int(raw_length) if probe.status==200 and raw_length else None
        reusable=probe if probe.status==200 else None
        if not reusable:await probe_stack.aclose()
        job["resumable"]=ranged
        job["total"] = size
        count = min(settings["connections"], max(1, (size or 0)//(2*1024*1024))) if ranged else 1
        bounds = [(i*size//count, (i+1)*size//count-1) for i in range(count)] if ranged else [(0,(size-1) if size is not None else None)]
        identity = [url, tag, size, bounds]
        import json
        mark = cache / "identity.json"
        same = bool(ranged and mark.exists() and mark.read_text("utf8") == json.dumps(identity))
        if not same:
            for part in cache.glob("part-*"):
                part.unlink()
        mark.write_text(json.dumps(identity),"utf8")
        parts = [cache / f"part-{i}" for i in range(count)]
        chunks = []
        for part,(a,b) in zip(parts,bounds):
            done = part.stat().st_size if part.exists() else 0
            if b is not None and done>b-a+1:
                part.unlink(); done=0
            chunks.append(dict(start=a,end=b,done=done,state="waiting"))
        job["segments"] = chunks
        job["done"] = sum(c["done"] for c in chunks)
        live_cap=settings.get("live_download_kib",lambda:settings.get("download_kib",0))
        next_write=time.monotonic()
        async def segment(i):
            nonlocal next_write
            c = chunks[i]
            length = c["end"]-c["start"]+1 if c["end"] is not None else None
            if ranged and c["done"] == length:
                c["state"]="done"; return
            start=c["start"]+c["done"]
            hdr={"Range":f"bytes={start}-{c['end']}","If-Range":tag} if ranged else {}
            c["state"]="active"
            async with (nullcontext(reusable) if reusable is not None else request(hdr)) as resp:
                if resp.status>=400:raise StatusError(resp.status)
                if ranged and (resp.status!=206 or resp.headers.get("Content-Range")!=f"bytes {start}-{c['end']}/{size}" or resp.headers.get("ETag",tag)!=tag):
                    raise ValueError("资源或分段范围已改变，请重试")
                if not ranged and resp.status!=200:
                    raise ValueError("服务器未返回完整文件")
                if not ranged and resp.headers.get("Content-Length") is not None:
                    length=int(resp.headers["Content-Length"]);job["total"]=length;c["end"]=length-1
                with parts[i].open("ab" if ranged else "wb") as f:
                    async for data in resp.chunks:
                        if length is not None and c["done"]+len(data)>length: raise ValueError("响应超过预期范围")
                        limit=live_cap()*1024
                        if limit:
                            now=time.monotonic()
                            next_write=max(now,next_write)+len(data)/limit
                            await asyncio.sleep(next_write-now)
                        f.write(data); c["done"]+=len(data); job["done"]+=len(data)
                if length is not None and c["done"]!=length: raise ValueError("传输提前结束")
            c["state"]="done"
        workers=[asyncio.create_task(segment(i)) for i in range(count)]
        try:
            await asyncio.gather(*workers)
        finally:
            for work in workers: work.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
    return parts


async def retry_http(job, cache, settings):
    for attempt in range(settings.get("retries",2)+1):
        try:return await fetch_http(job,cache,settings)
        except (aiohttp.ClientConnectionError,aiohttp.ClientPayloadError,TimeoutError,StatusError) as exc:
            if isinstance(exc,StatusError) and exc.status not in {408,429,500,502,503,504}:raise
            if attempt>=settings.get("retries",2):raise
            job["retry"]=attempt+1
            await asyncio.sleep(2**attempt)


async def finalize(job, parts, cache, out):
    temp = cache / "assembled.tmp"
    digest=hashlib.sha256()
    with temp.open("wb") as target:
        for part in parts:
            with part.open("rb") as f:
                while data:=f.read(512*1024):
                    target.write(data); digest.update(data)
                    await asyncio.sleep(0)
    job["sha256"]=digest.hexdigest()
    if job.get("expected_sha256") and job["sha256"]!=job["expected_sha256"]:
        temp.unlink()
        for part in parts:part.unlink(missing_ok=True)
        raise ValueError("SHA-256 与预期值不符，请重试")
    out.mkdir(exist_ok=True,parents=True)
    dest=out/job["name"]
    temp.replace(dest)
    for part in parts: part.unlink(missing_ok=True)
    job["path"]=str(dest)


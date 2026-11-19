"""Read public Bilibili stream choices using the same engine and outlet as the job."""
import asyncio
import json
import re
import shutil
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit
from .catalog import executable, make_plan
from .resolver import bilibili_input
from .processes import owned_process


def yt_command():
    binary=shutil.which("yt-dlp")
    return [binary] if binary else [sys.executable,"-m","yt_dlp"]


def normalize_media(value, engine):
    value={} if value is None else value
    if not isinstance(value,dict) or set(value)-{"mode","quality"}:
        raise ValueError("无效的 B 站媒体选项")
    mode=value.get("mode","video")
    if mode not in {"audio","video"}:raise ValueError("请选择视频或仅音频")
    quality="auto" if mode=="audio" else value.get("quality","auto")
    pattern=r"(?:v|av):[A-Za-z0-9_-]{1,64}" if engine=="yt-dlp" else r"bb:[\w \-·]{1,48}"
    if not isinstance(quality,str) or (quality!="auto" and not re.fullmatch(pattern,quality)):
        raise ValueError("画质与当前核心不兼容，请重新读取画质")
    return {"mode":mode,"quality":quality}


def media_args(media, engine):
    mode,quality=media["mode"],media["quality"]
    if mode=="audio":
        return ["--audio-only"] if engine=="BBDown" else ["-f","bestaudio/best","--extract-audio"]
    if quality=="auto":return []
    kind,choice=quality.split(":",1)
    if engine=="BBDown":return ["--dfn-priority",choice]
    return ["-f",choice+"+bestaudio" if kind=="v" else choice]


def yt_choices(formats):
    options={}
    for f in formats:
        fid=str(f.get("format_id",""))
        if f.get("has_drm") or f.get("vcodec") in {None,"none"} or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",fid):continue
        quality=("v:" if f.get("acodec") in {None,"none"} else "av:")+fid
        w,h=f.get("width"),f.get("height")
        label=f"{min(w,h)}p · {w} × {h}" if w and h else f.get("format_note") or fid
        fps=f.get("fps")
        if fps:label+=f" · {round(fps)} fps"
        codec=str(f["vcodec"]).split(".")[0].upper()
        options[quality]=dict(id=quality,label=label+" · "+codec,rank=(w or 0)*(h or 0))
    return sorted(options.values(),key=lambda o:-o["rank"])


async def inspect_formats(text,settings):
    url=bilibili_input(text.strip())
    if not url or len(text)>8192:raise ValueError("请先输入 BV 号或 B 站分享链接")
    plan=make_plan({"url":url,"channel":"bilibili"},settings)
    if not plan["ready"]:raise ValueError("当前频道核心尚未安装")
    engine=plan["engine"]
    if engine=="yt-dlp":
        proxy=f"http://127.0.0.1:{settings['mihomo_port']}" if plan["route"]=="mihomo" else ""
        cmd=yt_command()+["--ignore-config","--proxy",proxy,"--no-playlist","--skip-download","--no-warnings","--dump-single-json","--",url]
    else:
        part=parse_qs(urlsplit(url).query).get("p",["1"])[0]
        cmd=[executable("BBDown"),url,"--only-show-info","--select-page",part]
    with tempfile.TemporaryDirectory() as tmp:
        try:
            async with asyncio.timeout(35):
                async with owned_process(cmd,cwd=tmp,stdout=asyncio.subprocess.PIPE,tree=True,direct=plan["route"]=="direct") as proc:
                    raw=bytearray()
                    while chunk:=await proc.stdout.read(65536):
                        raw.extend(chunk)
                        if len(raw)>12*1024*1024:raise ValueError("媒体信息过大")
                    if await proc.wait():raise ValueError("核心未能解析此视频，请检查分 P、线路或访问权限")
        except TimeoutError as e:raise ValueError("读取画质超时，请重试") from e
    if engine=="yt-dlp":
        info=json.loads(raw)
        options=yt_choices(info.get("formats",[]))
    else:
        seen=set();options=[]
        try:listing=raw.decode("utf8")
        except UnicodeDecodeError:listing=raw.decode("gb18030","replace")
        for label,dims in re.findall(r"(?m)^\s*\d+\.\s*\[([^\]]+)\]\s*\[(\d+x\d+)\]",listing):
            if label in seen or not re.fullmatch(r"[\w \-·]{1,48}",label):continue
            seen.add(label);options.append({"id":"bb:"+label,"label":label+" · "+dims})
    if not options:raise ValueError("未取得可选画质，可保留自动画质或更换核心")
    return {"engine":engine,"options":options}


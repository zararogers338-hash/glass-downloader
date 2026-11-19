import json
import importlib.util
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
CHANNELS = {row["id"]: row for row in json.loads((ROOT / "channels.json").read_text("utf8"))}
ROUTES = {"direct", "mihomo", "tor"}
ENGINE_INFO={row["id"]:row for row in json.loads((ROOT/"engines.json").read_text("utf8"))}
FILE_ENGINES={"http","httpx","curl"}


def engines_for(channel):
    kind=channel if channel in {"tor","magnet","video","bilibili"} else "files"
    return {name for name,spec in ENGINE_INFO.items() if kind in spec["kinds"]}


def executable(name):
    folder=(Path(os.environ["LOCALAPPDATA"])/"GlassDownloader"/"components"
            if getattr(sys,"frozen",False) and os.name=="nt" else ROOT/".components")
    private=folder/(name+(".exe" if os.name=="nt" else ""))
    return str(private) if private.is_file() else shutil.which(name)


def components():
    result={name:bool(executable(exe)) for name,exe in
            {"aria2":"aria2c","curl":"curl","ffmpeg":"ffmpeg","mihomo":"mihomo","BBDown":"BBDown"}.items()}
    return result | {"http":True,"httpx":bool(importlib.util.find_spec("httpx") and importlib.util.find_spec("h2")),
                     "yt-dlp":bool(shutil.which("yt-dlp") or importlib.util.find_spec("yt_dlp"))}


def make_plan(data, settings=None):
    settings = settings or {}
    url = str(data.get("url", "")).strip()
    if not url or len(url) > 8192 or any(ord(c) < 32 for c in url):
        raise ValueError("请输入有效的下载链接")
    p = urlsplit(url)
    magnet = p.scheme == "magnet"
    host = (p.hostname or "").lower()
    if not magnet and (p.scheme not in {"http", "https"} or not host or p.username or p.password):
        raise ValueError("支持 HTTP、HTTPS 和 magnet 链接")
    if magnet and "xt=urn:bt" not in p.query.lower():
        raise ValueError("磁力链接缺少种子标识")
    onion = host.rstrip(".").endswith(".onion")
    inferred = "magnet" if magnet else "tor" if onion else "general"
    for suffix, key in {"huggingface.co":"huggingface", "github.com":"github", "arxiv.org":"arxiv",
                        "bilibili.com":"bilibili", "b23.tv":"bilibili", "modelscope.cn":"modelscope"}.items():
        if host == suffix or host.endswith("." + suffix):
            inferred = key
    channel = data.get("channel") or inferred
    if channel not in CHANNELS:
        raise ValueError("未知频道")
    profile = settings.get("profiles", {}).get(channel, {})
    default_engine = profile.get("engine") or CHANNELS[channel]["engine"]
    engine = data.get("prefer_engine") or ("aria2" if magnet else default_engine)
    default_route = "tor" if channel == "tor" or onion else "direct" if magnet else settings.get("default_route", "direct")
    route = data.get("prefer_proxy") or profile.get("route") or default_route
    if engine not in engines_for("magnet" if magnet else channel) or route not in ROUTES:
        raise ValueError("不支持的引擎或线路")
    if route not in ENGINE_INFO[engine]["routes"]:
        raise ValueError(f"{engine} 不支持当前线路，请在频道设置中选择兼容核心")
    if (onion or channel == "tor") and route != "tor":
        raise ValueError("洋葱地址必须选择 Tor 线路")
    if magnet and (route != "direct" or engine != "aria2"):
        raise ValueError("磁力任务当前需要 aria2 和直连线路")
    if engine in FILE_ENGINES|{"aria2"} and host in {"huggingface.co", "github.com", "www.modelscope.cn", "modelscope.cn"} and "/blob/" in p.path:
        if host == "github.com":
            url = urlunsplit(("https","raw.githubusercontent.com",p.path.replace("/blob/","/",1),p.query,""))
        else:
            url = urlunsplit((p.scheme, p.netloc, p.path.replace("/blob/","/resolve/",1),p.query,""))
    if host in {"arxiv.org","www.arxiv.org"} and p.path.startswith("/abs/"):
        url = "https://arxiv.org/pdf/" + p.path[5:]
    source = "original"
    if channel == "huggingface" and host == "huggingface.co" and profile.get("source") == "hf-mirror":
        resolved = urlsplit(url)
        if resolved.query or resolved.port or resolved.scheme != "https" or "/resolve/" not in resolved.path:
            raise ValueError("镜像策略仅接受无查询参数的公开 HTTPS 文件地址")
        url = urlunsplit(("https", "hf-mirror.com", resolved.path, "", ""))
        source = "hf-mirror"
    return dict(url=url,channel=channel,engine=engine,route=route,source=source,
                upload_kib=settings.get("upload_kib",128), ready=components().get(engine,False))


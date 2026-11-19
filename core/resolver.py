"""Resolve human-entered names before file transfers. No system proxy inheritance."""
import hashlib
import json
import re
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import aiohttp
from .catalog import FILE_ENGINES, make_plan
from .transfer import transport

SLUG = r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}"
REPO = re.compile(rf"{SLUG}(?:/{SLUG})?")
BV = re.compile(r"BV[A-Za-z0-9]{10}(?![A-Za-z0-9])")
SHARE = re.compile(r"https?://[^\s<>“”【】]+", re.I)

class ChooseRepo(ValueError):
    def __init__(self, choices):
        super().__init__("有多个可能的仓库，请选择作者和名称")
        self.choices=choices

async def metadata(url, route, settings, not_found_ok=False, *, as_text=False):
    session,proxy=transport(route,settings)
    try:
        async with session:
            async with session.get(url,proxy=proxy,headers={"User-Agent":"GlassDownloader/0.1","Accept":"application/json"}) as res:
                if res.status==404 and not_found_ok:return None
                if res.status in {403,429}: raise ValueError("目录服务拒绝请求或已限流。可以直接填完整仓库名或文件直链")
                if res.status==401:raise ValueError("资源可能需要登录，当前仅支持公开仓库")
                if res.status>=400:raise ValueError(f"目录服务返回 HTTP {res.status}")
                content=bytearray()
                async for chunk in res.content.iter_chunked(65536):
                    content.extend(chunk)
                    if len(content)>24*1024*1024:raise ValueError("仓库清单过大")
                return content.decode("utf-8","replace") if as_text else json.loads(content)
    except (aiohttp.ClientError,TimeoutError,OSError) as e:
        raise ValueError(f"目录请求失败，请检查所选线路（{type(e).__name__}）") from e

def choose(candidates, query):
    values=list(dict.fromkeys(v for v in candidates if REPO.fullmatch(v)))
    exact=[v for v in values if v.rsplit("/",1)[-1].lower()==query.lower()]
    if len(exact)==1:return exact[0]
    matches=exact or values
    if not matches:raise ValueError("没有找到公开仓库，请输入 作者/名称")
    if len(matches)==1:return matches[0]
    raise ChooseRepo(matches[:12])

def bilibili_input(text):
    for match in SHARE.finditer(text):
        link=match.group().rstrip('，。！？、）)！.,;')
        address=urlsplit(link)
        host=(address.hostname or "").lower()
        if host=="b23.tv":
            return "https://b23.tv"+address.path
        if host=="bilibili.com" or host.endswith(".bilibili.com"):
            video=BV.search(address.path)
            if video:
                part=parse_qs(address.query).get("p",[""])[0]
                suffix="?p="+part if part.isdigit() else ""
                return "https://www.bilibili.com/video/"+video.group()+"/"+suffix
    if not text.startswith(("http://","https://")):
        video=BV.search(text)
        if video:return "https://www.bilibili.com/video/"+video.group()+"/"
    return None

def file_entry(row):
    path=row["rfilename"]
    bits=path.split("/")
    for piece in bits:
        if (piece in {"",".",".."} or piece.endswith((" ",".")) or re.search(r'[<>:"\\|?*\x00-\x1f]',piece)
            or piece.split(".")[0].upper() in {"NUL","CON","PRN","AUX",*(f"COM{i}" for i in range(1,10)),*(f"LPT{i}" for i in range(1,10))}):
            raise ValueError("仓库包含无法安全保存的文件路径")
    lfs=row.get("lfs") or {}
    return dict(path=path,size=row.get("size"),sha256=lfs.get("sha256",""))

def check_tree(files):
    if not files:raise ValueError("仓库中没有文件")
    paths={f["path"].casefold() for f in files}
    if len(paths)!=len(files) or any("/".join(p.split("/")[:i]) in paths for p in paths for i in range(1,p.count("/")+1)):
        raise ValueError("仓库包含本机文件系统无法区分的路径")

async def resolve_input(data,settings):
    text=str(data.get("url") or data.get("input") or "").strip()
    if not text or len(text)>8192:raise ValueError("请输入资源名称或链接")
    cid=data.get("channel")
    bv=bilibili_input(text) if cid in {None,"general","video","bilibili"} else None
    if bv:return {**data,"channel":"bilibili","url":bv},None
    if cid=="arxiv" and re.fullmatch(r"(?:arXiv:)?\d{4}\.\d{4,5}(?:v\d+)?",text,re.I):
        return {**data,"url":"https://arxiv.org/pdf/"+text.split(":")[-1]},None
    if cid=="java" and re.fullmatch(r"(?:jdk\s*)?\d{1,2}", text, re.I):
        major=re.search(r"\d+",text).group()
        address=f"https://api.adoptium.net/v3/binary/latest/{major}/ga/windows/x64/jdk/hotspot/normal/eclipse"
        return {**data,"url":address},None
    if cid=="python" and re.fullmatch(r"(?:python\s*)?3\.\d+\.\d+",text,re.I):
        version=re.search(r"3\.\d+\.\d+",text).group()
        return {**data,"url":f"https://www.python.org/ftp/python/{version}/python-{version}-amd64.exe"},None
    if cid=="cpp" and (v:=re.fullmatch(r"llvm\s+(\d+\.\d+\.\d+)",text,re.I)):
        return {**data,"url":f"https://github.com/llvm/llvm-project/releases/download/llvmorg-{v[1]}/LLVM-{v[1]}-win64.exe"},None
    if cid=="python" and re.fullmatch(r"[a-zA-Z0-9][\w.-]*(?:==[\w.+-]+)?",text):
        name,_,version=text.partition("==")
        api="https://pypi.org/pypi/"+name+("/"+version if version else "")+"/json"
        route=make_plan({**data,"url":api},settings)["route"]
        release=await metadata(api,route,settings)
        files=release.get("urls") or []
        preferred=next((f for f in files if f["filename"].endswith("py3-none-any.whl")),None)
        preferred=preferred or next((f for f in files if f["packagetype"]=="sdist"),None)
        if not preferred:raise ValueError("这个包只有平台专用发行物，请选择适合平台的文件链接")
        return {**data,"url":preferred["url"],"expected_sha256":data.get("expected_sha256") or preferred.get("digests",{}).get("sha256","")},None
    if cid=="linux" and (v:=re.fullmatch(r"ubuntu\s+(\d{2}\.\d{2}(?:\.\d+)?)",text,re.I)):
        version=v[1];base="https://releases.ubuntu.com/"+version+"/"
        route=make_plan({**data,"url":base},settings)["route"]
        checksums=await metadata(base+"SHA256SUMS",route,settings,as_text=True)
        match=re.search(r"(?m)^([0-9a-fA-F]{64})\s+\*?(ubuntu-"+re.escape(version)+r"(?:\.\d+)?-desktop-amd64\.iso)\s*$",checksums)
        if not match:raise ValueError("该发行目录中没有匹配的桌面 x64 ISO，请输入镜像链接")
        return {**data,"url":base+match[2],"expected_sha256":data.get("expected_sha256") or match[1]},None
    url=urlsplit(text)
    host=(url.hostname or "").lower()
    if url.scheme and url.scheme!="https" and url.scheme!="http":
        return {**data,"url":text},None
    if host and (url.username is not None or url.password is not None):
        raise ValueError("请使用不含凭据的资源链接")
    family="github" if host in {"www.github.com","github.com"} else "huggingface" if host=="huggingface.co" else "modelscope" if host in {"modelscope.cn","www.modelscope.cn"} else None
    if host and (not family or cid not in {None,"general",family}):return {**data,"url":text},None
    family=family or cid
    if family not in {"github","huggingface","modelscope"}:return {**data,"url":text},None
    repo=url.path.strip("/") if host else text.strip("/")
    if family=="modelscope" and host:repo=repo.removeprefix("models/")
    dataset=family=="huggingface" and repo.startswith("datasets/")
    if dataset:repo=repo.removeprefix("datasets/")
    if family=="github":repo=repo.removesuffix(".git")
    if not REPO.fullmatch(repo):
        if host:return {**data,"url":text},None
        raise ValueError("请输入 作者/仓库名，或粘贴文件链接")
    # Determine the metadata route from the same channel policy as the transfer.
    base="https://huggingface.co" if family=="huggingface" else "https://github.com"
    probe=make_plan({**data,"channel":family,"url":base+"/"}, {**settings,"profiles":{k:{**v,"source":"original"} for k,v in settings.get("profiles",{}).items()}})
    route=probe["route"]
    if family=="modelscope":
        if "/" not in repo:raise ValueError("请输入魔搭完整模型名，例如 Qwen/Qwen2.5-0.5B-Instruct")
        if probe["engine"] not in FILE_ENGINES:raise ValueError("整仓下载支持内置 HTTP、HTTPX 或 cURL 核心")
        listing=await metadata("https://modelscope.cn/api/v1/models/"+repo+"/repo/files?Revision=master&Recursive=true",route,settings)
        if not listing.get("Success"):raise ValueError("无法取得魔搭公开文件清单")
        files=[]
        for f in listing["Data"]["Files"]:
            if f.get("Type")!="blob":continue
            if not re.fullmatch("[a-f0-9]{40,64}",f.get("Revision","")):raise ValueError("文件版本无效")
            entry=file_entry({"rfilename":f["Path"],"size":f["Size"],"lfs":{"sha256":f.get("Sha256","")}})
            entry["revision"]=f["Revision"];files.append(entry)
        check_tree(files)
        prefix="https://modelscope.cn/models/"+repo+"/resolve/"
        revision=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
        return {**data,"channel":family,"url":prefix+files[0]["revision"]+"/"+quote(files[0]["path"])},dict(repo=repo,revision=revision,base=prefix,files=files,total=sum(f["size"] for f in files))
    if family=="github":
        if "/" not in repo:
            found=await metadata("https://api.github.com/search/repositories?"+urlencode({"q":repo+" in:name","per_page":12}),route,settings)
            repo=choose([v["full_name"] for v in found["items"]],repo)
        return {**data,"channel":family,"url":"https://github.com/"+repo+"/archive/HEAD.zip"},None
    kind="datasets" if dataset else "models"
    profile=settings.get("profiles",{}).get(family,{})
    origin="https://hf-mirror.com" if profile.get("source")=="hf-mirror" else base
    async def get_repo(name):
        return await metadata(origin+"/api/"+kind+"/"+quote(name,safe="/")+"?blobs=true",route,settings,True)
    info=await get_repo(repo) if "/" in repo else None
    if "/" not in repo:
        results=await metadata(origin+"/api/"+kind+"?"+urlencode({"search":repo,"limit":12}),route,settings)
        repo=choose([item["id"] for item in results],repo)
        info=await get_repo(repo)
    if not info:raise ValueError("找不到该公开仓库")
    revision=info.get("sha","")
    if not re.fullmatch(r"[a-fA-F0-9]{40,64}",revision):raise ValueError("无法锁定仓库版本")
    files=[file_entry(r) for r in info.get("siblings",[])]
    check_tree(files)
    canonical=info.get("id") or repo
    if not REPO.fullmatch(canonical):raise ValueError("目录服务返回无效仓库名")
    prefix=origin+"/"+("datasets/" if dataset else "")+canonical+"/resolve/"+revision+"/"
    snap=dict(repo=canonical,revision=revision,base=prefix,files=files,
              total=sum(f["size"] for f in files) if all(isinstance(f["size"],int) for f in files) else None)
    if probe["engine"] not in FILE_ENGINES:raise ValueError("整仓下载支持内置 HTTP、HTTPX 或 cURL 核心")
    return {**data,"channel":family,"url":prefix+quote(files[0]["path"],safe="/")},snap


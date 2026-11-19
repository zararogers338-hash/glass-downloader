"""Common streaming replies for the HTTP file scheduler. Redirects are handled above this layer."""
import asyncio
from .catalog import executable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from multidict import CIMultiDict
import aiohttp
from aiohttp_socks import ProxyConnector
from .processes import owned_process

BUFFER=128*1024


def transport(route, settings):
    connector=ProxyConnector.from_url(f"socks5://127.0.0.1:{settings['tor_port']}",rdns=True) if route=="tor" else None
    proxy=f"http://127.0.0.1:{settings['mihomo_port']}" if route=="mihomo" else None
    return aiohttp.ClientSession(connector=connector,trust_env=False,auto_decompress=False,
        cookie_jar=aiohttp.DummyCookieJar(),headers={"Accept-Encoding":"identity"},
        timeout=aiohttp.ClientTimeout(total=None,sock_connect=30,sock_read=60)),proxy


@dataclass
class Reply:
    status:int
    headers:object
    chunks:object
    protocol:str
    url:object


@asynccontextmanager
async def file_transport(engine,route,settings):
    if engine=="http":
        session,proxy=transport(route,settings)
        async with session:
            @asynccontextmanager
            async def get(url,headers):
                async with session.get(url,proxy=proxy,headers=headers,allow_redirects=False) as r:
                    yield Reply(r.status,r.headers,r.content.iter_chunked(BUFFER),f"HTTP/{r.version.major}.{r.version.minor}",url)
            yield get
    elif engine=="httpx":
        import httpx
        if route=="tor":raise ValueError("HTTPX 适配器不支持 Tor")
        proxy=f"http://127.0.0.1:{settings['mihomo_port']}" if route=="mihomo" else None
        async with httpx.AsyncClient(http2=True,trust_env=False,proxy=proxy,timeout=httpx.Timeout(60,connect=30),
                                     headers={"Accept-Encoding":"identity"}) as client:
            @asynccontextmanager
            async def get(url,headers):
                try:
                    async with client.stream("GET",str(url),headers=headers,follow_redirects=False) as r:
                        yield Reply(r.status_code,r.headers,r.aiter_raw(),r.http_version,url)
                except httpx.TransportError as e:
                    raise aiohttp.ClientConnectionError(f"HTTPX 连接中断：{type(e).__name__}") from e
            yield get
    elif engine=="curl":
        binary=executable("curl")
        if not binary:raise ValueError("未安装 cURL")
        proxy={"direct":"","mihomo":f"http://127.0.0.1:{settings['mihomo_port']}","tor":f"socks5h://127.0.0.1:{settings['tor_port']}"}[route]
        @asynccontextmanager
        async def get(url,headers):
            args=[binary,"--disable","--silent","--no-buffer","--include","--suppress-connect-headers","--globoff",
                  "--proto","=http,https","--connect-timeout","30","--speed-time","60","--speed-limit","1",
                  "--proxy",proxy,"--noproxy","*" if route=="direct" else "","-H","Accept-Encoding: identity"]
            for k,v in headers.items():args+=["-H",f"{k}: {v}"]
            args+=["--",str(url)]
            async with owned_process(args,stdout=asyncio.subprocess.PIPE) as proc:
                while True:
                    first=(await proc.stdout.readline()).decode("latin1").split()
                    if len(first)<2 or not first[0].startswith("HTTP/") or not first[1].isdigit():
                        raise aiohttp.ClientConnectionError("cURL 未收到有效的 HTTP 响应")
                    status=int(first[1]);fields=CIMultiDict()
                    while True:
                        line=await proc.stdout.readline()
                        if not line:raise aiohttp.ClientConnectionError("cURL 响应头提前结束")
                        if line in {b"\r\n",b"\n"}:break
                        k,sep,v=line.decode("latin1").partition(":")
                        if sep:fields.add(k,v.strip())
                    if status>=200:break
                async def chunks():
                    while data:=await proc.stdout.read(BUFFER):
                        yield data
                    if code:=await proc.wait():
                        raise aiohttp.ClientPayloadError(f"cURL 传输中断（{code}）")
                yield Reply(status,fields,chunks(),first[0],url)
        yield get
    else:
        raise ValueError("未知 HTTP 传输核心")


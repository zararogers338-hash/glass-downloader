"""Offline regression checks for shorthand and snapshot resolution."""
import asyncio
import tempfile
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.resolver import resolve_input, ChooseRepo, check_tree, file_entry
from core.catalog import make_plan

async def main():
    settings={"profiles":{},"default_route":"direct","mihomo_port":7890,"tor_port":9050}
    async def input_for(channel,text):
        return await resolve_input(dict(channel=channel,url=text),settings)
    for text in ["BV1ap4y1p7wt","【视频分享】 https://www.bilibili.com/video/BV1ap4y1p7wt/?p=2&share_source=copy_web","https://b23.tv/abc"]:
        data,_=await input_for("bilibili",text)
        assert make_plan(data,settings)["engine"]=="yt-dlp"
        assert "share_source" not in data["url"]
        if "?p=2" in text:assert data["url"].endswith("/?p=2")
    data,_=await input_for("github","octocat/Hello-World")
    assert data["url"].endswith("/octocat/Hello-World/archive/HEAD.zip")
    with patch("core.resolver.metadata",new=AsyncMock(return_value={"items":[{"full_name":"a/test"},{"full_name":"b/test"}]})):
        try:await input_for("github","test")
        except ChooseRepo as e:assert len(e.choices)==2
        else:raise AssertionError("ambiguous repository needs owner selection")
    with patch("core.resolver.metadata",new=AsyncMock(return_value={"id":"test/model","sha":"a"*40,"siblings":[{"rfilename":"onnx/model.onnx","size":3}]})):
        data,spec=await input_for("huggingface","test/model")
        assert spec["total"]==3 and spec["revision"] in data["url"] and spec["files"][0]["path"]=="onnx/model.onnx"
    for path in ("../escape","CON/invalid",r"nested\bad","a/b."):
        try:file_entry({"rfilename":path})
        except ValueError:pass
        else:raise AssertionError(path)
    try:check_tree([{"path":"nested/file"},{"path":"NESTED/FILE"}])
    except ValueError:pass
    else:raise AssertionError("case collision")
    for channel,text,expected in (("python","3.13.5","amd64.exe"),("java","JDK 21","/21/"),("arxiv","1706.03762","/pdf/1706"),("cpp","LLVM 20.1.8","LLVM-20.1.8-win64")):
        data,_=await input_for(channel,text);assert expected in data["url"]
    print("PASS: BV, share link, repository names, ambiguity, snapshot paths and version shortcuts")

if __name__=="__main__":asyncio.run(main())


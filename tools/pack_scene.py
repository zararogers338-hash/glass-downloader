"""Prepare a launcher scene pack from a PNG, preserving its master."""
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]

def pack(source, channel, scene, title, archive=False):
    folder=ROOT/"scene-packs"/scene
    folder.mkdir(exist_ok=True)
    master=folder/"master.png"
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if master.exists() and hashlib.sha256(master.read_bytes()).hexdigest()!=digest:
        raise FileExistsError("已有不同母图，请使用新的场景 ID")
    if not master.exists():shutil.copyfile(source,master)
    with Image.open(master) as im:
        width,height=im.size
        for key,limit,quality in [("wallpaper",(3840,2160),94),("preview",(480,270),87)]:
            im.thumbnail(limit,Image.Resampling.LANCZOS)
            im.save(folder/(key+".webp"),quality=quality,method=4)
    manifest=dict(id=scene,version=1,channel=channel,title=title,layers=[dict(src="wallpaper.webp",depth=0)],
                  preview="preview.webp",master=dict(src="master.png",width=width,height=height,sha256=digest))
    (folder/"scene.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),"utf8")
    if archive:
        with zipfile.ZipFile(folder.with_suffix(".zip"),"w") as z:
            for name in ("scene.json","master.png","wallpaper.webp","preview.webp"):z.write(folder/name,name)
        with zipfile.ZipFile(folder.with_suffix(".zip")) as z:
            assert z.testzip() is None and hashlib.sha256(z.read("master.png")).hexdigest()==digest
    print(scene,width,height)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("source",type=Path);p.add_argument("channel");p.add_argument("scene");p.add_argument("title")
    p.add_argument("--zip",action="store_true")
    a=p.parse_args();pack(a.source,a.channel,a.scene,a.title,a.zip)


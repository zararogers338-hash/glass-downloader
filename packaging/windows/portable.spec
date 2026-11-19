# -*- mode: python ; coding: utf-8 -*-
import json
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, copy_metadata
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct,
)

root = Path(SPECPATH).parents[1]
version = json.loads((root/"package.json").read_text("utf8"))["version"]
data = [(str(root/name), ".") for name in ("channels.json", "engines.json", "speed-profiles.json", "LICENSE", "ASSETS.md")]
data += [(str(root/"dist"), "dist"), (str(root/".local/portable/THIRD-PARTY-NOTICES.zip"), "licenses")]
scenes = {c["scene"] for c in json.loads((root/"channels.json").read_text("utf8"))}
for scene in sorted(scenes):
    dest = "scene-packs/" + scene
    for name in ("scene.json", "preview.webp", "wallpaper.webp"):
        data.append((str(root/dest/name), dest))
native = root/"src-tauri/target/release/glass-downloader.exe"
# The Tauri shell loads its own resources; store it unchanged.
data.append((str(native), "desktop"))
data += copy_metadata("yt-dlp")
a = Analysis([str(root/"packaging/windows/portable_entry.py")], pathex=[str(root)],
             datas=data, binaries=[], hiddenimports=collect_submodules("yt_dlp.extractor"),
             excludes=["tkinter","pytest","IPython","sphinx"])
pyz = PYZ(a.pure)
numbers = tuple(int(x) for x in version.split(".")) + (0,)
properties = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numbers, prodvers=numbers, mask=0x3f, flags=0, OS=0x40004,
                      fileType=1, subtype=0, date=(0,0)),
    kids=[StringFileInfo([StringTable("040904B0", [
        StringStruct("ProductName", "泊岸 · Glass Downloader"),
        StringStruct("FileDescription", "Glass Downloader desktop workbench"),
        StringStruct("FileVersion", version),
        StringStruct("ProductVersion", version),
        StringStruct("OriginalFilename", f"GlassDownloader-{version}-windows-x64.exe"),
    ])]), VarFileInfo([VarStruct("Translation",[0x0409,1200])])],
)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=f"GlassDownloader-{version}-windows-x64",
          console=False, debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          icon=str(root/"src-tauri/icons/icon.ico"), version=properties)

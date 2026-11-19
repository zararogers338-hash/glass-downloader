"""Install pinned Windows x64 optional tools privately, validating WinGet archive digests."""
import hashlib
import io
import os
import platform
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

DEST = Path(__file__).resolve().parents[1] / ".components"
PACKAGES = [
    ("BBDown", "https://github.com/nilaoda/BBDown/releases/download/1.6.3/BBDown_1.6.3_20240814_win-x64.zip",
     "40f1e2af0d4e74df765c6f93d2e931f9bea201d5168d0bc62dc35a54b7e0ec02", "BBDown.exe"),
    ("aria2", "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip",
     "67d015301eef0b612191212d564c5bb0a14b5b9c4796b76454276a4d28d9b288", "aria2-1.37.0-win-64bit-build1/aria2c.exe"),
]

if __name__ == "__main__":
    if os.name != "nt" or platform.machine().lower() not in {"amd64","x86_64"}:
        raise SystemExit("These pinned archives are for Windows x64. Other platforms can provide tools on PATH.")
    DEST.mkdir(exist_ok=True)
    for name, url, checksum, member in PACKAGES:
        with urlopen(url, timeout=45) as response:
            data=response.read()
        if hashlib.sha256(data).hexdigest() != checksum:
            raise SystemExit(name+" archive digest mismatch")
        with ZipFile(io.BytesIO(data)) as archive:
            content=archive.read(member)
        target=DEST/Path(member).name
        tmp=target.with_suffix(".new")
        tmp.write_bytes(content)
        os.replace(tmp,target)
        print(name, "verified and installed")


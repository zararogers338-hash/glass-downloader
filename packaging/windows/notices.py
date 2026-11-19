"""Collect local license texts, without embedding build-machine paths."""
from importlib import metadata
from pathlib import Path
import json
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / ".local" / "portable"
LEGAL = re.compile(r"^(?:licen[sc]e|copying|notice|copyright|unlicense)(?:$|[-_. ].*)", re.I)


def legal_files(directory):
    for path in directory.iterdir():
        if LEGAL.match(path.name):
            if path.is_file():
                yield path
            elif path.is_dir():
                yield from (p for p in path.rglob("*") if p.is_file())


def build():
    archive_path = BUILD / "THIRD-PARTY-NOTICES.zip"
    index = []
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
        def package(kind, name, version, license_id, paths):
            index.append(f"{kind} | {name} | {version} | {license_id or 'See upstream package'}")
            for n, path in enumerate(sorted(set(paths))):
                archive.write(path, f"{kind}/{name}/{version}/{n:02d}-{path.name}")

        archive.write(ROOT/"LICENSE", "project/LICENSE")
        archive.write(ROOT/"ASSETS.md", "project/ASSETS.md")
        archive.write(Path(sys.base_prefix)/"LICENSE.txt", "Python/LICENSE.txt")
        for dist in metadata.distributions():
            paths = [dist.locate_file(f) for f in dist.files or () if LEGAL.match(f.name)
                     or any(x.lower() == "licenses" for x in f.parts)]
            package("Python", dist.metadata["Name"], dist.version, dist.metadata.get("License-Expression"),
                    [p for p in paths if p.is_file()])
        lock = json.loads((ROOT/"package-lock.json").read_text("utf8"))
        for rel, spec in lock["packages"].items():
            if rel and not spec.get("dev") and (ROOT/rel).is_dir():
                package("npm", rel.split("node_modules/")[-1], spec["version"], spec.get("license"), legal_files(ROOT/rel))
        cargo = json.loads((BUILD/"cargo-metadata.json").read_text(encoding="utf-8-sig"))
        for entry in cargo["packages"]:
            base = Path(entry["manifest_path"]).parent
            paths = list(legal_files(base))
            if entry.get("license_file"):
                path = base/entry["license_file"]
                if path.is_file():
                    paths.append(path)
            package("Cargo", entry["name"], entry["version"], entry.get("license"), paths)
        archive.writestr("INDEX.txt", "Build dependency and license inventory\n\n"+"\n".join(sorted(index))+"\n")
    print(archive_path.name, len(index), "inventory entries")


if __name__ == "__main__":
    build()

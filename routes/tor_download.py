"""Download one HTTP(S) resource through an existing local Tor SOCKS listener."""

import argparse
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlsplit


def download(url: str, output: Path, port: int = 9050) -> None:
    address = urlsplit(url)
    if address.scheme not in {"http", "https"} or not address.hostname:
        raise ValueError("Expected an HTTP or HTTPS URL")
    if not 1 <= port <= 65535:
        raise ValueError("Invalid local SOCKS port")
    if output.exists():
        raise FileExistsError(output)
    with tempfile.TemporaryDirectory(dir=output.parent) as staging:
        partial = Path(staging) / "download"
        subprocess.run([
            "curl", "--disable", "--globoff", "--fail", "--silent", "--show-error",
            "--location", "--proto", "=http,https", "--proto-redir", "=http,https",
            "--connect-timeout", "30", "--proxy", f"socks5h://127.0.0.1:{port}",
            "--noproxy", "", "--output", str(partial), "--", url,
        ], check=True)
        # Publish the completed file without clobbering a concurrent download.
        output.hardlink_to(partial)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("output", type=Path)
    parser.add_argument("--port", type=int, default=9050)
    args = parser.parse_args()
    try:
        download(args.url, args.output, args.port)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Tor download failed: {error}\n")

# Build with Python 3.13 x64, Node, Rust/MSVC and WebView2 on Windows x64.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$python = Join-Path $PWD '.venv/Scripts/python.exe'
if (!(Test-Path $python)) {
  python -m venv .venv
  if ($LASTEXITCODE) { exit $LASTEXITCODE }
}
& $python -c "import platform,struct; assert platform.system()=='Windows' and platform.machine().lower() in ('amd64','x86_64') and struct.calcsize('P')==8"
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $python -m pip install -r requirements.txt 'pyinstaller==6.22.3'
if ($LASTEXITCODE) { exit $LASTEXITCODE }
npm.cmd ci
if ($LASTEXITCODE) { exit $LASTEXITCODE }
npm.cmd run build
if ($LASTEXITCODE) { exit $LASTEXITCODE }
# Keep Rust panic locations useful without publishing a builder's home directory.
$separator = [char]31
$flags = @()
if ($env:CARGO_ENCODED_RUSTFLAGS) {
  $flags = @($env:CARGO_ENCODED_RUSTFLAGS -split $separator)
} elseif ($env:RUSTFLAGS) {
  $flags = @($env:RUSTFLAGS -split '\s+' | Where-Object { $_ })
}
$flags += "--remap-path-prefix=$($env:USERPROFILE)=/build/home"
$flags += "--remap-path-prefix=$($PWD.Path)=/build/glass-downloader"
$env:CARGO_ENCODED_RUSTFLAGS = $flags -join $separator
& ./tools/build-desktop.ps1
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$build = Join-Path $PWD '.local/portable'
$out = Join-Path $PWD 'deliverables/windows'
New-Item -Force -ItemType Directory -Path $build,$out | Out-Null
cargo metadata --format-version 1 --manifest-path src-tauri/Cargo.toml --filter-platform x86_64-pc-windows-msvc --locked | Set-Content (Join-Path $build 'cargo-metadata.json') -Encoding utf8
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $python packaging/windows/notices.py
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $python -m PyInstaller --noconfirm --distpath $out --workpath (Join-Path $build 'work') packaging/windows/portable.spec
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$version = (Get-Content package.json -Raw | ConvertFrom-Json).version
$filename = "GlassDownloader-$version-windows-x64.exe"
Copy-Item -Force (Join-Path $build 'THIRD-PARTY-NOTICES.zip') $out
$hash = (Get-FileHash (Join-Path $out $filename) -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $filename" | Set-Content (Join-Path $out "$filename.sha256") -Encoding ascii
Write-Output (Join-Path $out $filename)

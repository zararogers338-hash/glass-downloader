$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$privateTools = Join-Path $PWD '.toolchain'
if (Test-Path (Join-Path $privateTools 'cargo/bin/cargo.exe')) {
  $env:CARGO_HOME = Join-Path $privateTools 'cargo'
  $env:RUSTUP_HOME = Join-Path $privateTools 'rustup'
  $env:PATH = (Join-Path $privateTools 'cargo/bin') + ';' + $env:PATH
}
cargo build --manifest-path src-tauri/Cargo.toml --release --features custom-protocol
exit $LASTEXITCODE

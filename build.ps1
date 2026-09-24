$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run python -m venv .venv first."
}

& $python -m pip install -e "$PSScriptRoot[build]"
& $python -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "PhotoClean.spec")

Write-Host "Build complete: $PSScriptRoot\dist\PhotoClean\PhotoClean.exe"

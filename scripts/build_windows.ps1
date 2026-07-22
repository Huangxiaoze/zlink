# Build LeafLink.exe on Windows
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating venv..."
    python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install -U pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
& .\.venv\Scripts\python.exe scripts\build.py --clean @args

Write-Host ""
Write-Host "Output: dist\LeafLink\LeafLink.exe"

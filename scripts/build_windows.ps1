# Build ZLink for Windows:
#   1) PyInstaller onedir  -> dist\ZLink\ZLink.exe
#   2) Inno Setup installer -> dist\ZLink-Setup-<version>.exe
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -NoInstaller
#   powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -InstallInnoSetup
#   powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -OneFile

param(
    [switch]$NoInstaller,
    [switch]$InstallInnoSetup,
    [switch]$OneFile,
    [switch]$Console,
    [switch]$Clean = $true
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Find-Iscc {
    $envPath = $env:INNO_SETUP_ISCC
    if (-not $envPath) { $envPath = $env:ISCC }
    if ($envPath -and (Test-Path $envPath)) { return (Resolve-Path $envPath).Path }

    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) { return $path }
    }
    return $null
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating venv..."
    python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install -U pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt

$pyArgs = @("scripts\build.py")
if ($Clean) { $pyArgs += "--clean" }
if ($Console) { $pyArgs += "--console" }
if ($OneFile -and $NoInstaller) { $pyArgs += "--onefile" }

$wantInstaller = -not $NoInstaller -and -not $OneFile
if ($wantInstaller) {
    $iscc = Find-Iscc
    if (-not $iscc -and $InstallInnoSetup) {
        Write-Host "Installing Inno Setup via winget..."
        winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements
        $iscc = Find-Iscc
    }
    if (-not $iscc) {
        Write-Host ""
        Write-Host "Inno Setup not found. Building app folder only." -ForegroundColor Yellow
        Write-Host "To produce a Windows installer (Setup.exe), install Inno Setup 6:"
        Write-Host "  winget install --id JRSoftware.InnoSetup -e"
        Write-Host "or re-run:  .\scripts\build_windows.ps1 -InstallInnoSetup"
        Write-Host ""
        $wantInstaller = $false
    }
    else {
        $env:INNO_SETUP_ISCC = $iscc
        $pyArgs += "--installer"
        Write-Host "Using Inno Setup: $iscc"
    }
}

& .\.venv\Scripts\python.exe @pyArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
if (Test-Path "dist\ZLink\ZLink.exe") {
    Write-Host "App     : dist\ZLink\ZLink.exe"
}
$setup = Get-ChildItem "dist\ZLink-Setup-*.exe" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($setup) {
    Write-Host "Installer: $($setup.FullName)"
}
elseif ($OneFile -and (Test-Path "dist\ZLink.exe")) {
    Write-Host "Portable : dist\ZLink.exe"
}

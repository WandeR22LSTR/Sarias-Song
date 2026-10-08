<#
.SYNOPSIS
  Create (or update) the .venv and install Saria's Song's dependencies.

.DESCRIPTION
  Run from anywhere:
      powershell -ExecutionPolicy Bypass -File .\scripts\dev-setup.ps1
      powershell -ExecutionPolicy Bypass -File .\scripts\dev-setup.ps1 -Dev    # also installs pytest

  The `-ExecutionPolicy Bypass` is for this one command only; it does not change
  your system policy. The script never needs to "activate" the venv, it calls the
  venv's python.exe directly, so it also works under the default Restricted policy.
#>
param(
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$WantedVersion = "3.13"

# Repo root = the parent of the scripts folder.
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# Prefer the py launcher so we get 3.13 even if another Python is first on PATH.
# $PyExe plus the splatted $PyArgs (possibly empty) avoids passing a $null argument.
$PyExe = $null
$PyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    try {
        & py "-$WantedVersion" -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) { $PyExe = "py"; $PyArgs = @("-$WantedVersion") }
    }
    catch {
        # py exists but has no 3.13: fall through to plain python.
    }
}
if (-not $PyExe) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python not found. Install Python $WantedVersion (64-bit) from python.org, then run this again."
    }
    $PyExe = "python"
}

$found = (& $PyExe @PyArgs -c "import sys; print('%d.%d' % sys.version_info[:2])").Trim()
if ($found -ne $WantedVersion) {
    Write-Warning "Python $found found, but this project is developed and tested on $WantedVersion. It may still work; if something odd happens, install $WantedVersion."
}

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating .venv with Python $found ..."
    & $PyExe @PyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment." }
}
else {
    Write-Host ".venv already exists, updating it."
}

$requirements = if ($Dev) { "requirements-dev.txt" } else { "requirements.txt" }
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $VenvPython -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) { throw "Installing $requirements failed." }

Write-Host ""
Write-Host "Done. Run the tray app with:" -ForegroundColor Green
Write-Host "    .\.venv\Scripts\python.exe .\src\tray.py"
Write-Host "Run just the saver in a window with:"
Write-Host "    cd src; ..\.venv\Scripts\python.exe -m saver.main /s --windowed"

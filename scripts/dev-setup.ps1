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

# Ask an interpreter for its "major.minor" version. Returns $null unless it really
# ran and answered. This matters on Windows 10/11: with no Python installed,
# `python` is still a Microsoft Store placeholder that prints "Python was not found"
# instead of running, so "the command exists" is not proof that Python exists.
function Get-PythonVersion {
    param([string]$Exe, [string[]]$ExeArgs)
    try {
        $out = & $Exe @ExeArgs -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $text = ("$out").Trim()
            if ($text -match '^\d+\.\d+$') { return $text }
        }
    }
    catch {
        # Not runnable: treat as "no such Python".
    }
    return $null
}

# Default install folder names look like "Python313".
$FolderName = "Python" + $WantedVersion.Replace(".", "")

# Candidates in order of preference: the py launcher pinned to 3.13, then any py 3, then
# python on PATH. The last two are Python's default install folders: a Python installed
# a minute ago (e.g. by winget) is not on the PATH of a PowerShell window that was
# already open, but it is already sitting in these folders.
$candidates = @(
    @{ Exe = "py"; Args = @("-$WantedVersion") },
    @{ Exe = "py"; Args = @("-3") },
    @{ Exe = "python"; Args = @() },
    @{ Exe = (Join-Path $env:LOCALAPPDATA "Programs\Python\$FolderName\python.exe"); Args = @() },
    @{ Exe = (Join-Path $env:ProgramFiles "$FolderName\python.exe"); Args = @() }
)

$PyExe = $null
$PyArgs = @()
$found = $null
$tried = @()  # what we saw for each candidate, shown if nothing works
foreach ($c in $candidates) {
    $label = ("$($c.Exe) $($c.Args -join ' ')").Trim()
    $cmd = Get-Command $c.Exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) { $tried += "  $label : not found"; continue }
    $version = Get-PythonVersion -Exe $c.Exe -ExeArgs $c.Args
    if (-not $version) {
        $tried += "  $label : exists at $($cmd.Source) but did not run (a Microsoft Store placeholder?)"
        continue
    }
    $tried += "  $label : Python $version ($($cmd.Source))"
    if (-not $found -or $version -eq $WantedVersion) {
        $PyExe = $c.Exe; $PyArgs = $c.Args; $found = $version
    }
    if ($found -eq $WantedVersion) { break }
}

if (-not $found) {
    $triedText = $tried -join [Environment]::NewLine
    throw @"
No working Python found. (If you saw 'Python was not found; run without arguments to
install from the Microsoft Store', that is only a placeholder, Python itself is not installed.)

What I looked at:
$triedText

Install Python $WantedVersion (64-bit), then CLOSE and reopen PowerShell and run this again:
    winget install -e --id Python.Python.$WantedVersion
or download it from https://www.python.org/downloads/ and tick 'Add python.exe to PATH'.
"@
}
if ($found -ne $WantedVersion) {
    Write-Warning "Python $found found, but this project is developed and tested on $WantedVersion. It may still work; if something odd happens, install $WantedVersion."
}

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating .venv with Python $found ..."
    & $PyExe @PyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) { throw "Could not create the virtual environment." }
}
else {
    Write-Host ".venv already exists, updating it."
}

$requirements = if ($Dev) { "requirements-dev.txt" } else { "requirements.txt" }
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $VenvPython -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) { throw "Installing $requirements failed." }

# Prove the install is usable before saying "Done".
& $VenvPython -c "import pygame, pystray, PIL"
if ($LASTEXITCODE -ne 0) { throw "The packages installed but could not be imported." }

Write-Host ""
Write-Host "Done. Run the tray app with:" -ForegroundColor Green
Write-Host "    .\.venv\Scripts\python.exe .\src\tray.py"
Write-Host "Run just the saver in a window with:"
Write-Host "    cd src; ..\.venv\Scripts\python.exe -m saver.main /s --windowed"

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$frontendIndex = Join-Path $projectRoot "frontend\dist\index.html"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "The Hub is not set up yet. Run scripts\bootstrap.ps1 first."
}

if (-not (Test-Path -LiteralPath $frontendIndex)) {
    throw "The interface has not been built. Run scripts\bootstrap.ps1 first."
}

& $venvPython -m friendly_hub.launcher

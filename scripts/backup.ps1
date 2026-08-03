$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "The Hub is not set up yet. Run scripts\bootstrap.ps1 first."
}

& $venvPython -m friendly_hub.db.backup
if ($LASTEXITCODE -ne 0) { throw "The local safety backup failed." }

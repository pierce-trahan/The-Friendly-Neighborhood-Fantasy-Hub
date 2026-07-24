$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$frontendRoot = Join-Path $projectRoot "frontend"

if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv (Join-Path $projectRoot ".venv")
}

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Python package-manager upgrade failed." }
& $venvPython -m pip install -e "$projectRoot\backend[dev]"
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }
& $venvPython "$projectRoot\scripts\generate_contracts.py"
if ($LASTEXITCODE -ne 0) { throw "API contract generation failed." }

Push-Location $frontendRoot
try {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
    npm.cmd run generate:api
    if ($LASTEXITCODE -ne 0) { throw "Frontend API type generation failed." }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Setup complete. Run scripts\run.ps1 to open the Hub."

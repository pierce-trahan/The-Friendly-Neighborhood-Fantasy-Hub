$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$frontendRoot = Join-Path $projectRoot "frontend"
$pytestTemp = Join-Path $projectRoot ("tmp\pytest-" + [guid]::NewGuid().ToString("N"))

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "The project environment is missing. Run scripts\bootstrap.ps1 first."
}

New-Item -ItemType Directory -Path (Split-Path -Parent $pytestTemp) -Force | Out-Null

& $venvPython -m ruff check "$projectRoot\backend" "$projectRoot\scripts"
if ($LASTEXITCODE -ne 0) { throw "Backend linting failed." }
& $venvPython -m pytest "$projectRoot\backend" --basetemp $pytestTemp
if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }
& $venvPython "$projectRoot\scripts\generate_contracts.py"
if ($LASTEXITCODE -ne 0) { throw "API contract generation failed." }

Push-Location $frontendRoot
try {
    npm.cmd run generate:api
    if ($LASTEXITCODE -ne 0) { throw "Frontend API type generation failed." }
    npm.cmd run typecheck
    if ($LASTEXITCODE -ne 0) { throw "Frontend type-checking failed." }
    npm.cmd test
    if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }
    npm.cmd audit --audit-level=high
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency audit failed." }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "All Friendly Hub verification checks passed."

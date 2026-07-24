$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$frontendRoot = Join-Path $projectRoot "frontend"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "The project environment is missing. Run scripts\bootstrap.ps1 first."
}

$backendProcess = Start-Process `
    -FilePath $venvPython `
    -ArgumentList "-m", "uvicorn", "friendly_hub.main:app", "--host", "127.0.0.1", "--port", "8765", "--reload" `
    -WorkingDirectory (Join-Path $projectRoot "backend") `
    -WindowStyle Hidden `
    -PassThru

try {
    Push-Location $frontendRoot
    npm.cmd run dev
}
finally {
    Pop-Location
    if (-not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id
    }
}

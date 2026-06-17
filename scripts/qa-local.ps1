param(
  [switch]$SkipBackendTests,
  [switch]$SkipBuild,
  [switch]$SkipE2E
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "venv\Scripts\python.exe"
$frontend = Join-Path $root "frontend"

function Invoke-QACommand {
  param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
  )

  & $FilePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
  }
}

Push-Location $root
try {
  Invoke-QACommand $python manage.py seed_qa_data --reset-passwords --reset-e2e-data
  Invoke-QACommand $python manage.py check
  if (-not $SkipBackendTests) {
    Invoke-QACommand $python manage.py test calificaciones
  }
} finally {
  Pop-Location
}

Push-Location $frontend
try {
  Invoke-QACommand npm test
  Invoke-QACommand npm run lint
  if (-not $SkipBuild) {
    Invoke-QACommand npm run build
  }
  if (-not $SkipE2E) {
    $previousE2EPort = $env:E2E_FRONTEND_PORT
    if (-not $env:E2E_FRONTEND_PORT) {
      $env:E2E_FRONTEND_PORT = "3100"
    }
    try {
      Invoke-QACommand npm run test:e2e
    } finally {
      $env:E2E_FRONTEND_PORT = $previousE2EPort
    }
  }
} finally {
  Pop-Location
}

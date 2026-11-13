# Установка с нуля на Windows. Запускать из корня репозитория.
$ErrorActionPreference = "Stop"

$pyOk = python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Нужен Python 3.12 или новее."
    python -V
    exit 1
}

python -m venv .venv
& .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e ".[xlsx]"

if (-not (Test-Path config.toml)) { Copy-Item config.example.toml config.toml }
if (-not (Test-Path profile.toml)) { Copy-Item profile.example.toml profile.toml }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

Write-Host ""
Write-Host "Установлено."
Write-Host "1. hh-applicant-tool auth"
Write-Host "2. впишите id резюме в config.toml и факты в profile.toml"
Write-Host "3. hhjob doctor"

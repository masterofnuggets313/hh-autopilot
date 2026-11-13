#!/usr/bin/env bash
# Установка с нуля. Запускать из корня репозитория.
set -e

PY=${PYTHON:-python3}

if ! $PY -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
    echo "Нужен Python 3.12 или новее. Текущий: $($PY -V 2>&1)"
    exit 1
fi

$PY -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -e ".[xlsx]"

[ -f config.toml ] || cp config.example.toml config.toml
[ -f profile.toml ] || cp profile.example.toml profile.toml
[ -f .env ] || cp .env.example .env

echo
echo "Установлено."
echo "1. hh-applicant-tool auth"
echo "2. впишите id резюме в config.toml и факты в profile.toml"
echo "3. hhjob doctor"

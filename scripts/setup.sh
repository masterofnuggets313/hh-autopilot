#!/usr/bin/env bash
# Установка с нуля. Запускать из корня репозитория.
set -e

PY=${PYTHON:-python3}

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

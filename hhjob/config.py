"""Конфигурация: .env для секретов, config.toml и profile.toml для остального."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def load_env(path: Path) -> dict[str, str]:
    """Читает .env без сторонних библиотек. Секреты в репозиторий не попадают."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


@dataclass
class Track:
    """Один трек поиска: резюме плюс набор запросов."""

    name: str
    resume_id: str
    queries: list[str] = field(default_factory=list)
    salary_from: int = 0


@dataclass
class Limits:
    per_run: int = 10
    per_day: int = 40
    pause_seconds: float = 4.0


@dataclass
class Config:
    root: Path
    config_dir: Path | None = None
    area: int = 113
    profile_id: str = ""
    schedule: str = "remote"
    only_with_salary: bool = True
    tracks: dict[str, Track] = field(default_factory=dict)
    limits: Limits = field(default_factory=Limits)
    tags: dict[str, list[str]] = field(default_factory=dict)
    cold_markers: list[str] = field(default_factory=list)
    gph_markers: list[str] = field(default_factory=list)
    blockers_scope: str = "all"
    profile: dict[str, Any] = field(default_factory=dict)

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def state_dir(self) -> Path:
        return self.root / ".state"


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load(root: Path | None = None) -> Config:
    root = Path(root or Path.cwd())
    env = load_env(root / ".env")
    for key, value in env.items():
        os.environ.setdefault(key, value)

    raw = _read_toml(root / "config.toml")
    # Если каталог токенов не задан явно, переменную не трогаем: пусть
    # hh-applicant-tool берет свой каталог по умолчанию, туда же кладет токен
    # команда `hh-applicant-tool auth`.
    cfg_raw = os.environ.get("HH_CONFIG_DIR") or raw.get("config_dir") or ""
    cfg_dir = Path(cfg_raw).expanduser() if cfg_raw else None

    tracks: dict[str, Track] = {}
    for name, data in (raw.get("tracks") or {}).items():
        tracks[name] = Track(
            name=name,
            resume_id=str(data.get("resume_id", "")),
            queries=list(data.get("queries") or []),
            salary_from=int(data.get("salary_from") or 0),
        )

    limits_raw = raw.get("limits") or {}
    limits = Limits(
        per_run=int(limits_raw.get("per_run", 10)),
        per_day=int(limits_raw.get("per_day", 40)),
        pause_seconds=float(limits_raw.get("pause_seconds", 4.0)),
    )

    profile_raw = _read_toml(root / "profile.toml")
    return Config(
        root=root,
        config_dir=cfg_dir,
        area=int(raw.get("area", 113)),
        profile_id=str(raw.get("profile_id") or os.environ.get("HH_PROFILE_ID") or ""),
        schedule=str(raw.get("schedule", "remote")),
        only_with_salary=bool(raw.get("only_with_salary", True)),
        tracks=tracks,
        limits=limits,
        tags=dict(raw.get("tags") or {}),
        cold_markers=list((raw.get("filters") or {}).get("cold") or []),
        gph_markers=list((raw.get("filters") or {}).get("gph") or []),
        blockers_scope=str((raw.get("filters") or {}).get("scope") or "all"),
        profile=profile_raw.get("profile") or {},
    )

"""Журнал отправленного. Нужен, чтобы не откликнуться дважды на одну вакансию."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _path(root: Path) -> Path:
    return root / ".state" / "sent.json"


def load(root: Path) -> dict[str, Any]:
    path = _path(root)
    if not path.exists():
        return {"sent": {}, "runs": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save(root: Path, data: dict[str, Any]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def already_sent(data: dict[str, Any], vacancy_id: str) -> bool:
    return str(vacancy_id) in (data.get("sent") or {})


def mark(data: dict[str, Any], vacancy_id: str, **info: Any) -> None:
    data.setdefault("sent", {})[str(vacancy_id)] = {
        "at": datetime.now().isoformat(timespec="seconds"),
        **info,
    }


def sent_today(data: dict[str, Any]) -> int:
    today = date.today().isoformat()
    return sum(
        1 for v in (data.get("sent") or {}).values() if str(v.get("at", "")).startswith(today)
    )


def log_run(data: dict[str, Any], **info: Any) -> None:
    data.setdefault("runs", []).append(
        {"at": datetime.now().isoformat(timespec="seconds"), **info}
    )

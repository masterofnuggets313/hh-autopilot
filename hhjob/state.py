"""Журнал отправленного и память между запусками.

Здесь три вещи, которых не хватало:

1. Ключ по компании и названию. hh выдает перепост той же вакансии с новым id,
   и по одному id такой дубль не отловить.
2. Память о блокировке. После капчи темп снижается на неделю, а не до
   следующего запуска.
3. Очередь отложенных. Если уперлись в дневной лимит, остаток не теряется.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

BLOCK_DAYS = 7

# Предлоги и союзы, которые в названиях гуляют туда-сюда: «менеджер по продажам»
# и «менеджер продаж» это одна вакансия, а не две.
STOP_WORDS = {
    "по", "в", "на", "и", "с", "со", "для", "от", "до", "из", "за", "при", "о", "об",
    "the", "a", "an", "of", "and", "for", "with", "to", "in", "at",
}


def _path(root: Path) -> Path:
    return root / ".state" / "sent.json"


def load(root: Path) -> dict[str, Any]:
    path = _path(root)
    if not path.exists():
        return {"sent": {}, "runs": [], "keys": {}, "meta": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("sent", {})
    data.setdefault("runs", [])
    data.setdefault("keys", {})
    data.setdefault("meta", {})
    return data


def save(root: Path, data: dict[str, Any]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def title_key(title: str) -> str:
    """Ключ по набору слов в названии.

    Перестановка слов и пунктуация не мешают, а лишнее слово (город, сегмент,
    уровень) делает ключ другим. Это разные вакансии, а не перепост: так же
    решают в career-ops, иначе один работодатель с офисами в двух городах
    выглядит как перепост.
    """
    words = re.findall(r"[а-яёa-z0-9]+", (title or "").lower())
    words = [w for w in words if w not in STOP_WORDS]
    return "|".join(sorted(set(words)))


def sent_key(employer: str, title: str) -> str:
    return f"{(employer or '').strip().lower()}|{title_key(title)}"


def already_sent(
    data: dict[str, Any],
    vacancy_id: str,
    employer: str | None = None,
    title: str | None = None,
) -> bool:
    if str(vacancy_id) in (data.get("sent") or {}):
        return True
    if employer or title:
        return sent_key(employer or "", title or "") in (data.get("keys") or {})
    return False


def mark(data: dict[str, Any], vacancy_id: str, **info: Any) -> None:
    data.setdefault("sent", {})[str(vacancy_id)] = {
        "at": datetime.now().isoformat(timespec="seconds"),
        **info,
    }
    employer = info.get("employer") or ""
    title = info.get("name") or info.get("title") or ""
    if employer or title:
        data.setdefault("keys", {})[sent_key(employer, title)] = str(vacancy_id)


def sent_today(data: dict[str, Any]) -> int:
    today = date.today().isoformat()
    return sum(
        1 for v in (data.get("sent") or {}).values() if str(v.get("at", "")).startswith(today)
    )


def log_run(data: dict[str, Any], **info: Any) -> None:
    data.setdefault("runs", []).append(
        {"at": datetime.now().isoformat(timespec="seconds"), **info}
    )
    data.setdefault("meta", {})["last_run"] = datetime.now().isoformat(timespec="seconds")


# --- блокировки и темп ---


def block(data: dict[str, Any], reason: str, days: int = BLOCK_DAYS) -> None:
    now = datetime.now()
    data["block"] = {
        "at": now.isoformat(timespec="seconds"),
        "until": (now + timedelta(days=days)).isoformat(timespec="seconds"),
        "reason": reason[:200],
    }


def blocked_until(data: dict[str, Any]) -> datetime | None:
    raw = (data.get("block") or {}).get("until")
    if not raw:
        return None
    try:
        until = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return until if until > datetime.now() else None


def pause_for(data: dict[str, Any], base: float) -> float:
    """Пауза между откликами. После блокировки удваивается на неделю."""
    return float(base) * 2 if blocked_until(data) else float(base)


# --- очередь отложенных ---


def set_postponed(data: dict[str, Any], ids: list[str]) -> None:
    data["postponed"] = [str(i) for i in ids]


def postponed(data: dict[str, Any]) -> list[str]:
    return [str(i) for i in data.get("postponed") or []]


def clear_postponed(data: dict[str, Any]) -> None:
    data.pop("postponed", None)


# --- служебные отметки ---


def last_run_days(data: dict[str, Any]) -> float | None:
    """Сколько дней прошло с последнего запуска. None, если запусков не было."""
    raw = (data.get("meta") or {}).get("last_run")
    if not raw:
        return None
    try:
        last = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return (datetime.now() - last).total_seconds() / 86400


def resume_hash(data: dict[str, Any]) -> str:
    return str((data.get("meta") or {}).get("resume_hash") or "")


def set_resume_hash(data: dict[str, Any], value: str) -> None:
    data.setdefault("meta", {})["resume_hash"] = value

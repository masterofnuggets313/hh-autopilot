"""Отчет по воронке: сколько откликов, где висят, где отказы."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from . import hh

STATE_NAMES = {
    "response": "ждет ответа",
    "discard": "отказ",
    "interview": "собеседование",
    "invitation": "приглашение",
    "hired": "оффер",
}


def rows(api) -> list[dict[str, Any]]:
    out = []
    for n in hh.negotiations(api):
        v = n.get("vacancy") or {}
        emp = v.get("employer") or {}
        st = (n.get("state") or {}).get("id") or ""
        out.append(
            {
                "vacancy_id": v.get("id"),
                "vacancy": v.get("name") or "",
                "employer": emp.get("name") or "",
                "state": st,
                "state_name": STATE_NAMES.get(st, st),
                "created_at": n.get("created_at") or "",
                "updated_at": n.get("updated_at") or "",
                "url": v.get("alternate_url") or "",
            }
        )
    return out


def summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(i["state"] for i in items)
    total = len(items)
    return {
        "total": total,
        "by_state": dict(counter),
        "waiting": counter.get("response", 0),
        "discards": counter.get("discard", 0),
        "interviews": counter.get("interview", 0) + counter.get("invitation", 0),
    }


def to_csv(items: list[dict[str, Any]], path: Path) -> Path:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(items[0].keys()) if items else [])
        if items:
            writer.writeheader()
            writer.writerows(items)
    return path


def to_xlsx(items: list[dict[str, Any]], path: Path) -> Path:
    """xlsx, если установлен openpyxl. Иначе csv рядом."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError:
        return to_csv(items, path.with_suffix(".csv"))

    wb = Workbook()
    ws = wb.active
    ws.title = "Отклики"
    headers = list(items[0].keys()) if items else []
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for item in items:
        ws.append([item.get(h) for h in headers])
    ws.freeze_panes = "A2"
    for i, width in enumerate([12, 45, 28, 14, 18, 22, 22, 38], start=1):
        ws.column_dimensions[chr(64 + i)].width = width
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path

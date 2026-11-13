"""Отклики с письмами. Сначала проверки, потом отправка.

Порядок намеренный: валидация письма и вакансии до запроса, потому что отклик
с пустым или битым письмом уже не отозвать.
"""

from __future__ import annotations

import time
from typing import Any

from . import filters, hh, letters, state


def plan(
    api,
    targets: list[dict[str, Any]],
    profile: dict[str, Any],
    tags_cfg: dict[str, list[str]],
    ledger: dict[str, Any],
    template: str,
    *,
    limit: int = 0,
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Готовит к отправке. Возвращает (готовые, причины пропуска)."""
    ready: list[dict[str, Any]] = []
    skipped: list[tuple[str, str]] = []

    for v in targets:
        vid = str(v["id"])
        if state.already_sent(ledger, vid):
            skipped.append((vid, "уже откликались"))
            continue
        if v.get("archived"):
            skipped.append((vid, "в архиве"))
            continue

        full = hh.vacancy(api, vid)
        if full.get("archived"):
            skipped.append((vid, "в архиве"))
            continue

        tags = filters.tags_for(full, tags_cfg)
        text = letters.build(full, profile, tags, template)
        problems = letters.check(text)
        if problems:
            skipped.append((vid, "; ".join(problems)))
            continue

        ready.append({"vacancy": full, "letter": text, "tags": tags})
        if limit and len(ready) >= limit:
            break

    return ready, skipped


def send(
    api,
    ready: list[dict[str, Any]],
    ledger: dict[str, Any],
    root,
    *,
    resume_for: dict[str, str],
    default_resume: str,
    pause: float = 4.0,
    dry: bool = False,
    per_day: int = 40,
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    sent: list[dict[str, Any]] = []
    failed: list[tuple[str, str]] = []
    today = state.sent_today(ledger)

    for item in ready:
        v = item["vacancy"]
        vid = str(v["id"])
        if today >= per_day:
            failed.append((vid, f"дневной лимит {per_day} достигнут"))
            break

        resume_id = resume_for.get(vid, default_resume)
        if dry:
            sent.append({"id": vid, "dry": True, "chars": len(item["letter"])})
            continue

        try:
            hh.apply(api, resume_id, vid, item["letter"], delay=pause)
        except Exception as exc:  # noqa: BLE001
            msg = f"{type(exc).__name__}: {exc}"[:200]
            failed.append((vid, msg))
            low = str(exc).lower()
            if "captcha" in low or "403" in low or "limit" in low:
                failed.append((vid, "похоже на капчу или лимит, остановились"))
                break
            continue

        state.mark(ledger, vid, employer=v.get("employer"), resume=resume_id)
        state.save(root, ledger)
        today += 1
        sent.append(
            {
                "id": vid,
                "employer": v.get("employer"),
                "name": v.get("name"),
                "chars": len(item["letter"]),
            }
        )
        time.sleep(1.5)

    return sent, failed

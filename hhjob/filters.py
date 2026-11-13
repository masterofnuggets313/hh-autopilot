"""Фильтры и оценка вакансий.

Главная идея: hh не различает «до вычета» и «на руки», поэтому фильтр по зарплате
пропускает вакансии ниже планки. Здесь все суммы приводятся к деньгам на руки.
"""

from __future__ import annotations

import re
from typing import Any

# Признаки холодного поиска и активных продаж. Ищем по тексту вакансии.
DEFAULT_COLD = [
    r"холодн\w* (звон|поиск|баз|обзвон)",
    r"холодные звонки",
    r"обзвон",
    r"поиск (новых )?клиентов",
    r"привлечени\w* (новых )?клиент",
    r"активн\w* продаж",
    r"лидогенерац",
    r"собственн\w* клиентск\w* баз",
    r"налажива\w* контакт",
]

# Признаки оформления не по ТК.
DEFAULT_GPH = [
    r"ГПХ",
    r"гражданско-правов\w*",
    r"самозанят",
    r"оформлени\w* через ИП",
    r"работа как ИП",
]

NET_RATE = 0.87  # НДФЛ 13 процентов


def _match(patterns: list[str], text: str) -> list[str]:
    hits = []
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            hits.append(m.group(0))
    return hits


def cold_hits(text: str, patterns: list[str] | None = None) -> list[str]:
    return _match(patterns or DEFAULT_COLD, text)


def gph_hits(text: str, patterns: list[str] | None = None) -> list[str]:
    return _match(patterns or DEFAULT_GPH, text)


def net_salary(v: dict[str, Any]) -> int | None:
    """Сумма на руки по нижней границе. None, если зарплата не указана."""
    low = v.get("salary_from") or v.get("salary_to")
    if not low:
        return None
    low = int(low)
    return round(low * NET_RATE) if v.get("gross") else low


def money_label(v: dict[str, Any]) -> str:
    low, high = v.get("salary_from"), v.get("salary_to")
    if not low and not high:
        return "не указана"
    if low and high:
        base = f"{low} до {high}"
    elif low:
        base = f"от {low}"
    else:
        base = f"до {high}"
    suffix = " до вычета" if v.get("gross") else " на руки"
    net = net_salary(v)
    if v.get("gross") and net:
        return f"{base}{suffix}, около {net} на руки"
    return f"{base}{suffix}"


def tags_for(v: dict[str, Any], tags: dict[str, list[str]]) -> list[str]:
    """Какие темы затронуты в вакансии. По ним подбираются блоки письма."""
    haystack = f"{v.get('name', '')} {v.get('text', '')}".lower()
    found = []
    for tag, patterns in tags.items():
        for p in patterns:
            if re.search(p, haystack, re.I):
                found.append(tag)
                break
    return found


def score(v: dict[str, Any], tags: dict[str, list[str]]) -> int:
    """Оценка соответствия: темы из названия весят больше, чем из текста."""
    name = (v.get("name") or "").lower()
    text = (v.get("text") or "").lower()
    total = 0
    for patterns in tags.values():
        if any(re.search(p, name, re.I) for p in patterns):
            total += 3
        elif any(re.search(p, text, re.I) for p in patterns):
            total += 1
    return total


def pick(
    items: list[dict[str, Any]],
    *,
    tags: dict[str, list[str]] | None = None,
    salary_min: int = 0,
    drop_cold: bool = True,
    cold_patterns: list[str] | None = None,
    gph_patterns: list[str] | None = None,
    limit: int = 0,
) -> list[dict[str, Any]]:
    """Отсеивает холодные и низкооплачиваемые, считает оценку, сортирует."""
    tags = tags or {}
    out = []
    for v in items:
        text = v.get("text") or ""
        cold = cold_hits(text, cold_patterns)
        gph = gph_hits(text, gph_patterns)
        if drop_cold and cold:
            continue
        if gph:
            continue
        net = net_salary(v)
        if salary_min and net is not None and net < salary_min:
            continue
        item = dict(v)
        item["cold"] = cold
        item["gph"] = gph
        item["net"] = net
        item["score"] = score(v, tags)
        out.append(item)
    out.sort(key=lambda x: (x["score"], x.get("net") or 0), reverse=True)
    return out[:limit] if limit else out

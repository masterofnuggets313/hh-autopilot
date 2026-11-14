"""Фильтры и оценка вакансий.

Две вещи, которые здесь важнее остальных:

1. hh не различает «до вычета» и «на руки», поэтому все суммы приводятся
   к деньгам на руки.
2. Блокер ищется не как подстрока, а с учетом отрицания. «Без холодных
   звонков» это не холодные звонки, а наоборот то, что нужно. Без этой
   проверки фильтр выбрасывал ровно те вакансии, ради которых написан.
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

# Фразы, которые означают плюс, а не минус. Их показываем в карточке,
# чтобы при разборе было видно, за что вакансия понравилась.
PLUS_MARKERS = [
    r"без холодн\w* (звонк|поиск|обзвон|баз)",
    r"только входящ\w* (заявк|звонк|лид|поток)",
    r"входящ\w* поток",
    r"тепл\w* (баз|клиент|лид)",
    r"без поиска (новых )?клиент",
    r"не нужно заниматься холодн",
    r"готов\w* баз",
]

# Отрицание перед совпадением: «без холодных звонков», «не нужно заниматься
# холодным обзвоном». Смотрим только внутри той же части предложения, иначе
# «нет холодных звонков, но есть обзвон» спрятал бы настоящий блокер.
NEGATION_WINDOW = 70
NEGATION_AFTER = 40
NEG_BEFORE = re.compile(
    r"(?:^|[^\w])(без|не\s+нужн\w*|не\s+требу\w*|никаких|не\s+будет|нет|"
    r"исключен\w*|не\s+придет\w*|не\s+предстоит|не\s+связан\w*)",
    re.I,
)
# «не ГПХ», «не ИП»: отрицание стоит вплотную перед маркером. Только в конце
# окна, иначе «не только холодные звонки» тоже считалось бы отрицанием.
NEG_JUST_BEFORE = re.compile(r"(?:^|[^\w])не\s*$", re.I)
NEG_AFTER = re.compile(
    r"^\s*(?:\S+\s+){0,3}(?:нет|не\s+(?:будет|нужн\w*|требу\w*|предстоит)|"
    r"отсутству\w*|исключен\w*)",
    re.I,
)
CLAUSE = re.compile(r"[,.;:!?()\n]")
WORD_CHAR = re.compile(r"[а-яёa-z0-9_]", re.I)

# Заголовки блоков описания. Нужны, чтобы отличать требования от «будет
# плюсом» и от рассказа о компании.
HEADINGS = re.compile(
    r"^\s*(требовани\w*|ожидани\w*|обязанности|задачи|чем предстоит заниматься|"
    r"что нужно делать|что предстоит делать|requirements|responsibilities|"
    r"you will|what you.ll do|будет плюсом|желательно|nice to have|"
    r"условия|мы предлагаем|что мы предлагаем|оформление|о компании|бонусы|"
    r"плюсы)\s*:?\s*$",
    re.I | re.M,
)
COUNTS_AS_REQUIREMENT = re.compile(
    r"^(требовани|ожидани|обязанност|задачи|чем|что нужно|что предстоит|"
    r"requirements|responsibilities|you|what)",
    re.I,
)

NET_RATE = 0.87  # НДФЛ 13 процентов

# Граница слова слева. Нужна для коротких маркеров вроде ГПХ: без нее он
# находится внутри других слов.
_LEFT = r"(?<![а-яёa-z0-9])"


def _compiled(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(_LEFT + "(?:" + p + ")", re.I) for p in patterns]


def requirements_block(text: str) -> str:
    """Только блоки требований и обязанностей.

    Если заголовков нет, возвращает весь текст: молча сузить область поиска
    опаснее, чем проверить лишнее.
    """
    marks = list(HEADINGS.finditer(text))
    if not marks:
        return text
    out = []
    for i, mark in enumerate(marks):
        if not COUNTS_AS_REQUIREMENT.search(mark.group(1)):
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append(text[mark.end():end])
    body = "\n".join(out).strip()
    return body or text


def _negated(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - NEGATION_WINDOW):start]
    cut = 0
    for m in CLAUSE.finditer(before):
        cut = m.end()
    tail = before[cut:]
    if NEG_BEFORE.search(tail) or NEG_JUST_BEFORE.search(tail):
        return True

    # Маркер может оборваться на середине слова: «Холодных звон|ков нет».
    # Дотягиваем до конца слова, иначе отрицание после него не видно.
    while end < len(text) and WORD_CHAR.match(text[end]):
        end += 1

    after = text[end:end + NEGATION_AFTER]
    stop = CLAUSE.search(after)
    if stop:
        after = after[:stop.start()]
    return bool(NEG_AFTER.search(after))


def _scan(text: str, patterns: list[str]) -> tuple[list[str], list[str]]:
    """Возвращает (настоящие совпадения, совпадения под отрицанием)."""
    real: list[str] = []
    negated: list[str] = []
    for rx in _compiled(patterns):
        for m in rx.finditer(text):
            frag = m.group(0).strip()
            if _negated(text, m.start(), m.end()):
                if frag not in negated:
                    negated.append(frag)
            elif frag not in real:
                real.append(frag)
    return real, negated


def cold_hits(text: str, patterns: list[str] | None = None) -> list[str]:
    """Настоящие признаки холодного поиска. Отрицания сюда не попадают."""
    real, _ = _scan(text, patterns or DEFAULT_COLD)
    return real


def cold_negated(text: str, patterns: list[str] | None = None) -> list[str]:
    """Признаки, которые стоят под отрицанием: это плюс, а не минус."""
    _, negated = _scan(text, patterns or DEFAULT_COLD)
    return negated


def gph_hits(text: str, patterns: list[str] | None = None) -> list[str]:
    real, _ = _scan(text, patterns or DEFAULT_GPH)
    return real


def gph_negated(text: str, patterns: list[str] | None = None) -> list[str]:
    _, negated = _scan(text, patterns or DEFAULT_GPH)
    return negated


def plus_hits(text: str) -> list[str]:
    real, _ = _scan(text, PLUS_MARKERS)
    return real


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
    scope: str = "all",
    limit: int = 0,
) -> list[dict[str, Any]]:
    """Отсеивает холодные и низкооплачиваемые, считает оценку, сортирует.

    scope = "requirements" сужает поиск блокеров до блоков требований
    и обязанностей. По умолчанию проверяется весь текст: так безопаснее,
    потому что заголовки в описаниях есть не всегда.
    """
    tags = tags or {}
    out = []
    for v in items:
        text = v.get("text") or ""
        haystack = requirements_block(text) if scope == "requirements" else text
        cold = cold_hits(haystack, cold_patterns)
        gph = gph_hits(haystack, gph_patterns)
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
        item["cold_negated"] = cold_negated(text, cold_patterns)
        item["gph_negated"] = gph_negated(text, gph_patterns)
        item["plus"] = plus_hits(text)
        item["net"] = net
        item["score"] = score(v, tags)
        out.append(item)
    out.sort(key=lambda x: (x["score"], x.get("net") or 0), reverse=True)
    return out[:limit] if limit else out

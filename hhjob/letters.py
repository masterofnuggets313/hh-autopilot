"""Сборка писем из шаблона и блоков профиля.

Письмо не генерируется моделью: оно собирается из фактов, которые человек сам
записал в profile.toml. Блоки подбираются по темам, найденным в тексте вакансии.
Так письмо остается правдой, а не пересказом вакансии.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

PLACEHOLDERS = [
    "{",
    "}",
    "%(",
    "[имя",
    "[название",
    "[компания",
    "укажите",
    "вставьте",
    "TODO",
    "XXX",
    "ЗАМЕНИТЕ",
]

MIN_LEN = 400
MAX_LEN = 5000


def load_template(root: Path, family: str = "base") -> str:
    path = root / "templates" / "letters" / f"{family}.md"
    if not path.exists():
        path = root / "templates" / "letters" / "base.md"
    return path.read_text(encoding="utf-8")


def _blocks(profile: dict[str, Any], key: str, tags: list[str]) -> list[dict[str, Any]]:
    """Блоки, у которых есть общая тема с вакансией. Блок без тем считается общим."""
    out = []
    for block in profile.get(key) or []:
        block_tags = [t.lower() for t in (block.get("tags") or [])]
        if not block_tags or set(block_tags) & set(tags):
            out.append(block)
    return out


def build(
    vacancy: dict[str, Any],
    profile: dict[str, Any],
    tags: list[str],
    template: str,
    max_proof: int = 3,
) -> str:
    """Собирает письмо. vacancy должен содержать name, employer, text."""
    employer = vacancy.get("employer") or "компания"
    role = vacancy.get("name") or "вакансия"

    why = _blocks(profile, "why", tags)
    why_text = why[0]["text"] if why else (
        f"Откликаюсь на вакансию «{role}» в {employer}. Прочитал описание целиком, "
        "задачи понятны."
    )

    proof = _blocks(profile, "proof", tags)[:max_proof]
    proof_text = "\n\n".join(b["text"].strip() for b in proof)

    gap = _blocks(profile, "gap", tags)
    gap_text = gap[0]["text"].strip() if gap else ""

    question = profile.get("question") or (
        "Подскажите, что для вас будет главным результатом первых 3 месяцев."
    )

    # подстановка через replace, а не format: в тексте пользователя могут быть фигурные скобки
    values = {
        "{greeting}": profile.get("greeting") or "Здравствуйте!",
        "{why_company}": why_text.strip(),
        "{proof}": proof_text.strip(),
        "{gap}": gap_text,
        "{question}": question.strip(),
        "{signature}": (profile.get("signature") or profile.get("name") or "").strip(),
        "{employer}": employer,
        "{vacancy}": role,
    }
    letter = template
    for key, value in values.items():
        letter = letter.replace(key, value)
    letter = re.sub(r"\n{3,}", "\n\n", letter)
    # пустые блоки не должны оставлять двойные переводы строк
    return letter.strip()


def check(text: str) -> list[str]:
    """Проблемы, из-за которых письмо нельзя отправлять."""
    problems = []
    for token in PLACEHOLDERS:
        if token in text:
            problems.append(f"плейсхолдер {token!r}")
    if len(text) < MIN_LEN:
        problems.append(f"слишком короткое: {len(text)} символов")
    if len(text) > MAX_LEN:
        problems.append(f"длиннее лимита hh: {len(text)} символов")
    if text.rstrip().endswith((",", ":", ";")):
        problems.append("письмо обрывается на знаке")
    return problems

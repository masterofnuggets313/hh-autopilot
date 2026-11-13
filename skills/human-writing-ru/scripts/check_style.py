"""Проверка русского текста на машинные признаки, канцелярит, падежи и повторы.

Использование:
    python check_style.py file.md
    python check_style.py file.md --repeat-against other.md
    type file.md | python check_style.py -
    python check_style.py file.md --blocks     # проверять только ``` блоки
    python check_style.py file.md --no-grammar # без проверки падежей

Коды возврата: 0 чисто, 1 есть ошибки уровня ОШИБКА.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:
    import grammar
except Exception:  # модуль грамматики сломан, работаем без него
    grammar = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DASHES = {
    "\u2014": "длинное тире",
    "\u2013": "среднее тире",
    "\u2012": "цифровое тире",
}
ELLIPSIS = ["\u2026", "..."]

CLICHES = [
    "в современном мире",
    "в эпоху цифровизации",
    "стремительно развивается",
    "сегодня как никогда",
    "давайте разберемся",
    "давайте разберёмся",
    "погрузимся в",
    "раскрыть потенциал",
    "вывести на новый уровень",
    "играет ключевую роль",
    "является неотъемлемой частью",
    "важно отметить",
    "важно помнить",
    "важно понимать",
    "стоит учитывать",
    "нельзя не сказать",
    "ключевой аспект",
    "подводя итог",
    "в заключение",
    "безусловно",
    "уникальный",
    "инновационный",
    "отличный вопрос",
    "надеюсь, это поможет",
    "и это меняет все",
    "и это меняет всё",
    "и так далее",
    "и т.д",
    "и т.п",
    "и тому подобное",
    "и прочее",
]

# Канцелярит, который в письмах и анкетах почти всегда лишний.
BUREAU_HARD = [
    "в целях", "в рамках", "на основании", "в соответствии с",
    "на сегодняшний день", "на данный момент", "в настоящее время",
    "на текущий момент", "имеет место", "принимая во внимание",
    "в связи с вышеизложенным", "в связи с чем", "посредством",
    "с целью", "по вопросу", "в количестве", "в размере", "на предмет",
    "ввиду того", "исходя из того", "в силу того",
    "вышеуказанный", "вышеизложенный", "нижеследующий", "функционирование",
    "необходимо отметить", "следует отметить", "стоит отметить",
]

# Мягкие маркеры: бывают уместны, поэтому только предупреждение.
BUREAU_SOFT = [
    "является", "указанный", "настоящий", "в качестве", "в процессе",
    "в ходе", "ввиду", "вследствие", "в области", "оптимизация процессов",
    "системный подход", "комплексный подход", "в кратчайшие сроки",
    "надлежащим образом", "в установленном порядке", "при наличии",
    "при отсутствии", "в случае если", "данный", "данная", "данное",
    "данного", "данной", "данному", "данном", "данным", "данными",
]

BUREAU_RX = [
    (re.compile(r"\bосуществ\w*", re.I), "ОШИБКА", "заменить обычным глаголом"),
    (re.compile(r"\bпроизводит\w*\s+(проверк|оплат|работ|анализ|расчет|оценк|осмотр)", re.I),
     "ОШИБКА", "заменить одним глаголом"),
    (re.compile(r"\bносит\b[^.]{0,25}?характер", re.I), "ОШИБКА", "сказать прямо, что происходит"),
    (re.compile(r"\bпутем\s+[А-Яа-яЁё]", re.I), "ВНИМАНИЕ", "заменить на через или с помощью"),
    # две отглагольные формы подряд: обеспечение функционирования, проведение обучения
    (re.compile(r"\b\w{4,}(ение|ание|ятие)\s+(?:за\s+)?\w{4,}(ением|анием|ятием)\b", re.I),
     "ВНИМАНИЕ", "две отглагольные формы подряд, разбить глаголом"),
    # расщепление сказуемого
    (re.compile(r"\b(провод\w*|провож\w*|провел\w*|провед\w*|выполня\w*|оказыва\w*|"
                r"вести|ведет|веду|ведем|ведут|дает|дать|даю|даем)\s+"
                r"(проверк|анализ|оценк|контрол|обучени|поддержк|мониторинг|расчет|осмотр)", re.I),
     "ВНИМАНИЕ", "заменить одним глаголом"),
]

# Явные числительные: в текстах на отправку почти всегда должны быть цифрами.
NUMERALS_STRONG = re.compile(
    r"\b(четыре|четырех|четырёх|четверо|триста|тридцать|тридцати|пять|пяти|пятеро|"
    r"десяток|сорок|сорока|треть|трети|семь|семи|шесть|шести|восемь|восьми|"
    r"девять|девяти|пара|пару|полгода|полтора|сотня|тысяча)\b",
    re.IGNORECASE,
)

# Спорные: часто это местоимение или оборот ("один и тот же", "одна из"),
# поэтому только предупреждение для глаза, не ошибка.
NUMERALS_WEAK = re.compile(
    r"\b(два|две|двух|двоих|дважды|одну|одной|одного|одном|один|одна|одно)\b",
    re.IGNORECASE,
)
WEAK_OK = ("и тот", "и то", "из", "за другим")

RANGE = re.compile(r"\d+(?:[ \u00a0]\d{3})*\s*[-\u2013\u2014]\s*\d+(?:[ \u00a0]\d{3})*")


def load(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def code_blocks(text: str) -> list[tuple[int, str]]:
    """Возвращает строки внутри ``` блоков с их номерами."""
    out = []
    inside = False
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            inside = not inside
            continue
        if inside:
            out.append((i, line))
    return out


def code_lines(text: str) -> set[int]:
    return {n for n, _ in code_blocks(text)}


def lines_of(text: str, only_blocks: bool) -> list[tuple[int, str]]:
    if only_blocks:
        return code_blocks(text)
    return list(enumerate(text.splitlines(), 1))


def bureaucratic(line: str) -> list[tuple[str, str, str]]:
    out = []
    low = line.lower()
    for c in BUREAU_HARD:
        if c in low:
            out.append(("ОШИБКА", f"канцелярит {c!r}", "переписать обычной речью"))
    for c in BUREAU_SOFT:
        # по границам слова, иначе «появляется» ловится как «является»
        if re.search(rf"(?<![а-яёa-z]){re.escape(c)}(?![а-яёa-z])", low):
            out.append(("ВНИМАНИЕ", f"канцелярит {c!r}", "проверить, можно ли сказать проще"))
    for rx, level, hint in BUREAU_RX:
        m = rx.search(line)
        if m:
            out.append((level, f"канцелярит {m.group(0)!r}", hint))
    return out


def check(text: str, only_blocks: bool, use_grammar: bool = True) -> list[tuple[str, int, str, str]]:
    """Возвращает список (уровень, строка, что найдено, подсказка)."""
    problems = []
    in_code = code_lines(text)
    gram_ok = use_grammar and grammar is not None and grammar.available()

    for n, line in lines_of(text, only_blocks):
        if not line.strip():
            continue
        for ch, name in DASHES.items():
            if ch in line:
                problems.append(("ОШИБКА", n, name, "заменить на запятую, двоеточие или точку"))
        if re.search(r"\s-\s", line):
            problems.append(("ОШИБКА", n, "дефис с пробелами", "переписать без дефиса"))
        for e in ELLIPSIS:
            if e in line:
                problems.append(("ОШИБКА", n, "многоточие", "убрать, закончить мысль"))
        if "ё" in line or "Ё" in line:
            problems.append(("ОШИБКА", n, "буква ё", "писать е"))
        if "₽" in line:
            problems.append(("ОШИБКА", n, "знак рубля", "писать руб."))
        if line.strip() == "---":
            problems.append(("ВНИМАНИЕ", n, "разделитель ---", "в текстах на отправку убрать"))
        m = RANGE.search(line)
        if m:
            problems.append(("ОШИБКА", n, f"диапазон {m.group(0)!r}", "писать 'от X до Y' или 'X или Y'"))
        for c in CLICHES:
            if c in line.lower():
                problems.append(("ОШИБКА", n, f"клише {c!r}", "переписать фразу целиком"))
        for m in NUMERALS_STRONG.finditer(line):
            problems.append(("ОШИБКА", n, f"числительное словом {m.group(0)!r}", "поставить цифру"))
        for m in NUMERALS_WEAK.finditer(line):
            tail = line[m.end():m.end() + 12].lower()
            if any(tail.lstrip().startswith(w) for w in WEAK_OK):
                continue
            problems.append(("ВНИМАНИЕ", n, f"возможно числительное словом {m.group(0)!r}",
                             "если это счет, поставить цифру"))
        if line.count("?") and not line.strip().startswith(("#", "|", "1.", "2.", "3.")):
            problems.append(("ВНИМАНИЕ", n, "знак вопроса", "проверить, не риторический ли"))

        for level, what, hint in bureaucratic(line):
            problems.append((level, n, what, hint))

        # грамматику не гоняем по кускам кода, если это не режим --blocks
        if gram_ok and (only_blocks or n not in in_code) and not line.lstrip().startswith(("|", "#")):
            for level, what, hint in grammar.check(line):
                problems.append((level, n, what, hint))
    return problems


def sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+", flat)
    return [p.strip() for p in parts if len(p.strip()) > 25]


def repeats(text: str, other: str, only_blocks: bool) -> list[tuple[str, str]]:
    a = sentences(" ".join(l for _, l in lines_of(text, only_blocks)))
    b = " ".join(l for _, l in lines_of(other, only_blocks))
    b = re.sub(r"\s+", " ", b)
    found = []
    for s in a:
        if s in b:
            found.append(("ОШИБКА", f"повтор: {s[:90]!r}"))
    # повтор внутри самого текста
    seen = {}
    for s in a:
        seen[s] = seen.get(s, 0) + 1
    for s, n in seen.items():
        if n > 1:
            found.append(("ОШИБКА", f"дубль внутри текста x{n}: {s[:90]!r}"))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="Проверка русского текста на машинные признаки")
    ap.add_argument("path", help="файл или - для stdin")
    ap.add_argument("--repeat-against", help="файл с уже отправленным текстом")
    ap.add_argument("--blocks", action="store_true", help="проверять только ``` блоки")
    ap.add_argument("--no-grammar", action="store_true", help="без проверки падежей и управления")
    args = ap.parse_args()

    text = load(args.path)
    problems = check(text, args.blocks, use_grammar=not args.no_grammar)

    errors = [p for p in problems if p[0] == "ОШИБКА"]
    warnings = [p for p in problems if p[0] == "ВНИМАНИЕ"]

    for level, n, what, hint in problems:
        print(f"{level} стр.{n}: {what} -> {hint}")

    if args.repeat_against:
        other = load(args.repeat_against)
        for level, msg in repeats(text, other, args.blocks):
            print(f"{level}: {msg}")
            errors.append((level, 0, msg, ""))

    note = ""
    if not args.no_grammar and (grammar is None or not grammar.available()):
        note = " | падежи не проверены, нет pymorphy3"
    print(f"\nитог: ошибок {len(errors)}, предупреждений {len(warnings)}, "
          f"символов {len(text)}, строк {text.count(chr(10)) + 1}{note}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

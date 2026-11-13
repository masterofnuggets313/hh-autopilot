"""Согласование падежей, числа и управления в русском тексте.

Работает на морфологии pymorphy3, поэтому проверяет разбор, а не окончания.
Если библиотеки нет, модуль отключается и сообщает об этом через available().

Что проверяется:
  * прилагательное или причастие рядом с существительным (род, число, падеж);
  * число и падеж существительного после цифры (2 года, 5 лет, 21 год);
  * управление предлогов (согласно договору, в течение месяца);
  * типовые ошибки управления (оплатить за, внимание на).
"""
from __future__ import annotations

import re

try:
    import pymorphy3
except ImportError:  # библиотека не установлена
    pymorphy3 = None

MORPH = pymorphy3.MorphAnalyzer() if pymorphy3 else None

TOKEN = re.compile(r"[А-Яа-яЁё][А-Яа-яЁё-]*|\d+")
# только полные прилагательные: причастия часто стоят сказуемым при своем дополнении
# ("цифры написаны словом"), и проверка на согласование давала бы ложные срабатывания
ADJ_POS = {"ADJF"}
NOUN_POS = {"NOUN"}

# местоименные прилагательные, которые разбор отдает как ADJF
ADJ_STOP = {
    "этот", "тот", "весь", "свой", "мой", "твой", "наш", "ваш", "который", "какой",
    "такой", "один", "сам", "самый", "чей", "каждый", "любой", "другой", "иной",
    "некоторый", "данный", "сей", "таков", "это",
}

# служебные слова, которые разбор иногда отдает как существительное
NOT_NOUN = {
    "в", "во", "на", "с", "со", "из", "от", "до", "по", "за", "к", "ко", "о", "об",
    "обо", "при", "про", "для", "без", "под", "над", "через", "между", "и", "а", "но",
    "или", "ли", "же", "бы", "не", "ни", "то", "что", "как", "так", "уже", "еще",
    "это", "при", "ради", "сквозь", "сверх", "вне",
}

NUM_WORDS = {
    "два", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
    "десять", "двадцать", "тридцать", "сорок", "пятьдесят", "сто", "двести",
    "триста", "тысяча", "миллион", "полтора", "пара", "несколько", "много",
    "мало", "больше", "меньше",
}

# после цифры стоит знак, значит число не управляет следующим словом
BAD_AFTER = set(".,;:!?)]}»%+-")

_CACHE: dict[str, list] = {}


def available() -> bool:
    return MORPH is not None


def parses(word: str) -> list:
    key = word.lower()
    got = _CACHE.get(key)
    if got is None:
        got = MORPH.parse(key) if MORPH else []
        _CACHE[key] = got
    return got


def _adj(word: str) -> list:
    return [
        p for p in parses(word)
        if p.tag.POS in ADJ_POS and p.normal_form not in ADJ_STOP
    ]


def _nouns(word: str) -> list:
    low = word.lower()
    if low in NOT_NOUN or word.isupper():
        return []
    return [p for p in parses(word) if p.tag.POS in NOUN_POS]


def tokens(line: str) -> list[tuple[str, str, int, int]]:
    """Список (вид, слово, начало, конец), вид это w для слова и d для числа."""
    return [
        ("d" if m.group(0).isdigit() else "w", m.group(0), m.start(), m.end())
        for m in TOKEN.finditer(line)
    ]


def _case_ok(have: str | None, want: str | None) -> bool:
    if have is None or want is None:
        return True
    if have == want:
        return True
    # винительный и именительный совпадают у неодушевленных и у женского рода
    return {have, want} <= {"accs", "nomn"}


def _agree(a, n) -> bool:
    ta, tn = a.tag, n.tag
    if ta.number and tn.number and ta.number != tn.number:
        return False
    if ta.number != "plur" and ta.gender and tn.gender and ta.gender != tn.gender:
        return False
    return _case_ok(ta.case, tn.case)


def _noun_after(tks: list, start: int, limit: int = 4):
    """Первое существительное после позиции, с пропуском прилагательных.

    Слово, которое разбирается и как прилагательное, и как существительное
    (например "новых"), считается прилагательным, если сразу за ним стоит
    существительное.
    """
    fallback = None
    j = start
    steps = 0
    while j < len(tks) and steps < limit:
        kind, word = tks[j][0], tks[j][1]
        if kind == "d":
            break
        nouns = _nouns(word)
        if nouns:
            if fallback is None:
                fallback = (word, nouns)
            if not _adj(word):
                return word, nouns
            nxt = tks[j + 1] if j + 1 < len(tks) else None
            if nxt and nxt[0] == "w" and _nouns(nxt[1]) and not _adj(nxt[1]):
                j += 1
                steps += 1
                continue
            return word, nouns
        if _adj(word):
            j += 1
            steps += 1
            continue
        break
    return fallback


def _numeral_form(n: int) -> tuple[str, str]:
    tail = n % 100
    if 11 <= tail <= 14:
        return "gent", "plur"
    last = n % 10
    if last == 1:
        return "nomn", "sing"
    if last in (2, 3, 4):
        return "gent", "sing"
    return "gent", "plur"


SINGLE_GOV = {
    "согласно": "datv",
    "благодаря": "datv",
    "вопреки": "datv",
    "наперекор": "datv",
    "вследствие": "gent",
    "ввиду": "gent",
    "наподобие": "gent",
    "около": "gent",
    "после": "gent",
    "кроме": "gent",
    "мимо": "gent",
    "возле": "gent",
    "вокруг": "gent",
    "напротив": "gent",
    "ради": "gent",
    "вне": "gent",
    "сверх": "gent",
}

MULTI_GOV = [
    (("в", "течение"), "gent"),
    (("в", "продолжение"), "gent"),
    (("в", "результате"), "gent"),
    (("в", "силу"), "gent"),
    (("в", "отношении"), "gent"),
    (("в", "целях"), "gent"),
    (("в", "соответствии", "с"), "ablt"),
    (("в", "связи", "с"), "ablt"),
    (("по", "сравнению", "с"), "ablt"),
    (("наряду", "с"), "ablt"),
    (("по", "окончании"), "loct"),
    (("по", "приезде"), "loct"),
]

CASE_NAME = {
    "nomn": "именительный",
    "gent": "родительный",
    "datv": "дательный",
    "accs": "винительный",
    "ablt": "творительный",
    "loct": "предложный",
}

# перед этими словами число стоит не в именительном, правило не применяется
SKIP_BEFORE = {
    "в", "во", "за", "на", "по", "с", "со", "до", "от", "из", "к", "ко", "при",
    "о", "об", "обо", "под", "над", "про", "через", "спустя", "более", "менее",
    "свыше", "около", "почти", "порядка", "среди", "между", "для", "без", "после",
    "вплоть", "примерно", "всего", "уже", "еще", "только",
    "плюс", "итого", "вместе", "минимум", "максимум",
}

COLLOC = [
    # оплатить, оплатил, оплачиваем: все формы глагола, но не "оплата за", которая спорна, а не ошибочна
    (re.compile(r"\bоплати\w*\s+за\b|\bоплач\w+\s+за\b", re.I),
     "оплатить что, а не за что"),
    (re.compile(r"\b(уделить|уделять|уделим|уделяет|уделил)\s+внимани\w*\s+на\b", re.I),
     "уделить внимание чему, а не на что"),
    (re.compile(r"\bзаведующий\s+[А-Яа-яЁё]+\s*(?:ом|ем)\b", re.I), "заведующий чего, а не чем"),
]


def _numeral_counts(line: str, tks: list, i: int) -> bool:
    """Считает ли цифра следующее за ней слово, а не служит меткой или кодом."""
    kind, word, start, end = tks[i]
    if len(word) >= 5:
        return False  # номер вакансии, чата, телефона
    after = line[end:end + 1]
    if after in BAD_AFTER:
        return False  # пункт списка, процент, плюс, конец фразы
    before = line[start - 1] if start > 0 else ""
    if before and before.isalpha():
        return False  # B2B, 1С, SMM2, Битрикс24
    if i > 0:
        prev = tks[i - 1]
        if prev[0] == "d":
            return False  # разделитель тысяч
        low = prev[1].lower()
        if low in SKIP_BEFORE or low in NUM_WORDS:
            return False
    return True


def check(line: str) -> list[tuple[str, str, str]]:
    """Возвращает список (уровень, что найдено, подсказка) для одной строки."""
    if not MORPH:
        return []

    out: list[tuple[str, str, str]] = []
    tks = tokens(line)
    if not tks:
        return out

    # 1. прилагательное и существительное рядом
    for i in range(len(tks) - 1):
        kind, word, _, end = tks[i]
        nkind, nword, nstart, _ = tks[i + 1]
        if kind != "w" or nkind != "w":
            continue
        if line[end:nstart].strip():
            continue  # между словами стоит знак препинания, связи нет
        if word.lower() in SINGLE_GOV:
            continue  # предлог, который разбирается и как прилагательное
        adj, noun = _adj(word), _nouns(nword)
        if not adj or not noun:
            continue
        if i > 0 and tks[i - 1][0] == "d":
            continue  # после числа прилагательное законно стоит во множественном
        if i > 0 and tks[i - 1][1].lower() in NUM_WORDS:
            continue  # три новых тега: та же логика, что и с цифрой
        if any(_agree(a, n) for a in adj for n in noun):
            continue
        out.append(("ОШИБКА", f"не согласовано: {word} {nword}",
                    "поставить прилагательное в тот же род, число и падеж, что у существительного"))

    # 2. число и падеж после цифры
    for i, (kind, word, _start, _end) in enumerate(tks):
        if kind != "d":
            continue
        n = int(word)
        if len(word) == 4 and 1900 <= n <= 2099:
            continue  # это год, а не счет
        if not _numeral_counts(line, tks, i):
            continue
        found = _noun_after(tks, i + 1)
        if not found:
            continue
        nword, noun = found
        want_case, want_number = _numeral_form(n)
        ok = False
        for p in noun:
            case, number = p.tag.case, p.tag.number
            if number != want_number:
                continue
            if case == want_case or (want_case == "nomn" and case == "accs"):
                ok = True
                break
        if ok:
            continue
        out.append(("ОШИБКА", f"после {word} нужно {CASE_NAME[want_case]} "
                              f"{'множественное' if want_number == 'plur' else 'единственное'}: {nword}",
                    "перестроить число или слово"))

    # 3. управление предлогов
    lows = [w.lower() if k == "w" else "" for k, w, _s, _e in tks]
    for i, low in enumerate(lows):
        if low == "в" and i + 1 < len(lows) and lows[i + 1] == "течении":
            out.append(("ОШИБКА", "в течении", "предлог пишется в течение"))
            continue
        if low in SINGLE_GOV:
            found = _noun_after(tks, i + 1)
            if found:
                nword, noun = found
                want = SINGLE_GOV[low]
                cases = [p.tag.case for p in noun]
                if all(c is not None and c != want for c in cases):
                    out.append(("ОШИБКА", f"после {low} нужен {CASE_NAME[want]}: {nword}",
                                "поправить окончание"))
        for seq, want in MULTI_GOV:
            if tuple(lows[i:i + len(seq)]) == seq:
                found = _noun_after(tks, i + len(seq))
                if found:
                    nword, noun = found
                    cases = [p.tag.case for p in noun]
                    if all(c is not None and c != want for c in cases):
                        out.append(("ОШИБКА", f"после {' '.join(seq)} нужен {CASE_NAME[want]}: {nword}",
                                    "поправить окончание"))

    # 4. типовые ошибки управления
    for rx, hint in COLLOC:
        m = rx.search(line)
        if m:
            out.append(("ОШИБКА", f"управление: {m.group(0)!r}", hint))

    return out

"""Проверка того, что скилл лежит в репозитории и валидатор работает."""

import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "skills" / "human-writing-ru"
SCRIPT = SKILL / "scripts" / "check_style.py"

CLEAN = """Здравствуйте. 4 года работаю с продажами в B2B.
Настраивал воронку в Битрикс24 для 30 организаций. Отвечу на вопросы в чате.
"""

DIRTY = """В современном мире продажи — это важно.
Опыт 3-4 года, доход от 80 000–100 000 руб., работаю ещё и удалённо...
"""


def run(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_skill_files_present():
    assert (SKILL / "SKILL.md").exists()
    assert SCRIPT.exists()
    assert (SKILL / "scripts" / "grammar.py").exists()


def test_clean_text_passes(tmp_path):
    path = tmp_path / "clean.md"
    path.write_text(CLEAN, encoding="utf-8")
    result = run(path)
    assert result.returncode == 0, result.stdout
    assert "ошибок 0" in result.stdout


def test_dirty_text_is_caught(tmp_path):
    path = tmp_path / "dirty.md"
    path.write_text(DIRTY, encoding="utf-8")
    result = run(path)
    assert result.returncode == 1
    for expected in ("длинное тире", "буква ё", "многоточие", "клише"):
        assert expected in result.stdout


def test_repeats_against_sent_text(tmp_path):
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    line = "Настраиваю воронку в Битрикс24 и обучаю менеджеров работе с ней."
    first.write_text(line + "\n", encoding="utf-8")
    second.write_text(line + "\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(second), "--repeat-against", str(first)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert "повтор" in result.stdout


def test_full_lint_uses_skill(tmp_path, capfd):
    from hhjob import cli

    path = tmp_path / "letter.md"
    path.write_text(DIRTY, encoding="utf-8")
    code = cli.main(["lint", "--full", str(path)])
    out = capfd.readouterr().out
    assert code == 1
    assert "длинное тире" in out


def test_quick_lint_still_works(tmp_path, capsys):
    from hhjob import cli

    path = tmp_path / "letter.md"
    path.write_text(DIRTY, encoding="utf-8")
    code = cli.main(["lint", str(path)])
    out = capsys.readouterr().out
    assert code == 1
    assert "замечаний" in out


def _grammar():
    pytest.importorskip("pymorphy3")
    if str(SKILL / "scripts") not in sys.path:
        sys.path.insert(0, str(SKILL / "scripts"))
    import grammar

    if not grammar.available():
        pytest.skip("pymorphy3 не разобрался")
    return grammar


def test_cases_after_preposition():
    grammar = _grammar()
    found = [what for _, what, _ in grammar.check("Согласно договора работа идет по плану.")]
    assert any("согласно" in what for what in found)


def test_payment_government_in_past_tense():
    grammar = _grammar()
    found = [what for _, what, _ in grammar.check("Клиент оплатил за услуги.")]
    assert any("оплатил за" in what for what in found)


def test_payment_noun_is_not_flagged():
    grammar = _grammar()
    found = [what for _, what, _ in grammar.check("Оплата за месяц прошла вовремя.")]
    assert not any("оплата за" in what for what in found)

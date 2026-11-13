"""Письма: сборка из блоков, подбор по темам, защита от плейсхолдеров."""

from pathlib import Path

from hhjob import letters

ROOT = Path(__file__).resolve().parents[1]

PROFILE = {
    "name": "Тест Тестов",
    "signature": "Тест Тестов",
    "greeting": "Здравствуйте!",
    "question": "Что будет главным результатом первых 3 месяцев?",
    "why": [{"tags": ["sales"], "text": "Откликаюсь на роль в вашей компании."}],
    "proof": [
        {"tags": ["sales"], "text": "Вывел отдел на 30 млн руб. выручки."},
        {"tags": ["crm"], "text": "Спроектировал модель данных на 13 модулей."},
    ],
    "gap": [{"tags": ["sales"], "text": "Опыта в вашей отрасли нет."}],
}

VACANCY = {"name": "Руководитель отдела продаж", "employer": "Ромашка",
           "text": "Нужен руководитель отдела продаж, CRM и воронка."}


def test_build_contains_blocks():
    template = letters.load_template(ROOT)
    text = letters.build(VACANCY, PROFILE, ["sales", "crm"], template)
    assert "30 млн руб." in text
    assert "13 модулей" in text
    assert "Опыта в вашей отрасли нет." in text
    assert "Тест Тестов" in text


def test_build_skips_foreign_tags():
    template = letters.load_template(ROOT)
    text = letters.build(VACANCY, PROFILE, ["seo"], template)
    assert "30 млн руб." not in text


def test_placeholder_detected():
    problems = letters.check("Здравствуйте! {vacancy} и еще текст. " * 20)
    assert any("плейсхолдер" in p for p in problems)


def test_short_letter_detected():
    problems = letters.check("Здравствуйте. Коротко.")
    assert any("короткое" in p for p in problems)


def test_normal_letter_passes():
    body = "Здравствуйте! " + "Работал с CRM и воронкой продаж. " * 20 + "Спасибо."
    assert letters.check(body) == []


def test_braces_in_profile_do_not_break():
    profile = dict(PROFILE)
    profile["proof"] = [{"tags": [], "text": "Сделал {фигурные} скобки в тексте."}]
    template = letters.load_template(ROOT)
    text = letters.build(VACANCY, profile, [], template)
    assert "{фигурные}" in text

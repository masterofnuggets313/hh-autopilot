"""Фильтры: деньги на руки, холодный поиск, отсев."""

from hhjob import filters


def test_net_from_gross():
    v = {"salary_from": 100000, "gross": True}
    assert filters.net_salary(v) == 87000


def test_net_from_net():
    v = {"salary_from": 100000, "gross": False}
    assert filters.net_salary(v) == 100000


def test_net_none_without_salary():
    assert filters.net_salary({"gross": True}) is None


def test_money_label_shows_net():
    v = {"salary_from": 120000, "gross": True}
    label = filters.money_label(v)
    assert "до вычета" in label
    assert "104400" in label


def test_cold_markers():
    text = "Работа с готовой базой, холодные звонки и обзвон клиентов."
    assert filters.cold_hits(text)


def test_no_cold_on_clean_text():
    text = "Ведение действующих клиентов, продление подписок, допродажи."
    assert not filters.cold_hits(text)


def test_gph_markers():
    assert filters.gph_hits("Оформление по ГПХ, испытательный срок 3 месяца.")


def test_pick_drops_cold_and_low_salary():
    items = [
        {"id": "1", "name": "Аккаунт-менеджер", "text": "действующие клиенты",
         "salary_from": 120000, "gross": False},
        {"id": "2", "name": "Менеджер", "text": "холодные звонки", "salary_from": 150000,
         "gross": False},
        {"id": "3", "name": "Менеджер", "text": "действующие клиенты", "salary_from": 70000,
         "gross": True},
    ]
    picked = filters.pick(items, salary_min=100000)
    assert [v["id"] for v in picked] == ["1"]


def test_score_prefers_title_matches():
    tags = {"sales": ["продаж"]}
    in_title = {"name": "Руководитель отдела продаж", "text": ""}
    in_text = {"name": "Менеджер", "text": "работа с продажами"}
    assert filters.score(in_title, tags) > filters.score(in_text, tags)

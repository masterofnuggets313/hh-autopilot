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


# --- отрицания: «без холодных звонков» это плюс, а не блокер ---


def test_negation_before_marker():
    text = "Работа с входящими заявками, без холодного поиска"
    assert filters.cold_hits(text) == []
    assert filters.cold_negated(text)


def test_negation_after_marker():
    assert filters.cold_hits("Холодного поиска клиентов нет.") == []
    assert filters.cold_hits("Холодных звонков нет, работа с теплыми лидами.") == []


def test_negation_just_before_marker():
    assert filters.gph_hits("Оформление строго по ТК РФ, не ГПХ и не самозанятость.") == []


def test_negation_does_not_hide_real_blocker_in_next_clause():
    """«нет холодных звонков, но есть обзвон» это все равно холодные звонки."""
    assert filters.cold_hits("Нет холодных звонков, но есть обзвон базы.")


def test_not_only_is_not_negation():
    assert filters.cold_hits("Не только холодные звонки, но и работа с базой.")


def test_plus_markers_are_reported():
    text = "Только входящие заявки, без холодных звонков, теплая база."
    assert filters.plus_hits(text)


def test_requirements_block_stops_at_next_heading():
    text = (
        "Обязанности:\nведение клиентов\n"
        "Будет плюсом:\nопыт холодных звонков\n"
    )
    block = filters.requirements_block(text)
    assert "ведение клиентов" in block
    assert "опыт холодных звонков" not in block


def test_requirements_block_without_headings_returns_all():
    text = "Просто текст без заголовков про холодные звонки"
    assert filters.requirements_block(text) == text


def test_scope_requirements_ignores_company_story():
    items = [{
        "id": "1", "name": "Менеджер", "salary_from": 120000, "gross": False,
        "text": "Обязанности:\nработа с входящими\nО компании:\nвыросли из холодных звонков\n",
    }]
    assert filters.pick(items, scope="requirements")
    assert not filters.pick(items, scope="all")

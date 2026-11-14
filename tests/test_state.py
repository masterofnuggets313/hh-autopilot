"""Память между запусками: дубли, блокировки, очередь отложенных."""

from datetime import datetime, timedelta

from hhjob import apply as apply_mod
from hhjob import state


def test_title_key_ignores_word_order_and_punctuation():
    a = state.title_key("Менеджер по продажам (B2B)")
    b = state.title_key("продажам менеджер B2B")
    assert a == b


def test_title_key_keeps_extra_words_apart():
    """Один работодатель с офисами в двух городах это не перепост."""
    a = state.title_key("Инженер Москва")
    b = state.title_key("Инженер Берлин")
    assert a != b


def test_already_sent_by_id():
    data = {"sent": {"123": {"at": "2026-11-14T10:00:00"}}, "keys": {}}
    assert state.already_sent(data, "123")


def test_already_sent_by_company_and_title():
    """Перепост получает новый id, но компания и название те же."""
    data = {"sent": {}, "keys": {}}
    state.mark(data, "123", employer="Контур", name="Менеджер по продажам")
    assert state.already_sent(data, "999", "Контур", "Менеджер по продажам")
    assert not state.already_sent(data, "999", "Контур", "Директор по продажам")


def test_block_doubles_pause_for_a_week():
    data = {}
    assert state.pause_for(data, 4) == 4
    state.block(data, "captcha")
    assert state.pause_for(data, 4) == 8


def test_expired_block_stops_doubling():
    data = {"block": {"until": (datetime.now() - timedelta(days=1)).isoformat()}}
    assert state.blocked_until(data) is None
    assert state.pause_for(data, 4) == 4


def test_postponed_queue_roundtrip():
    data = {}
    assert state.postponed(data) == []
    state.set_postponed(data, [1, "2"])
    assert state.postponed(data) == ["1", "2"]
    state.clear_postponed(data)
    assert state.postponed(data) == []


def test_last_run_days_none_before_first_run():
    assert state.last_run_days({}) is None
    data = {}
    state.log_run(data, sent=1)
    assert state.last_run_days(data) is not None


def test_daily_limit_moves_rest_to_queue(tmp_path, monkeypatch):
    calls = []

    def fake_apply(api, resume_id, vacancy_id, letter, delay=0.0):
        calls.append(vacancy_id)

    monkeypatch.setattr(apply_mod.hh, "apply", fake_apply)
    ledger = {}
    ready = [
        {"vacancy": {"id": str(i), "employer": "A", "name": f"Вакансия {i}"}, "letter": "текст"}
        for i in range(1, 4)
    ]
    sent, failed = apply_mod.send(
        None, ready, ledger, tmp_path,
        resume_for={}, default_resume="r1", pause=0, per_day=1,
    )
    assert len(sent) == 1
    assert calls == ["1"]
    assert state.postponed(ledger) == ["2", "3"]
    assert any("лимит" in why for _, why in failed)


def test_captcha_stops_and_keeps_rest(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("captcha required")

    monkeypatch.setattr(apply_mod.hh, "apply", boom)
    ledger = {}
    ready = [
        {"vacancy": {"id": str(i), "employer": "A", "name": f"Вакансия {i}"}, "letter": "текст"}
        for i in range(1, 3)
    ]
    sent, failed = apply_mod.send(
        None, ready, ledger, tmp_path,
        resume_for={}, default_resume="r1", pause=0, per_day=10,
    )
    assert sent == []
    assert state.blocked_until(ledger) is not None
    assert state.postponed(ledger) == ["1", "2"]

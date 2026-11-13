"""Тонкая обертка над hh_applicant_tool.

Пакет hh-applicant-tool отвечает за OAuth, хранение токена и подпись запросов.
Мы не копируем его код, а зависим от него. Обертка нужна по двум причинам:
классы в разных версиях называются по-разному, и хочется один нормальный API.
"""

from __future__ import annotations

import html
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable


def client(config_dir: Path | str | None = None, profile_id: str | None = None):
    """Возвращает api-клиент hh. Токен уже должен быть получен через hh-applicant-tool auth."""
    if config_dir:
        os.environ["CONFIG_DIR"] = str(config_dir)
    if profile_id:
        os.environ["HH_PROFILE_ID"] = profile_id
    argv_backup = sys.argv[:]
    sys.argv = ["hh-applicant-tool", "-d", "0.5", "whoami"]
    try:
        from hh_applicant_tool.tool import HHApplicantTool
    finally:
        sys.argv = argv_backup
    return HHApplicantTool().api_client


def clean_html(raw: str) -> str:
    """Текст без скриптов, стилей и тегов. Брендированные описания иначе не читаются."""
    if not raw:
        return ""
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    raw = re.sub(r"</(p|li|div|h\d)>", "\n", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = raw.replace("\xa0", " ")
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def resumes(api) -> list[dict[str, Any]]:
    res = api.get("/resumes/mine")
    return list(res.get("items") or [])


def search(
    api,
    query: str,
    *,
    area: int = 113,
    schedule: str = "remote",
    salary_from: int = 0,
    only_with_salary: bool = True,
    per_page: int = 100,
    max_pages: int = 5,
) -> list[dict[str, Any]]:
    """Поиск вакансий. Возвращает нормализованные словари, без дублей по id."""
    params: dict[str, Any] = {
        "text": query,
        "area": area,
        "per_page": per_page,
        "order_by": "relevance",
    }
    if schedule:
        params["schedule"] = schedule
    if only_with_salary:
        params["only_with_salary"] = "true"
    if salary_from:
        params["salary"] = salary_from

    out: dict[str, dict[str, Any]] = {}
    page = 0
    while page < max_pages:
        res = api.get("/vacancies", {**params, "page": page})
        items = res.get("items") or []
        if not items:
            break
        for v in items:
            out[str(v["id"])] = normalize(v)
        if page >= int(res.get("pages", 1)) - 1:
            break
        page += 1
    return list(out.values())


def normalize(v: dict[str, Any]) -> dict[str, Any]:
    sal = v.get("salary") or {}
    emp = v.get("employer") or {}
    return {
        "id": str(v.get("id")),
        "name": v.get("name") or "",
        "employer": emp.get("name") or "",
        "employer_id": str(emp.get("id") or ""),
        "area": (v.get("area") or {}).get("name") or "",
        "salary_from": sal.get("from"),
        "salary_to": sal.get("to"),
        "currency": sal.get("currency"),
        "gross": bool(sal.get("gross")),
        "experience": (v.get("experience") or {}).get("name") or "",
        "schedule": (v.get("schedule") or {}).get("name") or "",
        "published_at": v.get("published_at") or "",
        "url": v.get("alternate_url") or f"https://hh.ru/vacancy/{v.get('id')}",
    }


def vacancy(api, vacancy_id: str) -> dict[str, Any]:
    """Полная вакансия с текстом. Учитывает брендированное описание."""
    raw = api.get(f"/vacancies/{vacancy_id}")
    text = clean_html(raw.get("description") or "")
    branded = raw.get("branded_description") or ""
    if branded:
        branded_text = clean_html(branded)
        if len(branded_text) > len(text):
            text = branded_text
    data = normalize(raw)
    data.update(
        {
            "text": text,
            "archived": bool(raw.get("archived")),
            "letter_required": bool(raw.get("response_letter_required")),
            "employer_trusted": bool((raw.get("employer") or {}).get("trusted")),
            "employer_accredited": bool(
                (raw.get("employer") or {}).get("accredited_it_employer")
            ),
        }
    )
    return data


def negotiations(api) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    page = 0
    while True:
        res = api.get("/negotiations", {"per_page": 100, "page": page})
        out.extend(res.get("items") or [])
        if page >= int(res.get("pages", 1)) - 1:
            break
        page += 1
    return out


def negotiation(api, neg_id: str) -> dict[str, Any]:
    return api.get(f"/negotiations/{neg_id}")


def messages(api, neg_id: str) -> list[dict[str, Any]]:
    res = api.get(f"/negotiations/{neg_id}/messages")
    return list(res.get("items") or [])


def apply(api, resume_id: str, vacancy_id: str, message: str, delay: float = 4.0):
    return api.post(
        "/negotiations",
        {"resume_id": resume_id, "vacancy_id": int(vacancy_id), "message": message},
        delay=delay,
    )


def chat_send(chat_id: int | str, text: str):
    """Ответ в чат переговоров. Класс Operation в разных версиях лежит по разным путям."""
    from hh_applicant_tool.tool import HHApplicantTool

    op = None
    try:
        from hh_applicant_tool.operations.reply_chats import Operation  # type: ignore

        op = Operation()
        op.tool = HHApplicantTool()
    except Exception:  # noqa: BLE001
        raise RuntimeError(
            "не удалось загрузить Operation из hh_applicant_tool, проверьте версию пакета"
        )
    return op.send_chat_message(int(chat_id), text, refer_url=op.chat_referer(int(chat_id)))


def iter_ids(items: Iterable[dict[str, Any]]) -> list[str]:
    return [str(i.get("id")) for i in items if i.get("id")]

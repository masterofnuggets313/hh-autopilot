"""Командная строка hhjob."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import __version__, apply as apply_mod, config as cfg_mod, filters, hh, letters
from . import report as report_mod
from . import state as state_mod
from . import style as style_mod


def _load(args) -> cfg_mod.Config:
    return cfg_mod.load(Path(args.root).resolve())


def _dump(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _access_id(resume: dict) -> str:
    """Поле access бывает и словарем, и вложенным в type."""
    access = resume.get("access") or {}
    if isinstance(access.get("type"), dict):
        return str((access["type"] or {}).get("id") or "")
    return str(access.get("id") or "")


def cmd_doctor(args) -> int:
    cfg = _load(args)
    ok = True
    print(f"hhjob {__version__}")
    print(f"каталог: {cfg.root}")
    print(f"конфиг hh: {cfg.config_dir or 'по умолчанию у hh-applicant-tool'}")

    try:
        api = hh.client(cfg.config_dir, cfg.profile_id)
        me = api.get("/me")
        print(f"авторизация: да, {me.get('first_name')} {me.get('last_name')}")
    except Exception as exc:  # noqa: BLE001
        print(f"авторизация: НЕТ ({type(exc).__name__}). Запустите: hh-applicant-tool auth")
        return 1

    try:
        rs = hh.resumes(api)
        visible = [r for r in rs if _access_id(r) == "clients"]
        print(f"резюме: {len(rs)}, видимых работодателям: {len(visible)}")
        for r in rs:
            mark = "ok" if _access_id(r) == "clients" else "скрыто"
            print(f"  {r['id'][:12]} {mark:6} {r.get('title')}")
    except Exception as exc:  # noqa: BLE001
        print(f"резюме: ошибка {type(exc).__name__}")
        ok = False

    if not cfg.tracks:
        print("треки: не настроены, скопируйте config.example.toml в config.toml")
        ok = False
    else:
        for name, t in cfg.tracks.items():
            print(f"трек {name}: резюме {t.resume_id[:12]}, запросов {len(t.queries)}")

    if not cfg.profile.get("proof"):
        print("профиль: нет блоков proof, письма будут пустыми")
        ok = False
    else:
        print(f"профиль: блоков proof {len(cfg.profile['proof'])}")

    return 0 if ok else 1


def cmd_search(args) -> int:
    cfg = _load(args)
    api = hh.client(cfg.config_dir, cfg.profile_id)
    tracks = [args.track] if args.track else list(cfg.tracks)
    if not tracks:
        print("нет треков в config.toml")
        return 1

    collected: dict[str, dict] = {}
    for name in tracks:
        track = cfg.tracks[name]
        queries = [args.query] if args.query else track.queries
        for q in queries:
            try:
                found = hh.search(
                    api,
                    q,
                    area=cfg.area,
                    schedule=cfg.schedule,
                    salary_from=args.salary or track.salary_from,
                    only_with_salary=cfg.only_with_salary,
                    max_pages=args.pages,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  {name} / {q}: ошибка {type(exc).__name__}")
                continue
            print(f"  {name} / {q}: {len(found)}")
            for v in found:
                v["track"] = name
                collected.setdefault(v["id"], v)

    items = list(collected.values())
    picked = filters.pick(
        items,
        tags=cfg.tags,
        salary_min=args.salary or 0,
        cold_patterns=cfg.cold_markers or None,
        gph_patterns=cfg.gph_markers or None,
        limit=args.limit,
    )
    out = _dump(cfg.data_dir / f"candidates-{date.today().isoformat()}.json", picked)
    print(f"\nсобрано {len(items)}, после фильтров {len(picked)}")
    for v in picked[:15]:
        print(f"  {v['score']:>2} | {filters.money_label(v):32} | {v['employer'][:24]:24} | {v['name'][:40]}")
    print(f"\nфайл: {out}")
    return 0


def cmd_describe(args) -> int:
    cfg = _load(args)
    api = hh.client(cfg.config_dir, cfg.profile_id)
    src = Path(args.file) if args.file else cfg.data_dir / f"candidates-{date.today().isoformat()}.json"
    items = json.loads(src.read_text(encoding="utf-8"))
    limit = args.limit or 10
    out = []
    for v in items[:limit]:
        full = hh.vacancy(api, v["id"])
        full["track"] = v.get("track")
        full["score"] = v.get("score")
        full["cold"] = filters.cold_hits(full.get("text", ""), cfg.cold_markers or None)
        out.append(full)
        print(f"  {v['id']} | {full['employer'][:26]:26} | {len(full['text'])} симв. | {full['name'][:38]}")
    path = _dump(cfg.data_dir / "described.json", out)
    print(f"\nописаний: {len(out)}, файл: {path}")
    return 0


def cmd_letters(args) -> int:
    cfg = _load(args)
    src = cfg.data_dir / "described.json"
    if not src.exists():
        print("нет data/described.json, сначала hhjob describe")
        return 1
    items = json.loads(src.read_text(encoding="utf-8"))
    template = letters.load_template(cfg.root, args.family or "base")
    out = []
    for v in items:
        tags = filters.tags_for(v, cfg.tags)
        text = letters.build(v, cfg.profile, tags, template, max_proof=args.proof)
        problems = letters.check(text)
        out.append({"id": v["id"], "employer": v["employer"], "name": v["name"],
                    "track": v.get("track"), "tags": tags, "letter": text,
                    "problems": problems})
        mark = "ok" if not problems else "ПРОБЛЕМА: " + "; ".join(problems)
        print(f"  {v['id']} | {len(text):>4} симв. | {mark}")
    path = _dump(cfg.data_dir / "letters.json", out)
    print(f"\nфайл: {path}")
    return 0 if all(not i["problems"] for i in out) else 2


def cmd_apply(args) -> int:
    cfg = _load(args)
    src = cfg.data_dir / "letters.json"
    if not src.exists():
        print("нет data/letters.json, сначала hhjob letters")
        return 1
    api = hh.client(cfg.config_dir, cfg.profile_id)
    ledger = state_mod.load(cfg.root)

    items = json.loads(src.read_text(encoding="utf-8"))
    ready, skipped = [], []
    for item in items:
        if item["problems"]:
            skipped.append((item["id"], "; ".join(item["problems"])))
            continue
        if state_mod.already_sent(ledger, item["id"]):
            skipped.append((item["id"], "уже откликались"))
            continue
        try:
            full = hh.vacancy(api, item["id"])
        except Exception as exc:  # noqa: BLE001
            skipped.append((item["id"], f"вакансия не открылась: {exc}"))
            continue
        if full.get("archived"):
            skipped.append((item["id"], "в архиве"))
            continue
        ready.append({"vacancy": full, "letter": item["letter"], "tags": item["tags"],
                      "track": item.get("track")})

    if args.track:
        ready = [r for r in ready if r.get("track") == args.track]
    if args.limit:
        ready = ready[: args.limit]
    print(f"к отправке {len(ready)}, пропущено {len(skipped)}")
    for vid, why in skipped:
        print(f"  пропуск {vid}: {why}")

    resume_for = {}
    for item in ready:
        track = cfg.tracks.get(item.get("track") or "")
        if track:
            resume_for[str(item["vacancy"]["id"])] = track.resume_id
    if args.resume:
        default_resume = args.resume
    else:
        default_resume = next((t.resume_id for t in cfg.tracks.values()), "")

    sent, failed = apply_mod.send(
        api, ready, ledger, cfg.root,
        resume_for=resume_for, default_resume=default_resume,
        pause=cfg.limits.pause_seconds, dry=args.dry, per_day=cfg.limits.per_day,
    )
    state_mod.log_run(ledger, sent=len(sent), failed=len(failed), dry=bool(args.dry))
    state_mod.save(cfg.root, ledger)

    print(f"\nотправлено {len(sent)}, ошибок {len(failed)}")
    for f in failed:
        print(f"  {f[0]}: {f[1]}")
    return 0


def cmd_chats(args) -> int:
    cfg = _load(args)
    api = hh.client(cfg.config_dir, cfg.profile_id)
    from datetime import datetime, timedelta

    since = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    waiting = []
    checked = 0
    for n in hh.negotiations(api):
        if (n.get("state") or {}).get("id") != "response":
            continue
        if (n.get("updated_at") or "")[:10] < since:
            continue
        if checked >= args.limit:
            break
        checked += 1
        neg_id = str(n.get("id"))
        try:
            msgs = hh.messages(api, neg_id)
        except Exception:  # noqa: BLE001
            continue
        if not msgs:
            continue
        last = msgs[-1]
        author = (last.get("author") or {}).get("participant_type")
        if author == "applicant":
            continue
        waiting.append(
            {
                "negotiation": neg_id,
                "chat_id": n.get("chat_id"),
                "employer": ((n.get("vacancy") or {}).get("employer") or {}).get("name"),
                "vacancy": (n.get("vacancy") or {}).get("name"),
                "last_text": (last.get("text") or "")[:500],
                "at": last.get("creationTime") or last.get("created_at"),
            }
        )
    print(f"проверено чатов: {checked}, ждут ответа: {len(waiting)}")
    for w in waiting:
        print(f"  {w['negotiation']} | {w['employer']} | {w['last_text'][:80]}")
    _dump(cfg.data_dir / "waiting.json", waiting)

    if args.reply:
        replies = json.loads(Path(args.reply).read_text(encoding="utf-8"))
        for chat_id, text in replies.items():
            print(f"  -> {chat_id}: {text[:60]}")
            if not args.dry:
                hh.chat_send(chat_id, text)
    return 0


def cmd_report(args) -> int:
    cfg = _load(args)
    api = hh.client(cfg.config_dir, cfg.profile_id)
    items = report_mod.rows(api)
    s = report_mod.summary(items)
    print(f"всего {s['total']}, ждут {s['waiting']}, отказы {s['discards']}, собесы {s['interviews']}")
    out = Path(args.out) if args.out else cfg.data_dir / f"report-{date.today().isoformat()}.xlsx"
    path = report_mod.to_xlsx(items, out) if out.suffix == ".xlsx" else report_mod.to_csv(items, out)
    print(f"файл: {path}")
    return 0


def cmd_lint(args) -> int:
    bad = 0
    for name in args.files:
        text = Path(name).read_text(encoding="utf-8")
        problems = style_mod.lint(text)
        print(f"{name}: {len(problems)} замечаний")
        for rule, frag, fix in problems[:20]:
            print(f"  [{rule}] {frag} -> {fix}")
        bad += len(problems)
    return 0 if bad == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hhjob", description="Поиск работы на hh.ru через агента")
    p.add_argument("--root", default=".", help="каталог с config.toml")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="проверить установку и доступы").set_defaults(func=cmd_doctor)

    s = sub.add_parser("search", help="собрать и отфильтровать вакансии")
    s.add_argument("--track")
    s.add_argument("--query")
    s.add_argument("--salary", type=int, default=0)
    s.add_argument("--limit", type=int, default=60)
    s.add_argument("--pages", type=int, default=3)
    s.set_defaults(func=cmd_search)

    d = sub.add_parser("describe", help="скачать полные описания")
    d.add_argument("--file")
    d.add_argument("--limit", type=int, default=10)
    d.set_defaults(func=cmd_describe)

    l = sub.add_parser("letters", help="собрать письма")
    l.add_argument("--family", default="base")
    l.add_argument("--proof", type=int, default=3)
    l.set_defaults(func=cmd_letters)

    a = sub.add_parser("apply", help="отправить отклики")
    a.add_argument("--dry", action="store_true")
    a.add_argument("--limit", type=int, default=0)
    a.add_argument("--resume")
    a.add_argument("--track")
    a.set_defaults(func=cmd_apply)

    c = sub.add_parser("chats", help="кто ждет ответа")
    c.add_argument("--reply", help="json вида {chat_id: текст}")
    c.add_argument("--days", type=int, default=3, help="смотреть переговоры за N дней")
    c.add_argument("--limit", type=int, default=40, help="сколько чатов проверить")
    c.add_argument("--dry", action="store_true")
    c.set_defaults(func=cmd_chats)

    r = sub.add_parser("report", help="отчет по воронке")
    r.add_argument("--out")
    r.set_defaults(func=cmd_report)

    t = sub.add_parser("lint", help="проверить текст на стиль")
    t.add_argument("files", nargs="+")
    t.set_defaults(func=cmd_lint)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

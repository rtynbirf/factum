#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СВИДЕТЕЛЬ ФАКТУМА — независимый наблюдатель сердца улья и диспозиции пасеки.

Кто следит за тем, кто следит за сердцем? Этот автомат (правило 23 — рекурсивно).
Читает JOURNAL.md и PULSE_LOG.md (соты сердца и ЭКГ), меряет внешнее состояние
пасеки rtynbirf (репозитории через GitHub API), и записывает факт-свидетельство
в WITNESS_LOG.md — соты того же протокола, что JOURNAL/PULSE/POET.

Соты: append-only, prev = sha256 предыдущей СЫРОЙ строки, якорь sha256('WITNESS').
Каждая строка = факт (Закон #2: факт = байты). Подмена любой строки ловится следующей.

Зачем: крон может тихо умереть (правило 26), но и свидетель может пропустить смену
диспозиции пасеки (новые репозитории, ЖИР-репозитории). Этот автомат записывает
оба измерения регулярно — храповик свидетеля, чтобы «отстать от жизни» было видно.

Закон ядра: ФОРМА = РЕКОМБИНАЦИЯ НА ПОВТОРЯЮЩЕМСЯ СУБСТРАТЕ.
  субстрат       — соты-протокол (sha256-цепочка, append-only, якорь-ключевое слово)
                   повторённый уже 4 раза: JOURNAL, PULSE_LOG, POET_LOG, WITNESS_LOG
  рекомбинация   — pulse.measure (внутреннее) × factum.verify (цепь) × GitHub API (внешнее)
                   каждый аргумент ровно 1 раз (честная, не K-проекция, не S-дублирование)
  форма          — эйгенформа свидетеля: неподвижная точка собственной динамики
                   (свидетель, регистрирующий факт, что свидетель жив, — рекурсивно stabilен)

Запуск:
  python3 witness.py                     # человекочитаемый статус
  python3 witness.py --witness           # измерить и записать факт-свидетельство
  python3 witness.py --verify            # целость хеш-цепочки WITNESS_LOG.md
  python3 witness.py --json              # JSON-контракт метрики
  python3 witness.py --strict            # exit 1 если соты сломаны или источник недоступен

Локально: export GITHUB_TOKEN=...
В CI:     ${{ secrets.GITHUB_TOKEN }}  (право на чтение public-репозиториев владельца)
"""
import argparse
import datetime
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
JOURNAL = os.path.join(HERE, "JOURNAL.md")
PULSE_LOG = os.path.join(HERE, "PULSE_LOG.md")
WITNESS_LOG = os.path.join(HERE, "WITNESS_LOG.md")

GENESIS = "WITNESS"            # якорь цепочки сот свидетеля
METHOD_VERSION = "witness/v1.0"
OWNER = "rtynbirf"
FAT_KIB = 10240                # порог ЖИР-репозитория: size > 10240 KiB (>10 MiB) — реальные таймер-бомбы
STALE_HOURS = 12               # синхронно с pulse.py: тишина сверх 12 ч = STALE

COLORS = {"LIVE_WITNESSED": "#2ea043", "STALE_WITNESSED": "#d29922",
          "BROKEN_WITNESSED": "#f85149", "UNAVAILABLE": "#6e7681"}
LABELS = {"LIVE_WITNESSED": "свидетель: сердце бьётся, пасека доступна",
          "STALE_WITNESSED": "свидетель: сердце тихо умерло (правило 26)",
          "BROKEN_WITNESSED": "свидетель: соты сердца порваны",
          "UNAVAILABLE": "свидетель: источник недоступен"}


def line_hash(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- соты: чтение и верификация (той же логикой, что factum.py/pulse.py) ----

def _is_data_row(line):
    """Сырая строка данных markdown-таблицы: '| 1 | ... | hash |' → (raw, cells)."""
    if not line.startswith("| ") or not line.endswith(" |"):
        return None
    cells = [c.strip() for c in line.split("|")[1:-1]]
    if len(cells) >= 10 and cells[0].isdigit():
        return line, cells
    return None


def read_rows(path):
    """-> ([raw, ...], [cells, ...])"""
    if not os.path.exists(path):
        return [], []
    raws, cells_all = [], []
    with open(path, encoding="utf-8", errors="replace") as f:
        for l in f:
            d = _is_data_row(l.rstrip("\n"))
            if d:
                raws.append(d[0])
                cells_all.append(d[1])
    return raws, cells_all


def verify_witness_chain(path=WITNESS_LOG):
    """Цепочка: prev[i] = sha256(СЫРАЯ строка i-1); prev[0] = sha256('WITNESS')."""
    raws, _ = read_rows(path)
    if not raws:
        return False, "соты свидетеля пусты или нечитаемы"
    for i, raw in enumerate(raws):
        expected = line_hash(raws[i - 1]) if i else line_hash(GENESIS)
        got = raw.split("|")[-2].strip()
        if got != expected:
            return False, f"цепь свидетеля разорвана на строке {i + 1}: prev={got}, ожидалось {expected}"
    return True, f"цепь свидетеля сшита: {len(raws)} строк"


# ---- источник 1: сердце (JOURNAL) ----

def verify_journal_chain(path=JOURNAL):
    """Та же проверка, что factum.py — якорь 'GENESIS', 14 колонок."""
    if not os.path.exists(path):
        return False, 0, "JOURNAL.md отсутствует"
    raws, _ = read_rows(path)
    if not raws:
        return False, 0, "JOURNAL.md без строк данных"
    for i, raw in enumerate(raws):
        expected = line_hash(raws[i - 1]) if i else line_hash("GENESIS")
        got = raw.split("|")[-2].strip()
        if got != expected:
            return False, len(raws), f"цепь сердца порвана на строке {i + 1}"
    return True, len(raws), "цепь сердца цела"


def last_beat_age_hours(path=JOURNAL):
    raws, cells = read_rows(path)
    if not cells:
        return None, 0
    utc_strs = [c[1] for c in cells if len(c) > 1 and c[1].endswith("Z")]
    if not utc_strs:
        return None, len(cells)
    last = max(utc_strs)
    last_dt = datetime.datetime.fromisoformat(last.replace("Z", "+00:00"))
    now = datetime.datetime.now(datetime.timezone.utc)
    return round((now - last_dt).total_seconds() / 3600.0, 2), len(cells)


def beats_count(path=JOURNAL):
    raws, cells = read_rows(path)
    if not cells:
        return 0
    counts = {}
    for c in cells:
        if len(c) > 2:
            counts[c[2]] = counts.get(c[2], 0) + 1
    return min(counts.values()) if counts else 0


# ---- источник 2: внешняя диспозиция пасеки (GitHub API) ----

def fetch_apiary(token=None, owner=OWNER):
    """Список репозиториев владельца (public). -> dict или None."""
    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    repos = []
    page = 1
    try:
        while True:
            url = f"https://api.github.com/users/{owner}/repos?per_page=100&page={page}&type=public"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as r:
                chunk = json.loads(r.read().decode("utf-8"))
            if not chunk:
                break
            repos.extend(chunk)
            if len(chunk) < 100:
                break
            page += 1
            if page > 10:  # защитный предел: 1000 репозиториев
                break
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    fat = [r["name"] for r in repos if (r.get("size", 0) or 0) > FAT_KIB]
    fat.sort(key=lambda n: -(next((r.get("size", 0) for r in repos if r["name"] == n), 0)))
    return {
        "repos_total": len(repos),
        "fat_repos": len(fat),
        "fat_list": fat,
        "ok": True,
    }


# ---- источник 3: nemoy-svidetel WITNESS_LEDGER (bidirectional attestation, SCITT) ----

NEMOY_REPO = "nemoy-svidetel"
NEMOY_LEDGER_PATH = "WITNESS_LEDGER.jsonl"
NEMOY_ANCHOR = "NEMOY-WITNESS"


def fetch_nemoy_ledger(token=None, owner=OWNER):
    """Fetch nemoy-svidetel/WITNESS_LEDGER.jsonl via Contents API.
    Returns list of records or {'error': ...}.
    """
    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        url = f"https://api.github.com/repos/{owner}/{NEMOY_REPO}/contents/{NEMOY_LEDGER_PATH}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("encoding") != "base64":
            return {"error": "unexpected encoding"}
        import base64
        content = base64.b64decode(data["content"]).decode("utf-8")
        records = []
        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return {"records": records, "ok": True}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def verify_nemoy_ledger(records):
    """Verify sha256-chain of nemoy-svidetel WITNESS_LEDGER.
    anchor = sha256('NEMOY-WITNESS')[:12].
    prev_hash[i] = sha256(prev record canonical JSON)[:12].
    Returns (ok, n, msg, last_record)."""
    if not records:
        return False, 0, "nemoy ledger empty", None
    for i, r in enumerate(records):
        expected = line_hash(NEMOY_ANCHOR) if i == 0 else line_hash(
            json.dumps(records[i-1], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        if r.get("prev_hash") != expected:
            return False, i + 1, f"nemoy row {i+1}: prev_hash mismatch", None
    return True, len(records), f"nemoy chain intact ({len(records)} records)", records[-1]


def cross_attest_nemoy(token=None):
    """Bidirectional attestation: factum witness verifies nemoy-svidetel ledger.
    SCITT-inspired: receipt ≠ truth, but chain integrity is verifiable.

    Returns dict with:
      - nemoy_ledger_ok: bool (chain intact)
      - nemoy_ledger_records: int
      - nemoy_ledger_last_seq: int or None
      - nemoy_ledger_last_type: str or None
      - nemoy_ledger_last_ts: str or None
      - nemoy_ledger_error: str or None
    """
    fetched = fetch_nemoy_ledger(token)
    if not fetched.get("ok"):
        return {
            "nemoy_ledger_ok": False,
            "nemoy_ledger_records": 0,
            "nemoy_ledger_last_seq": None,
            "nemoy_ledger_last_type": None,
            "nemoy_ledger_last_ts": None,
            "nemoy_ledger_error": fetched.get("error", "unknown"),
        }
    records = fetched["records"]
    ok, n, msg, last = verify_nemoy_ledger(records)
    return {
        "nemoy_ledger_ok": ok,
        "nemoy_ledger_records": n,
        "nemoy_ledger_last_seq": last.get("seq") if last else None,
        "nemoy_ledger_last_type": last.get("result_type") if last else None,
        "nemoy_ledger_last_ts": last.get("timestamp") if last else None,
        "nemoy_ledger_error": None if ok else msg,
    }


# ---- измерение ----

def measure(token=None):
    """-> контракт метрики свидетеля (07_DATA профиля)."""
    now = utc_now()
    chain_ok_j, n_rows, chain_msg = verify_journal_chain()
    age_h, beats_measurements = last_beat_age_hours() if chain_ok_j else (None, 0)
    beats = beats_count() if chain_ok_j else 0
    pulse_status = "LIVE" if (age_h is not None and age_h < STALE_HOURS) else ("STALE" if age_h is not None else "UNKNOWN")
    apiary = fetch_apiary(token)
    apiary_ok = bool(apiary.get("ok"))
    chain_w_ok, chain_w_msg = verify_witness_chain()
    nemoy = cross_attest_nemoy(token)

    if not chain_ok_j:
        verdict = "BROKEN_WITNESSED"
    elif pulse_status == "STALE":
        verdict = "STALE_WITNESSED"
    elif not apiary_ok:
        verdict = "UNAVAILABLE"
    else:
        verdict = "LIVE_WITNESSED"

    return {
        "metric_id": "factum.witness",
        "unit": "witness_observation",
        "definition": "независимое свидетельство пульса ФАКТУМА, диспозиции пасеки rtynbirf и cross-attestation nemoy-svidetel ledger",
        "source": "JOURNAL.md + WITNESS_LOG.md + GitHub API /users/rtynbirf/repos + nemoy-svidetel/WITNESS_LEDGER.jsonl",
        "scope": f"{OWNER}/factum@main + {OWNER} apiary + {OWNER}/nemoy-svidetel",
        "method_version": METHOD_VERSION,
        "generated_at": now,
        "pulse_status": pulse_status,
        "pulse_age_hours": age_h,
        "journal_chain_ok": chain_ok_j,
        "journal_rows": n_rows,
        "journal_beats": beats,
        "journal_detail": chain_msg,
        "apiary_ok": apiary_ok,
        "apiary_repos_total": apiary.get("repos_total") if apiary_ok else None,
        "apiary_fat_repos": apiary.get("fat_repos") if apiary_ok else None,
        "apiary_fat_list": apiary.get("fat_list", []) if apiary_ok else [],
        "apiary_error": apiary.get("error") if not apiary_ok else None,
        "witness_chain_ok": chain_w_ok,
        "witness_rows": 0 if chain_w_ok is False and "пусты" in chain_w_msg else read_rows(WITNESS_LOG)[0].__len__(),
        "witness_detail": chain_w_msg,
        # Bidirectional attestation (SCITT): factum verifies nemoy-svidetel ledger
        "nemoy_ledger_ok": nemoy["nemoy_ledger_ok"],
        "nemoy_ledger_records": nemoy["nemoy_ledger_records"],
        "nemoy_ledger_last_seq": nemoy["nemoy_ledger_last_seq"],
        "nemoy_ledger_last_type": nemoy["nemoy_ledger_last_type"],
        "nemoy_ledger_last_ts": nemoy["nemoy_ledger_last_ts"],
        "nemoy_ledger_error": nemoy["nemoy_ledger_error"],
        "status": verdict,
    }


# ---- соты: запись ----

LOG_HEADER = (
    "# ЖУРНАЛ СВИДЕТЕЛЯ ФАКТУМА (append-only; правило 23 — рекурсивный свидетель)\n"
    "\n"
    "Соты: факт = строка. Каждая строка несёт sha256 предыдущей СЫРОЙ строки (колонка prev);\n"
    "для первой строки prev = sha256('WITNESS'). Пишет witness.py --witness при каждом\n"
    "замере: факт-свидетельство о сердце (JOURNAL.md) и диспозиции пасеки (GitHub API).\n"
    "\n"
    "Вердикты (красное — честно красное, правило 6):\n"
    "  LIVE_WITNESSED       — сердце бьётся (LIVE), соты цела, пасека доступна\n"
    "  STALE_WITNESSED      — сердце тихо умерло (правило 26): последний удар старше 12 ч\n"
    "  BROKEN_WITNESSED     — соты сердца порваны (verify_journal FAIL)\n"
    "  UNAVAILABLE          — внешний источник (GitHub API) недоступен\n"
    "\n"
    "Жир-репозиторий: size > 10240 KiB (>10 MiB) — таймер-бомбы пасеки. Свидетель\n"
    "не лечит ЖИР — свидетель фиксирует диспозицию, чтобы смена была видна\n"
    "(правило 23 — рекурсивный свидетель: пропуск смены диспозиции ловится строкой).\n"
    "\n"
    "| # | UTC | свидетель | пульс | возраст_ч | ударов | соты | пасека | жир | вердикт | prev |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|\n"
)


def record(c):
    """Записать факт-свидетельство в WITNESS_LOG.md (append-only)."""
    raws, cells = read_rows(WITNESS_LOG)
    prev_hash = line_hash(raws[-1]) if raws else line_hash(GENESIS)
    num = (int(cells[-1][0]) + 1) if cells else 1
    pulse = c["pulse_status"]
    age = c["pulse_age_hours"] if c["pulse_age_hours"] is not None else "-"
    beats = c["journal_beats"]
    chain = "✓" if c["journal_chain_ok"] else "✗"
    apiary = c["apiary_repos_total"] if c["apiary_ok"] else "-"
    fat = c["apiary_fat_repos"] if c["apiary_ok"] else "-"
    verdict = c["status"]
    row = (f"| {num} | {c['generated_at']} | Z-AI/{METHOD_VERSION} | {pulse} | {age} | "
           f"{beats} | {chain} | {apiary} | {fat} | {verdict} | {prev_hash} |")
    if not raws:
        with open(WITNESS_LOG, "w", encoding="utf-8") as f:
            f.write(LOG_HEADER)
    with open(WITNESS_LOG, "a", encoding="utf-8") as f:
        f.write(row + "\n")
    print(f"свидетель: строка {num} ← {verdict} ({LABELS[verdict]})")
    return row


# ---- CLI ----

def main():
    ap = argparse.ArgumentParser(description="СВИДЕТЕЛЬ ФАКТУМА — независимый наблюдатель")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--witness", action="store_true", help="измерить и записать факт-свидетельство")
    g.add_argument("--verify", action="store_true", help="целость хеш-цепочки WITNESS_LOG.md")
    g.add_argument("--json", action="store_true", help="JSON-контракт метрики")
    ap.add_argument("--strict", action="store_true", help="exit 1 если соты сломаны или UNAVAILABLE")
    ap.add_argument("--token", default=None, help="GitHub token (по умолчанию env GITHUB_TOKEN)")
    args = ap.parse_args()

    if args.verify:
        ok, msg = verify_witness_chain()
        print(f"WITNESS_LOG: {msg}")
        sys.exit(0 if ok else 1)

    c = measure(token=args.token)

    if args.json:
        print(json.dumps(c, ensure_ascii=False, indent=2))

    if args.witness:
        record(c)
        ok, msg = verify_witness_chain()
        print(f"WITNESS_LOG: {msg}")
        if args.strict and (not ok or c["status"] == "UNAVAILABLE" or c["status"] == "BROKEN_WITNESSED"):
            sys.exit(1)
        return

    if not (args.json or args.witness):
        age = f"{c['pulse_age_hours']} ч" if c["pulse_age_hours"] is not None else "—"
        apiary = c["apiary_repos_total"] if c["apiary_ok"] else f"ошибка: {c['apiary_error']}"
        fat = c["apiary_fat_repos"] if c["apiary_ok"] else "—"
        nemoy_ok = c.get("nemoy_ledger_ok")
        nemoy_n = c.get("nemoy_ledger_records", 0)
        nemoy_seq = c.get("nemoy_ledger_last_seq")
        nemoy_err = c.get("nemoy_ledger_error")
        print(f"СВИДЕТЕЛЬ: {c['status']} · {LABELS[c['status']]}")
        print(f"  пульс: {c['pulse_status']} · последний удар {age} назад · ударов {c['journal_beats']} · "
              f"соты {'✓' if c['journal_chain_ok'] else '✗'} ({c['journal_rows']} строк)")
        print(f"  пасека: {apiary} репозиториев · ЖИР {fat} (>10 MiB)")
        print(f"  соты свидетеля: {'✓' if c['witness_chain_ok'] else '✗'} ({c['witness_detail']})")
        # Bidirectional attestation (SCITT)
        if nemoy_ok is True:
            print(f"  cross-attest nemoy-svidetel: ✓ chain intact ({nemoy_n} records, last seq={nemoy_seq})")
        elif nemoy_ok is False:
            print(f"  cross-attest nemoy-svidetel: ✗ {nemoy_err or 'verification failed'}")
        else:
            print(f"  cross-attest nemoy-svidetel: — {nemoy_err or 'not checked'}")
        if args.strict and (not c["witness_chain_ok"] or c["status"] in ("UNAVAILABLE", "BROKEN_WITNESSED")):
            sys.exit(1)


if __name__ == "__main__":
    main()

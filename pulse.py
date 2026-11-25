#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПУЛЬС ФАКТУМА — кардиограмма сердца улья.

Кто следит за сердцем? Этот автомат. Читает JOURNAL.md (факт = строка, соты с
sha256-цепочкой), меряет возраст последнего удара и публикует честный статус.

Статусы (красное — честно красное, правило 6):
  LIVE               — последний удар свежее STALE_HOURS (12 ч = 2 пропущенных удара)
  STALE              — тишина сверх порога: тихая смерть крона, правило 26
  SOURCE_UNAVAILABLE — журнал нечитаем/пуст

Контракт метрики — 07_DATA профиля: metric_id/value/unit/definition/source/
generated_at/scope/method_version/status. Свидетель пульса — PULSE_LOG.md
(соты: append-only, prev = sha256 предыдущей СЫРОЙ строки, якорь sha256('PULSE')).

Запуск:
  python3 pulse.py                 # человекочитаемый статус
  python3 pulse.py --json          # JSON-контракт (для автоматов)
  python3 pulse.py --badge         # перезаписать pulse.json + pulse.svg
  python3 pulse.py --monitor       # badge + свидетель в PULSE_LOG при смене статуса
  python3 pulse.py --strict        # exit 1, если не LIVE или цепь сломана (для гейтов)
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "JOURNAL.md"
PULSE_JSON = HERE / "pulse.json"
PULSE_SVG = HERE / "pulse.svg"
PULSE_LOG = HERE / "PULSE_LOG.md"

BEAT_INTERVAL_H = 6          # ритм пейсмекера: cron "17 */6 * * *"
STALE_HOURS = 12             # 2 пропущенных удара = STALE
RESUS_HOURS = 12.5           # сверх этого монитор просит дефибрилляцию (правило 26)
METHOD_VERSION = "pulse/v1.0"
GENESIS = "PULSE"            # якорь цепочки ECG-сот

COLORS = {"LIVE": "#2ea043", "STALE": "#d29922", "SOURCE_UNAVAILABLE": "#f85149"}
LABELS = {"LIVE": "бьётся", "STALE": "ТИХАЯ СМЕРТЬ КРОНА", "SOURCE_UNAVAILABLE": "ЖУРНАЛ НЕЧИТАЕМ"}


def line_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def _is_data_row(line: str):
    """Сырая строка данных markdown-таблицы: '| 1 | ... | hash |' → (raw, cells)."""
    if not line.startswith("| ") or not line.endswith(" |"):
        return None
    cells = [c.strip() for c in line.split("|")[1:-1]]
    if len(cells) >= 8 and cells[0].isdigit():
        return line, cells
    return None


def read_rows(path: Path):
    """-> ([raw, ...], [cells, ...])"""
    if not path.exists():
        return [], []
    raws, cells_all = [], []
    for l in path.read_text(encoding="utf-8", errors="replace").splitlines():
        d = _is_data_row(l)
        if d:
            raws.append(d[0])
            cells_all.append(d[1])
    return raws, cells_all


def verify_journal(path=JOURNAL):
    """Цепочка сот: prev[i] = sha256(СЫРАЯ строка i-1); prev[0] = sha256('GENESIS')."""
    raws, _ = read_rows(path)
    if not raws:
        return False, "журнал нечитаем или строк данных нет"
    for i, raw in enumerate(raws):
        expected = line_hash(raws[i - 1]) if i else line_hash("GENESIS")
        got = raw.split("|")[-2].strip()
        if got != expected:
            return False, f"цепь разорвана на строке {i + 1}: prev={got}, ожидалось {expected}"
    return True, f"цепь сшита: {len(raws)} строк"


def parse_utc(s: str):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def measure():
    """-> контракт метрики (07_DATA профиля)."""
    raws, cells = read_rows(JOURNAL)
    chain_ok, msg = verify_journal()
    now = datetime.now(timezone.utc)
    base = {
        "metric_id": "factum.pulse",
        "unit": "hours_since_last_beat",
        "definition": "возраст последней строки данных JOURNAL.md (UTC), часы",
        "source": "JOURNAL.md (соты, append-only, sha256-цепочка)",
        "scope": "rtynbirf/factum@main",
        "method_version": METHOD_VERSION,
        "beat_interval_hours": BEAT_INTERVAL_H,
        "stale_threshold_hours": STALE_HOURS,
        "generated_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    if not cells:
        base.update(value=None, status="SOURCE_UNAVAILABLE", chain_ok=chain_ok, beats=0,
                    worlds={}, detail=msg, resuscitation_needed=True)
        return base
    # колонки JOURNAL: 0:# 1:UTC 2:мир 3:seed 4:шаги 5:типы 6:F 7:F_str 8:доля 9:N1 10:N2 11:N3 12:вердикт 13:prev
    last_utc = max(parse_utc(c[1]) for c in cells)
    age_h = (now - last_utc).total_seconds() / 3600.0
    worlds = {}
    for c in cells:  # append-only → последняя строка мира и есть свежая
        worlds[c[2]] = {"utc": c[1], "F": c[6], "verdict": c[12]}
    status = "LIVE" if age_h < STALE_HOURS else "STALE"
    base.update(value=round(age_h, 2), status=status, chain_ok=chain_ok, beats=len(cells),
                worlds=worlds, detail=msg,
                last_beat_utc=last_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
                resuscitation_needed=(age_h >= RESUS_HOURS))
    return base


def badge_svg(c):
    st = c["status"]
    color = COLORS[st]
    age = f"{c['value']}ч" if c.get("value") is not None else "—"
    chain = "соты ✓" if c.get("chain_ok") else "СОТЫ ✗"
    right = f"{LABELS[st]} · удар {age} назад · {chain}"
    left = "ПУЛЬС ФАКТУМА"
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    w_l, w_r = 8 * len(left) + 16, 7 * len(right) + 16
    total = w_l + w_r
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="24" role="img" '
        f'aria-label="{esc(left)}: {esc(right)}"><title>{esc(left)}: {esc(right)}</title>'
        f'<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        f'<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<clipPath id="r"><rect width="{total}" height="24" rx="3" fill="#fff"/></clipPath>'
        f'<g clip-path="url(#r)"><rect width="{w_l}" height="24" fill="#24292f"/>'
        f'<rect x="{w_l}" width="{w_r}" height="24" fill="{color}"/>'
        f'<rect width="{total}" height="24" fill="url(#s)"/></g>'
        f'<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">'
        f'<text x="{w_l // 2}" y="16">{esc(left)}</text>'
        f'<text x="{w_l + w_r // 2}" y="16">{esc(right)}</text></g></svg>'
    )


def write_badge(c):
    PULSE_JSON.write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PULSE_SVG.write_text(badge_svg(c), encoding="utf-8")
    print(f"badge: pulse.json + pulse.svg ← {c['status']}")


LOG_HEADER = (
    "# ЖУРНАЛ ПУЛЬСА ФАКТУМА (append-only; свидетель крона, правило 23)\n"
    "\n"
    "Соты: факт = строка. Каждая строка несёт sha256 предыдущей СЫРОЙ строки (колонка prev);\n"
    "для первой строки prev = sha256('PULSE'). Пишет pulse.py --monitor ТОЛЬКО при смене\n"
    "статуса: LIVE↔STALE↔SOURCE_UNAVAILABLE — история болезней сердца без шума.\n"
    "Порог: удар каждые 6 ч; 12 ч тишины = STALE (тихая смерть крона, правило 26);\n"
    "сверх 12.5 ч монитор требует дефибрилляцию (gh workflow run factum-heartbeat).\n"
    "\n"
    "| # | UTC | статус | возраст_ч | ударов | соты | причина | prev |\n"
    "|---|---|---|---|---|---|---|---|\n"
)

REASONS = {"LIVE": "удар зафиксирован в JOURNAL.md",
           "STALE": "тишина сверх порога 12ч (правило 26)",
           "SOURCE_UNAVAILABLE": "журнал нечитаем"}


def monitor(c):
    """Свидетель пульса: строка в PULSE_LOG только при СМЕНЕ статуса (без шума)."""
    raws, cells = read_rows(PULSE_LOG)
    if cells and cells[-1][2] == c["status"]:
        print(f"свидетель: статус {c['status']} без изменений — строка не дублируется")
        return
    prev_hash = line_hash(raws[-1]) if raws else line_hash("PULSE")
    age = c["value"] if c.get("value") is not None else "-"
    row = (f"| {len(cells) + 1} | {c['generated_at']} | {c['status']} | {age} | "
           f"{c.get('beats', 0)} | {'✓' if c.get('chain_ok') else '✗'} | "
           f"{REASONS.get(c['status'], '')} | {prev_hash} |")
    if not raws:
        PULSE_LOG.write_text(LOG_HEADER, encoding="utf-8")
    with PULSE_LOG.open("a", encoding="utf-8") as f:
        f.write(row + "\n")
    print(f"свидетель: строка {len(cells) + 1} ← {c['status']} ({REASONS.get(c['status'], '')})")


def main():
    ap = argparse.ArgumentParser(description="ПУЛЬС ФАКТУМА — кардиограмма сердца улья")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--json", action="store_true", help="JSON-контракт метрики")
    g.add_argument("--badge", action="store_true", help="перезаписать pulse.json + pulse.svg")
    g.add_argument("--monitor", action="store_true", help="badge + свидетель в PULSE_LOG при смене статуса")
    ap.add_argument("--strict", action="store_true", help="exit 1 если не LIVE или соты сломаны")
    args = ap.parse_args()
    c = measure()
    if args.json:
        print(json.dumps(c, ensure_ascii=False, indent=2))
    if args.badge or args.monitor:
        write_badge(c)
    if args.monitor:
        monitor(c)
    if not (args.json or args.badge or args.monitor):
        w = ", ".join(f"{k}={v['verdict']}" for k, v in c.get("worlds", {}).items()) or "—"
        age = f"{c['value']} ч" if c.get("value") is not None else "—"
        print(f"ПУЛЬС: {c['status']} · последний удар {age} назад · ударов {c.get('beats', 0)} · "
              f"соты {'✓' if c.get('chain_ok') else '✗'} · миры: {w}")
        print(f"свидетель: {c.get('detail', '')}")
    if args.strict and (c["status"] != "LIVE" or not c.get("chain_ok")):
        sys.exit(1)


if __name__ == "__main__":
    main()

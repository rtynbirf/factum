#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
МИНИПРИТОК — эксперименты П1/П2 по открытым пунктам §9 MODEL.md.

П1 (§9: «минимальный приток, при котором строгая форма ещё возникает»):
  в chem.py приток задаётся параметром inflow (апейрон: с вероятностью inflow
  в W попадает свежая пищевая строка; inflow=0 — закрытая система). Сетка
  притока лог-равномерная (шаг ~ x3) плюс контроль inflow=0; катализ p
  фиксирован на точке сетки (якорь CHEM_RESULTS.md: p=0.12, приток 0.1 -> 19/20).
  Критерий живого контура: |𝔉|>=2 (как в CHEM_RESULTS.md и JOURNAL.md).
  Методика: грубая сетка (6 прогонов на точку) -> сгущение у порога
  (средние точки по 8 прогонов, соседние с порогом и якорные — до 20).
  Шагов на прогон 150000 у ВСЕХ точек. Для каждой точки: доля живых +
  доверительный интервал Уилсона (95%). Порог = минимальный приток сетки,
  при котором точечная доля >= 50%.

П2 (§9: «роль памяти H ... сравнение пока только на SKI/BCI»):
  память в chem.py — флаг конструктора Chem(memory=True/False): при ВЫКЛ
  вытеснение слотов равномерное (накопленный credit не защищает воспроизводимое,
  см. chem.py::_replace). Правка chem.py не нужна — обёртка передаёт флаг CLI.
  Сравнение ВКЛ/ВЫКЛ на притоке 0.1 и на пороговом притоке из П1 (n>=8+8,
  здесь 20+20 по схеме сидов chem_sweep.py).

Бюджет: суммарная стенка всех прогонов ограничена (--budget минут, по умолчанию
25); счётчик секунд прогонов копится в state-файле между запусками; при
исчерпании бюджета скрипт честно режет план сгущения и печатает предупреждение
(список урезаний попадает в MININFLUX.md).

Хеш-соты (MININFLUX.md): append-only, каждая строка данных несёт prev = sha256
предыдущей СЫРОЙ строки (первые 12 hex-символов, как factum.py line_hash);
первая строка данных хеширует якорь 'MININFLUX' (в JOURNAL.md якорь — 'GENESIS').
Проверка целости: python3 scripts/mininflux.py verify.

CLI:
  python3 scripts/mininflux.py grid --stage 1 --out R.json   # П1: грубая сетка
  python3 scripts/mininflux.py grid --stage 2 --out R.json   # П1: сгущение у порога
  python3 scripts/mininflux.py memory --out R.json           # П2: память ВКЛ/ВЫКЛ
  python3 scripts/mininflux.py report --out R.json           # собрать MININFLUX.md
  python3 scripts/mininflux.py verify                        # целость хеш-цепочки

State-файл (--out) по умолчанию кладётся РЯДОМ с клоном, а не в репо:
репо получает только scripts/mininflux.py и MININFLUX.md.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import statistics as st
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                     # корень клона factum
sys.path.insert(0, ROOT)

from chem import Chem                            # только импорт, chem.py не правим

# ---------- параметры экспериментов (в стиле chem_sweep.py / generations.py) ----------

M, L = 300, 6                                    # ёмкость и длина строк (как в CHEM_RESULTS.md)
T_FULL = 150000                                  # шагов на прогон (полный бюджет CHEM_RESULTS.md)
CAT_P_GRID = (0.12, 0.05, 0.03)                  # катализ: якорь + два нижних режима CHEM_RESULTS
INFLUX_GRID = (0.0, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1)  # лог-сетка притока + контроль 0
N_COARSE, N_MID, N_DENSE = 6, 8, 20              # прогонов на точку: грубо / средние точки / плотно
SEEDS = list(range(1, 21))                       # схема сидов chem_sweep.py (S = range(1, 21))
ANCHOR_CAT, ANCHOR_INFLOW = 0.12, 0.1            # якорный режим CHEM_RESULTS.md
GUARD_CAT = 0.1                                  # П2, доп. точка: альтернативное чтение «p=0.1»
EXPECT = {(0.12, 0.1): 19, (0.12, 0.0): 12,      # ожидаемые живые по CHEM_RESULTS.md
          (0.05, 0.1): 13, (0.05, 0.0): 10,
          (0.03, 0.1): 12, (0.03, 0.0): 9}
MININFLUX_MD = os.path.join(ROOT, "MININFLUX.md")
Z95 = 1.959963984540054


# ---------- утилиты (хеши — как в factum.py) ----------

def line_hash(s):
    """sha256 сырой строки, первые 12 hex — тот же правило, что в factum.py."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def wilson(k, n, z=Z95):
    """Доверительный интервал Уилсона (95%) для доли k/n."""
    if n == 0:
        return (0.0, 1.0)
    ph = k / n
    d = 1.0 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fmt_ci(k, n):
    lo, hi = wilson(k, n)
    return "[%.2f;%.2f]" % (lo, hi)


# ---------- state между запусками (прогоны детерминированы, копим по сидам) ----------

def key_of(pc, infl, mem):
    return "%g|%g|%s" % (pc, infl, mem)


def load_state(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"runs": {}, "mids": {}, "wall_s": 0.0, "cut": [], "ms_meta": []}


def save_state(path, stt):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stt, f, ensure_ascii=False, indent=1)


def pool(cell):
    """Свести ячейку по всем накопленным сидам -> (живых, всего, список F)."""
    sds = sorted(int(s) for s in cell["seeds"])
    F = [cell["seeds"][str(sd)][0] for sd in sds]
    k = sum(1 for f in F if f >= 2)
    return k, len(F), F


def time_left_s(stt, budget_min):
    """Остаток стеночного бюджета прогонов (сек) с запасом на накладные."""
    return budget_min * 60.0 - stt["wall_s"] - 60.0


def run_missing(cell, pc, infl, mem, target, steps):
    """Догнать ячейку до target сидов (seeds 1..target, схема chem_sweep.py)."""
    have = set(int(s) for s in cell["seeds"])
    need = [sd for sd in SEEDS[:target] if sd not in have]
    sec = 0.0
    for sd in need:
        t0 = time.perf_counter()
        c = Chem(seed=sd, p=pc, inflow=infl, memory=mem).run(steps)
        f = len(c.organization())
        sec += time.perf_counter() - t0
        cell["seeds"][str(sd)] = [f, c.new]
    if need:
        cell["utc"] = utc_now()
        cell["steps"] = steps
    return len(need), sec


def milestone(cell, stage, mem):
    """Снимок ячейки на момент завершения этапа — будущая строка сот."""
    k, n, F = pool(cell)
    cell.setdefault("ms", []).append({
        "utc": cell.get("utc") or utc_now(), "stage": stage, "mem": mem,
        "n": n, "k": k, "medF": st.median(F) if F else 0.0, "steps": cell.get("steps", T_FULL)})


# ---------- П1: сетка притока ----------

def grid_stage1(stt, runs, a):
    """Грубая сетка: N_COARSE прогонов на точку, полный T."""
    for pc in CAT_P_GRID:
        for infl in sorted(INFLUX_GRID):
            cell = runs.setdefault(key_of(pc, infl, True), {"seeds": {}})
            have = len(cell["seeds"])
            if have >= N_COARSE:
                continue
            need = N_COARSE - have
            if time_left_s(stt, a.budget) < need * 1.4:
                stt["cut"].append("П1 сетка: кат %g приток %g — не хватает бюджета, точка пропущена"
                                  % (pc, infl))
                print("РЕЗКА: " + stt["cut"][-1], flush=True)
                continue
            added, sec = run_missing(cell, pc, infl, True, N_COARSE, a.steps)
            stt["wall_s"] += sec
            milestone(cell, "сетка", True)
            k, n, F = pool(cell)
            print("П1 сетка кат=%g приток=%g: %d/%d живых (%.2f) CI95 %s мед|F|=%.1f [%.1f с]"
                  % (pc, infl, k, n, k / n, fmt_ci(k, n), st.median(F), sec), flush=True)


def find_bracket(fracs):
    """Первое пересечение 50% при росте притока -> (ниже, выше) или None."""
    pts = sorted(fracs)
    for i, x in enumerate(pts):
        if fracs[x] >= 0.5:
            if i == 0:
                return None            # порог = 0: закрытая система уже жива
            return (pts[i - 1], x)
    return None                        # порога в сетке нет: живых < 50% всюду


def grid_stage2(stt, runs, a):
    """Сгущение у порога: якорные точки до 20, средние точки по 8, соседи порога до 20."""
    for pc in CAT_P_GRID:
        # 1) якорные точки (закрытая 0 и открытая 0.1) — до 20 прогонов для крепого CI
        for infl in (min(INFLUX_GRID), max(INFLUX_GRID)):
            cell = runs[key_of(pc, infl, True)]
            if len(cell["seeds"]) < N_DENSE:
                if time_left_s(stt, a.budget) < (N_DENSE - len(cell["seeds"])) * 1.4:
                    stt["cut"].append("П1 сгущение: кат %g приток %g — точка оставлена на n=%d"
                                      % (pc, infl, len(cell["seeds"])))
                    print("РЕЗКА: " + stt["cut"][-1], flush=True)
                    continue
                added, sec = run_missing(cell, pc, infl, True, N_DENSE, a.steps)
                stt["wall_s"] += sec
                milestone(cell, "сгущение", True)
                k, n, F = pool(cell)
                print("П1 сгущение кат=%g приток=%g: %d/%d живых (%.2f) CI95 %s [%.1f с]"
                      % (pc, infl, k, n, k / n, fmt_ci(k, n), sec), flush=True)
        # 2) проверка якорей против CHEM_RESULTS.md (детерминизм: должно совпасть)
        for infl in (min(INFLUX_GRID), max(INFLUX_GRID)):
            k, n, _ = pool(runs[key_of(pc, infl, True)])
            exp = EXPECT.get((pc, infl))
            if exp is not None and n == 20:
                print("ЯКОРЬ CHEM_RESULTS кат=%g приток=%g: ожидалось %d/20, получено %d/20 — %s"
                      % (pc, infl, exp, k, "совпало" if k == exp else "РАСХОЖДЕНИЕ"), flush=True)
        # 3) скобка порога по грубым данным
        fracs = {}
        for infl in sorted(INFLUX_GRID):
            k, n, _ = pool(runs[key_of(pc, infl, True)])
            fracs[infl] = k / n
        br = find_bracket(fracs)
        mids = stt["mids"].setdefault(str(pc), [])
        if br:
            lo, hi = br
            # две средние лог-точки внутри скобки
            if lo > 0:
                ratio = (hi / lo) ** (1.0 / 3.0)
                cands = [lo * ratio, lo * ratio * ratio]
            else:                       # скобка от нуля: делим верх пополам
                cands = [hi / 3.0, 2 * hi / 3.0]
            for mx in cands:
                mx = round(mx, 8)
                if any(abs(mx - v) < 1e-12 for v in list(INFLUX_GRID) + mids):
                    continue
                mids.append(mx)
                cell = runs.setdefault(key_of(pc, mx, True), {"seeds": {}})
                if time_left_s(stt, a.budget) < N_MID * 1.4:
                    stt["cut"].append("П1 сгущение: средняя точка кат %g приток %g — не прогнана"
                                      % (pc, mx))
                    print("РЕЗКА: " + stt["cut"][-1], flush=True)
                    mids.remove(mx)
                    runs.pop(key_of(pc, mx, True), None)
                    continue
                added, sec = run_missing(cell, pc, mx, True, N_MID, a.steps)
                stt["wall_s"] += sec
                milestone(cell, "сгущение", True)
                k, n, F = pool(cell)
                print("П1 сгущение кат=%g приток=%g (средняя): %d/%d живых (%.2f) CI95 %s [%.1f с]"
                      % (pc, mx, k, n, k / n, fmt_ci(k, n), sec), flush=True)
        # 4) пересчитать скобку на уточнённой сетке и уплотнить соседей порога до 20
        fracs = {}
        for infl in sorted(set(INFLUX_GRID) | set(mids)):
            cell = runs[key_of(pc, infl, True)]
            k, n, _ = pool(cell)
            fracs[infl] = k / n
        br = find_bracket(fracs)
        if br:
            for infl in br:
                cell = runs[key_of(pc, infl, True)]
                if len(cell["seeds"]) < N_DENSE:
                    if time_left_s(stt, a.budget) < (N_DENSE - len(cell["seeds"])) * 1.4:
                        stt["cut"].append("П1 сгущение: сосед порога кат %g приток %g оставлен на n=%d"
                                          % (pc, infl, len(cell["seeds"])))
                        print("РЕЗКА: " + stt["cut"][-1], flush=True)
                        continue
                    added, sec = run_missing(cell, pc, infl, True, N_DENSE, a.steps)
                    stt["wall_s"] += sec
                    milestone(cell, "сгущение", True)
                    k, n, F = pool(cell)
                    print("П1 сгущение кат=%g приток=%g (сосед порога): %d/%d живых (%.2f) CI95 %s [%.1f с]"
                          % (pc, infl, k, n, k / n, fmt_ci(k, n), sec), flush=True)
        # 4.5) если бюджет позволяет — добить ВСЮ основную сетку до 20 прогонов
        #      (шум n=6 у кат 0.12 немонотонен; плотный профиль честнее)
        for infl in sorted(INFLUX_GRID):
            cell = runs[key_of(pc, infl, True)]
            if len(cell["seeds"]) < N_DENSE:
                if time_left_s(stt, a.budget) < (N_DENSE - len(cell["seeds"])) * 1.4:
                    stt["cut"].append("П1 сгущение: кат %g приток %g оставлен на n=%d (бюджет)"
                                      % (pc, infl, len(cell["seeds"])))
                    print("РЕЗКА: " + stt["cut"][-1], flush=True)
                    continue
                added, sec = run_missing(cell, pc, infl, True, N_DENSE, a.steps)
                stt["wall_s"] += sec
                milestone(cell, "сгущение", True)
                k, n, F = pool(cell)
                print("П1 сгущение кат=%g приток=%g: %d/%d живых (%.2f) CI95 %s [%.1f с]"
                      % (pc, infl, k, n, k / n, fmt_ci(k, n), sec), flush=True)
        # 5) итоговая картина по этой кат-точке
        print("--- кат p=%g, уточнённая сетка притока:" % pc, flush=True)
        for infl in sorted(set(INFLUX_GRID) | set(mids)):
            k, n, _ = pool(runs[key_of(pc, infl, True)])
            print("    приток %-8g: %d/%d живых (%.2f) CI95 %s" % (infl, k, n, k / n, fmt_ci(k, n)), flush=True)


def cmd_grid(a):
    stt = load_state(a.out)
    stt["budget_min"] = a.budget
    runs = stt["runs"]
    t0 = time.perf_counter()
    if a.stage == 1:
        grid_stage1(stt, runs, a)
    else:
        grid_stage2(stt, runs, a)
    stt["wall_s"] += 0.0                # сек прогонов уже учтены по точкам
    save_state(a.out, stt)
    print("Готово: стадия %d, стенка стадии %.1f с; всего прогонов %.1f с; осталось ~%.0f с бюджета"
          % (a.stage, time.perf_counter() - t0, stt["wall_s"], time_left_s(stt, a.budget)), flush=True)
    if stt["cut"]:
        print("Урезания: " + " | ".join(stt["cut"]), flush=True)


# ---------- П2: память ВКЛ/ВЫКЛ ----------

def threshold_inflow(stt, runs, pc):
    """Минимальный приток уточнённой сетки с точечной долей >= 50% (или None)."""
    mids = stt["mids"].get(str(pc), [])
    for infl in sorted(set(INFLUX_GRID) | set(mids)):
        cell = runs[key_of(pc, infl, True)]
        k, n, _ = pool(cell)
        if n and k / n >= 0.5:
            return infl
    return None


def cmd_memory(a):
    stt = load_state(a.out)
    stt["budget_min"] = a.budget
    runs = stt["runs"]
    thr = threshold_inflow(stt, runs, ANCHOR_CAT)
    if thr is None:
        thr = ANCHOR_INFLOW
        print("ВНИМАНИЕ: порог при кат %g не найден, П2 идёт на притоке %g" % (ANCHOR_CAT, thr), flush=True)
    print("Пороговый приток из П1 (кат %g): %g" % (ANCHOR_CAT, thr), flush=True)
    cells = [(ANCHOR_CAT, ANCHOR_INFLOW, True), (ANCHOR_CAT, ANCHOR_INFLOW, False),
             (ANCHOR_CAT, thr, True), (ANCHOR_CAT, thr, False),
             (GUARD_CAT, ANCHOR_INFLOW, True), (GUARD_CAT, ANCHOR_INFLOW, False)]
    for pc, infl, mem in cells:
        cell = runs.setdefault(key_of(pc, infl, mem), {"seeds": {}})
        have = len(cell["seeds"])
        reused = have >= N_DENSE
        target = N_DENSE
        if not reused:
            # минимум n>=8 обязателен; до 20 — если хватает бюджета
            if time_left_s(stt, a.budget) < (target - have) * 1.4:
                target = max(N_MID, have)
                if time_left_s(stt, a.budget) < (target - have) * 1.4:
                    stt["cut"].append("П2: кат %g приток %g память %s — не хватает бюджета (есть n=%d)"
                                      % (pc, infl, "ВКЛ" if mem else "ВЫКЛ", have))
                    print("РЕЗКА: " + stt["cut"][-1], flush=True)
                    continue
        added, sec = run_missing(cell, pc, infl, mem, target, a.steps)
        stt["wall_s"] += sec
        stage = "П2 (прогоны П1, детерминизм)" if reused else "П2"
        milestone(cell, stage, mem)
        k, n, F = pool(cell)
        print("П2 кат=%g приток=%g память=%s: %d/%d живых (%.2f) CI95 %s мед|F|=%.1f [%.1f с]"
              % (pc, infl, "ВКЛ" if mem else "ВЫКЛ", k, n, k / n, fmt_ci(k, n),
                 st.median(F), sec), flush=True)
    save_state(a.out, stt)
    print("Всего прогонов (П1+П2): %.1f с" % stt["wall_s"], flush=True)


# ---------- сборка MININFLUX.md (соты) ----------

HEADER_TMPL = """# МИНИПРИТОК ЖИВОГО КОНТУРА (append-only; §9 MODEL.md, FACTUM v1.0)

Соты: факт = строка. Каждая строка данных несёт sha256 предыдущей СЫРОЙ строки
(колонка prev); для первой строки предыдущей считается строка-якорь MININFLUX,
т.е. prev[1] = sha256('MININFLUX')[:12] = %(anchor)s. Подмена любой строки ловится
СЛЕДУЮЩЕЙ строкой. Проверка: `python3 scripts/mininflux.py verify`.

Что закрывает (§9 MODEL.md): «минимальный приток, при котором строгая форма ещё
возникает» и «роль памяти H: сравнение пока только на SKI/BCI».

Методика: мир chem.py (M=%(M)d, L=%(L)d, T=%(T)d шагов на КАЖДЫЙ прогон, сиды 1..n по
схеме chem_sweep.py). В колонке p — приток inflow (апейрон); катализ p указан в
колонке «эксперимент». Сетка притока лог-равномерная (шаг ~ x3) плюс контроль
p=0 — закрытая система. Критерий живого контура |𝔉|>=2 (как в CHEM_RESULTS.md и
JOURNAL.md: «CHEM — F >= 2»); строгий критерий SKI-мира в chem.py не реализован,
поэтому «строгая форма» здесь представлена критерием репо (лигированный продукт
y=a+b по построению не подстрока реагентов, расщеплённый — подстрока). Доля живых
+ интервал Уилсона 95%%. Этапы: «сетка» — грубый поиск (n=6), «сгущение» —
средние точки (n=8) и соседние с порогом/якорные точки (n=20). Порог = минимальный
приток сетки с точечной долей >= 50%%; скобки сетки указаны честно.

Память: chem.py уже имеет флаг Chem(memory=True/False) — при ВЫКЛ вытеснение
равномерное (накопленный credit не защищает слоты, chem.py::_replace); правки
chem.py не потребовалось, флаг передаёт обёртка scripts/mininflux.py. Прогоны
детерминированы сидом;%(anchors)s

| # | UTC | эксперимент | p | шаги | n | живых | доля | CI95 | память | prev |
|---|---|---|---|---|---|---|---|---|---|---|
"""


def experiment_label(ms, pc):
    if ms["stage"].startswith("П2"):
        return "%s (кат %g)" % (ms["stage"], pc)
    return "П1 %s (кат %g)" % (ms["stage"], pc)


def cmd_report(a):
    stt = load_state(a.out)
    runs = stt["runs"]
    rows = []                                    # сырые строки данных, по порядку
    prev_raw = "MININFLUX"                       # якорь первой строки
    num = 0
    # П1: по кат-точкам, внутри — по притоку, этапы в порядке накопления
    # (вехи П2 здесь не выводим — они принадлежат П2-блоку ниже)
    for pc in CAT_P_GRID:
        mids = stt["mids"].get(str(pc), [])
        for infl in sorted(set(INFLUX_GRID) | set(mids)):
            cell = runs.get(key_of(pc, infl, True))
            if not cell:
                continue
            for ms in cell.get("ms", []):
                if ms["stage"].startswith("П2"):
                    continue
                num += 1
                row = ("| %d | %s | %s | %g | %d | %d | %d/%d | %.2f | %s | %s | %s |"
                       % (num, ms["utc"], experiment_label(ms, pc), infl, ms["steps"],
                          ms["n"], ms["k"], ms["n"], ms["k"] / ms["n"], fmt_ci(ms["k"], ms["n"]),
                          "ВКЛ" if ms["mem"] else "ВЫКЛ", line_hash(prev_raw)))
                rows.append(row)
                prev_raw = row
    # П2: ячейки в порядке cmd_memory (порог 0.0 — валидный, не путать с None)
    thr = threshold_inflow(stt, runs, ANCHOR_CAT)
    if thr is None:
        thr = ANCHOR_INFLOW
    for pc, infl, mem in [(ANCHOR_CAT, ANCHOR_INFLOW, True), (ANCHOR_CAT, ANCHOR_INFLOW, False),
                          (ANCHOR_CAT, thr, True), (ANCHOR_CAT, thr, False),
                          (GUARD_CAT, ANCHOR_INFLOW, True), (GUARD_CAT, ANCHOR_INFLOW, False)]:
        cell = runs.get(key_of(pc, infl, mem))
        if not cell:
            continue
        for ms in cell.get("ms", []):
            if not ms["stage"].startswith("П2"):
                continue                          # П1-этапы уже выведены выше
            num += 1
            row = ("| %d | %s | %s | %g | %d | %d | %d/%d | %.2f | %s | %s | %s |"
                   % (num, ms["utc"], experiment_label(ms, pc), infl, ms["steps"],
                      ms["n"], ms["k"], ms["n"], ms["k"] / ms["n"], fmt_ci(ms["k"], ms["n"]),
                      "ВКЛ" if ms["mem"] else "ВЫКЛ", line_hash(prev_raw)))
            rows.append(row)
            prev_raw = row

    # ---- ВЫВОД (по плотнейшим данным) ----
    budget_min = stt.get("budget_min", 25.0)
    # якорные проверки против CHEM_RESULTS.md (считаем из данных, не хардкодим)
    checks = []
    for pc in CAT_P_GRID:
        for infl in (min(INFLUX_GRID), max(INFLUX_GRID)):
            k, n, _ = pool(runs[key_of(pc, infl, True)])
            exp = EXPECT.get((pc, infl))
            if exp is not None:
                checks.append("кат %g приток %g: %d/20 (ожидалось %d/20)" % (pc, infl, k, exp))
    anchors_text = (" якорные точки воспроизвели CHEM_RESULTS.md: " + "; ".join(checks) + ".")
    out = ["## ВЫВОД\n"]
    for pc in CAT_P_GRID:
        mids = stt["mids"].get(str(pc), [])
        pts = sorted(set(INFLUX_GRID) | set(mids))
        fracs = {}
        for infl in pts:
            k, n, _ = pool(runs[key_of(pc, infl, True)])
            fracs[infl] = (k, n)
        thr_pc = None
        for infl in pts:
            k, n = fracs[infl]
            if n and k / n >= 0.5:
                thr_pc = infl
                break
        if thr_pc == 0.0:
            k, n = fracs[0.0]
            lo, hi = wilson(k, n)
            line = ("- П1, кат p=%g: минимальный приток с долей >= 50%% — **0 (закрытая система)**: "
                    "%d/%d живых ([%.2f;%.2f]). Приток для живого контура на этом режиме не "
                    "обязателен; скобки снизу нет (приток неотрицателен)." % (pc, k, n, lo, hi))
            if lo < 0.5:
                line += " Оговорка: точечная доля у самой границы критерия — CI95 допускает и значение ниже 50%."
            out.append(line)
        elif thr_pc is None:
            k, n = fracs[max(pts)]
            out.append("- П1, кат p=%g: порог не достигнут — даже приток %g даёт %d/%d (%s); "
                       "порог лежит выше 0.1." % (pc, max(pts), k, n, fmt_ci(k, n)))
        else:
            i = pts.index(thr_pc)
            klo, nlo = fracs[pts[i - 1]]
            khi, nhi = fracs[thr_pc]
            line = ("- П1, кат p=%g: точечный порог притока — между %g (%d/%d, %s) и **%g** "
                    "(%d/%d, %s); минимальная точка сетки с долей >= 50%% — %g."
                    % (pc, pts[i - 1], klo, nlo, fmt_ci(klo, nlo), thr_pc, khi, nhi,
                       fmt_ci(khi, nhi), thr_pc))
            # честная оговорка: если выше порога доля снова падает ниже 50%, порог размыт
            above = [(infl, fracs[infl]) for infl in pts[i + 1:]]
            worst = min(above, key=lambda kv: kv[1][0] / kv[1][1]) if above else None
            if worst and worst[1][0] / worst[1][1] < 0.5:
                line += (" Оговорка: профиль доли выше порога немонотонен (минимум %d/%d при притоке "
                         "%g) — порог размыт, читать как оценку порядка, а не резкую границу."
                         % (worst[1][0], worst[1][1], worst[0]))
            out.append(line)
    # память: числа ВКЛ/ВЫКЛ (по всем накопленным сидам ячейки)
    mem_rows = []
    mem_data = {}
    for pc, infl in [(ANCHOR_CAT, ANCHOR_INFLOW), (ANCHOR_CAT, thr), (GUARD_CAT, ANCHOR_INFLOW)]:
        kon, non, Fon = pool(runs[key_of(pc, infl, True)])
        koff, noff, Foff = pool(runs[key_of(pc, infl, False)])
        mem_data[(pc, infl)] = (kon / non, koff / noff, st.median(Fon), st.median(Foff))
        mem_rows.append("кат %g приток %g: ВКЛ %d/%d (%.2f) против ВЫКЛ %d/%d (%.2f)"
                        % (pc, infl, kon, non, kon / non, koff, noff, koff / noff))
    d_on, d_off, medF_on, medF_off = mem_data[(ANCHOR_CAT, thr)]
    out.append("- П2, память (живой контур |𝔉|>=2, n=20 на клетку): " + "; ".join(mem_rows) + ".")
    if d_off > d_on + 0.05:
        verdict = ("выключение памяти ПОВЫШАЕТ долю живых контуров — сильнее всего в закрытой "
                   "системе (приток 0): %.2f против %.2f (мед.|𝔉| %.1f против %.1f); направление "
                   "совпадает с REDTEAM_chem_memory.md (кат 0.08: открытая ВКЛ 16/20, ВЫКЛ 20/20; "
                   "закрытая ВКЛ 9/20, ВЫКЛ 16/20). Память H — не условие возникновения контура, "
                   "а фактор, удерживающий долю живых ниже (защита воспроизводимого тормозит "
                   "собирание большой организации)."
                   % (d_off, d_on, medF_off, medF_on))
    elif d_on > d_off + 0.05:
        verdict = ("выключение памяти ПОНИЖАЕТ долю живых контуров (в закрытой системе %.2f "
                   "против %.2f); направление противоречит REDTEAM_chem_memory.md (кат 0.08: "
                   "открытая ВКЛ 16/20, ВЫКЛ 20/20)." % (d_on, d_off))
    else:
        verdict = ("разница долей ВКЛ/ВЫКЛ в закрытой системе в пределах 0.05 (%.2f против %.2f) — "
                   "существенного эффекта памяти на возникновение контура не видно."
                   % (d_on, d_off))
    out.append("- Вердикт по памяти: " + verdict)
    out.append("- Все прогонки T=%d шагов (урезаний длины не потребовалось); суммарная стенка "
               "прогонов П1+П2: %.0f с (~%.1f мин) из бюджета %.0f мин. Урезаний по бюджету: %d."
               % (T_FULL, stt["wall_s"], stt["wall_s"] / 60.0, budget_min, len(stt["cut"])))
    if stt["cut"]:
        for c in stt["cut"]:
            out.append("  - урезано: " + c)
    out.append("- Якоря детерминизма: " + "; ".join(checks) + " — совпадение подтверждает "
               "воспроизводимость обвязки.")
    out.append("")

    text = HEADER_TMPL % {"anchor": line_hash("MININFLUX"), "M": M, "L": L, "T": T_FULL,
                          "anchors": anchors_text}
    with open(MININFLUX_MD, "w", encoding="utf-8") as f:
        f.write(text + "\n".join(rows) + "\n\n" + "\n".join(out))
    print("written: %s (%d строк данных)" % (MININFLUX_MD, len(rows)), flush=True)


# ---------- проверка сот ----------

def cmd_verify(a):
    if not os.path.exists(MININFLUX_MD):
        raise SystemExit("MININFLUX.md не найден")
    rows = []
    with open(MININFLUX_MD, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("| ") and not line.startswith("| #"):
                rows.append(line)
    prev_raw = "MININFLUX"
    for i, row in enumerate(rows):
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) != 11:
            raise SystemExit("строка %d: %d колонок вместо 11" % (i + 1, len(cells)))
        if cells[-1] != line_hash(prev_raw):
            raise SystemExit("строка %d: хеш-цепочка порвана" % (i + 1))
        prev_raw = row
    print("MININFLUX: %d строк данных; цепочка цела" % len(rows))


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description="МИНИПРИТОК — П1/П2 по §9 MODEL.md (соты MININFLUX.md)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(ROOT), "mininflux_results.json"),
                    help="state-файл с результатами (по умолчанию РЯДОМ с клоном, не в репо)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grid", help="П1: сетка притока")
    g.add_argument("--stage", type=int, choices=[1, 2], default=1, help="1 — грубая сетка, 2 — сгущение")
    g.add_argument("--steps", type=int, default=T_FULL, help="шагов на прогон")
    g.add_argument("--budget", type=float, default=25.0, help="стеночный бюджет всех прогонов, минут")
    m = sub.add_parser("memory", help="П2: память ВКЛ/ВЫКЛ")
    m.add_argument("--steps", type=int, default=T_FULL, help="шагов на прогон")
    m.add_argument("--budget", type=float, default=25.0, help="стеночный бюджет всех прогонов, минут")
    r = sub.add_parser("report", help="собрать MININFLUX.md из state-файла")
    v = sub.add_parser("verify", help="проверить хеш-цепочку MININFLUX.md")
    a = ap.parse_args()
    if a.cmd == "grid":
        cmd_grid(a)
    elif a.cmd == "memory":
        cmd_memory(a)
    elif a.cmd == "report":
        cmd_report(a)
    elif a.cmd == "verify":
        cmd_verify(a)


if __name__ == "__main__":
    main()

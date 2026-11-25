#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ФАКТУМ v1.1 — ОТБОР ФОРМ (эксперимент поколений; открытый §9 MODEL.md).

Форма 𝔉 становится ЕДИНИЦЕЙ ОТБОРА:
  поколение 0: свежие миры -> 𝔉_0 (gfp-организация, живая: |𝔉|>=2)
  поколение g: K сеянцев 𝔉_g (копия формы с шумом копирования mu) ->
               каждый сеянец прокручивается в мире -> минимальный критерий
               |𝔉|>=2 (сеянец жив) -> отбор лучшего (сначала strict-размер,
               потом размер) -> 𝔉_{g+1}. Порода умерла -> перезапуск от свежего мира.
  КОНТРОЛЬ: та же процедура БЕЗ отбора (случайный из живых сеянцев) —
            подъём от отбора против дрейфа от шума.

Мировые якоря практики: минимальный критерий (Soros, Cheney, Stanley — ALIFE 2016,
«How the Strictness of the Minimal Criterion Impacts Open-Ended Evolution»);
POET (Lehman, Stanley, GECCO 2019 — бесконечная порождаемость задач);
Tierra (Ray, 1992 — наследование копированием с шумом, цифровой отбор).

Гипотеза: итерированный отбор форм поднимает |𝔉| над контролем и над базовой
линией свежих миров и (SKI) находит СТРОГУЮ форму — то, чего в статичном мире
0/20 (LINEAR_RESULTS.md).

CLI (SKI — по частям с JSON-состоянием, как linear_experiment; CHEM — целиком):
  python3 generations.py SKI INIT      # 𝔉_0 + базовая линия свежих миров
  python3 generations.py SKI STEP n    # n поколений (линия отбора + контроль)
  python3 generations.py SKI REPORT    # собрать GENERATIONS_RESULTS.md
  python3 generations.py CHEM RUN      # весь химический эксперимент
"""
import json
import os
import random
import statistics as st
import sys

import emergent as E
import chem as H

sys.setrecursionlimit(200000)

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "GENERATIONS_RESULTS.md")

M_SKI = 150          # ёмкость SKI-мира
T_SKI = 3000         # шагов мира на сеянца (бюджет §1 LINEAR_RESULTS)
G_SKI = 12           # поколений отбора
K = 4                # сеянцев на породу
MU = 0.05            # шум копирования: слот заменяется свежим термом из апейрона

M_CHEM = 300         # ёмкость химии
T_CHEM = 20000       # тиков на сеянца
G_CHEM = 30          # поколений
MU2 = 0.02           # точечная бит-мутация копируемой строки

SKI_STATE = os.path.join(HERE, "gen_ski.json")
CHEM_STATE = os.path.join(HERE, "gen_chem.json")

P = 0.12             # химия: вероятность катализа (лучший режим CHEM_RESULTS.md)


# ---------- сериализация термов (кортежи <-> JSON) ----------

def jterm(t):
    return t if isinstance(t, str) else [jterm(t[0]), jterm(t[1])]


def pterm(t):
    return t if isinstance(t, str) else (pterm(t[0]), pterm(t[1]))


def load(path, default):
    if os.path.exists(path):
        return json.load(open(path))
    return default


def save(path, d):
    json.dump(d, open(path, "w"))


# ---------- SKI: линия отбора ----------

def ski_seedling(form, rng):
    """Форма -> начальный мир длины M_SKI: слоты циклом по типам; шум mu — свежий терм."""
    w0 = [form[i % len(form)] for i in range(M_SKI)]
    return [E.rand_term(rng, 2) if rng.random() < MU else x for x in w0]


def ski_litter(form, g, line):
    """K сеянцев одной породы. -> (метрики сеянцев, живой родитель или None)."""
    cands = []
    for k in range(K):
        seed = 100000 * g + 1000 * line + 17 * k + 5
        rng = random.Random(seed)
        w = E.World(seed=seed, w0=ski_seedling(form, rng), inflow=0.5, memory=True).run(T_SKI)
        cands.append({"f": list(w.organization()),
                      "fs": list(w.organization(strict=True))})
    ok = [c for c in cands if len(c["f"]) >= 2]
    if not ok:
        return cands, None
    best = max(ok, key=lambda c: (len(c["fs"]), len(c["f"])))
    return cands, best["f"]


def ski_control(form, g):
    """Контрольная порода: случайный из живых сеянцев (минимальный критерий без оптимизации)."""
    cands, _ = ski_litter(form, g, line=1)
    ok = [c for c in cands if len(c["f"]) >= 2]
    if not ok:
        return cands, None
    return cands, random.Random(555 + g).choice(ok)["f"]


def fresh_form(seed_start):
    """Перезапуск породы: первый свежий мир с живой формой."""
    for s in range(20):
        w = E.World(seed=seed_start + s, inflow=0.5, memory=True).run(T_SKI)
        f = list(w.organization())
        if len(f) >= 2:
            return f
    return None


def ski_init():
    d = load(SKI_STATE, {"g": 0, "parent": None, "ctrl": None, "rows": [],
                         "deaths_s": 0, "deaths_c": 0, "strict_hits": 0, "seedlings": 0})
    if d["parent"] is not None:
        print("already inited")
        return
    f0 = fresh_form(777)
    assert f0, "F0 не найден за 20 попыток"
    d["parent"] = [jterm(x) for x in f0]
    d["ctrl"] = d["parent"]
    base = []
    for s in range(3):
        w = E.World(seed=4242 + s, inflow=0.5, memory=True).run(T_SKI)
        base.append(len(w.organization()))
    d["baseline"] = base
    save(SKI_STATE, d)
    print("F0: |F|=%d; базовая линия свежих миров: %s" % (len(f0), base))


def ski_step(n):
    d = load(SKI_STATE, None)
    assert d and d["parent"], "сначала SKI INIT"
    for _ in range(n):
        g = d["g"]
        parent = [pterm(x) for x in d["parent"]]
        cands, nxt = ski_litter(parent, g, line=0)
        d["seedlings"] += len(cands)
        d["strict_hits"] += sum(1 for c in cands if c["fs"])
        sel = {"maxF": max(len(c["f"]) for c in cands),
               "maxFS": max(len(c["fs"]) for c in cands),
               "next": len(nxt) if nxt else 0, "dead": nxt is None}
        if nxt is None:
            d["deaths_s"] += 1
            f0 = fresh_form(9000 + 10 * g)
            assert f0, "перезапуск не удался"
            nxt = f0
        d["parent"] = [jterm(x) for x in nxt]

        cands_c, nxt_c = ski_control(parent, g)
        d["seedlings"] += len(cands_c)
        d["strict_hits"] += sum(1 for c in cands_c if c["fs"])
        ctl = {"maxF": max(len(c["f"]) for c in cands_c),
               "maxFS": max(len(c["fs"]) for c in cands_c),
               "next": len(nxt_c) if nxt_c else 0, "dead": nxt_c is None}
        if nxt_c is None:
            d["deaths_c"] += 1
            f0 = fresh_form(9500 + 10 * g)
            assert f0, "перезапуск контроля не удался"
            nxt_c = f0
        d["ctrl"] = [jterm(x) for x in nxt_c]

        d["rows"].append({"g": g, "sel": sel, "ctl": ctl})
        d["g"] = g + 1
        print("gen %d: sel %s | ctl %s" % (g, sel, ctl))
    save(SKI_STATE, d)


# ---------- CHEM: та же процедура на строках ----------

def chem_seedling(form, rng):
    w0 = [form[i % len(form)] for i in range(M_CHEM)]
    out = []
    for x in w0:
        r = rng.random()
        if r < MU:
            out.append(rng.choice(H.FOOD))
        elif r < MU + MU2:
            i = rng.randrange(len(x))
            out.append(x[:i] + rng.choice("01") + x[i + 1:])
        else:
            out.append(x)
    return out


def chem_litter(form, g, line):
    cands = []
    for k in range(K):
        seed = 100000 * g + 1000 * line + 17 * k + 5
        rng = random.Random(seed)
        c = H.Chem(seed=seed, p=P, inflow=0.1, memory=True)
        c.W = chem_seedling(form, rng)
        c.run(T_CHEM)
        cands.append(list(c.organization()))
    ok = [c for c in cands if len(c) >= 2]
    if not ok:
        return cands, None
    return cands, max(ok, key=len)


def chem_fresh(seed_start):
    for s in range(20):
        c = H.Chem(seed=seed_start + s, p=P, inflow=0.1, memory=True).run(T_CHEM)
        f = list(c.organization())
        if len(f) >= 2:
            return f
    return None


def chem_run():
    d = load(CHEM_STATE, {"g": 0, "parent": None, "ctrl": None, "rows": [],
                          "deaths_s": 0, "deaths_c": 0, "baseline": None})
    if d["parent"] is None:
        f0 = chem_fresh(777)
        assert f0, "chem F0 не найден"
        d["parent"] = f0
        d["ctrl"] = f0
        d["baseline"] = [len(chem_fresh(4242 + s) or []) for s in range(3)]
        print("chem F0: |F|=%d; базовая линия: %s" % (len(f0), d["baseline"]))
    for _ in range(G_CHEM):
        g = d["g"]
        cands, nxt = chem_litter(d["parent"], g, line=0)
        sel = {"maxF": max(len(c) for c in cands),
               "next": len(nxt) if nxt else 0, "dead": nxt is None}
        if nxt is None:
            d["deaths_s"] += 1
            nxt = chem_fresh(9000 + 10 * g) or []
        d["parent"] = nxt
        cands_c, nxt_c = chem_litter(d["ctrl"], g, line=1)
        ctl = {"maxF": max(len(c) for c in cands_c),
               "next": len(nxt_c) if nxt_c else 0, "dead": nxt_c is None}
        if nxt_c is None:
            d["deaths_c"] += 1
            nxt_c = chem_fresh(9500 + 10 * g) or []
        d["ctrl"] = nxt_c
        d["rows"].append({"g": g, "sel": sel, "ctl": ctl})
        d["g"] = g + 1
        print("gen %d: sel %s | ctl %s" % (g, sel, ctl))
    save(CHEM_STATE, d)


# ---------- отчёт ----------

def _ski_table(d):
    head = ("| поколение | линия ОТБОРА: max|F| / maxFS / |F|_родителя / смерть "
            "| КОНТРОЛЬ: max|F| / maxFS / |F|_родителя / смерть |",
            "|---|---|---|")
    lines = []
    for r in d["rows"]:
        s, c = r["sel"], r["ctl"]
        lines.append("| %d | %d / %d / %d / %s | %d / %d / %d / %s |"
                     % (r["g"], s["maxF"], s["maxFS"], s["next"], "да" if s["dead"] else "нет",
                        c["maxF"], c["maxFS"], c["next"], "да" if c["dead"] else "нет"))
    return head[0], head[1], lines


def _chem_table(d):
    head = ("| поколение | ОТБОР: max|F| / |F|_родителя / смерть "
            "| КОНТРОЛЬ: max|F| / |F|_родителя / смерть |",
            "|---|---|---|")
    lines = []
    for r in d["rows"]:
        s, c = r["sel"], r["ctl"]
        lines.append("| %d | %d / %d / %s | %d / %d / %s |"
                     % (r["g"], s["maxF"], s["next"], "да" if s["dead"] else "нет",
                        c["maxF"], c["next"], "да" if c["dead"] else "нет"))
    return head[0], head[1], lines


def report():
    parts = ["# ОТБОР ФОРМ (эксперимент поколений, FACTUM v1.1)\n",
             "Форма 𝔉 = единица отбора. Минимальный критерий: |𝔉|>=2 (сеянец жив).\n"
             "Отбор: максимум (strict-размер, размер); КОНТРОЛЬ: случайный из живых.\n"
             "Сеянец = копия формы родителя с шумом (mu=%.2f SKI; mu=%.2f+mu2=%.2f CHEM).\n"
             "Смерть породы = перезапуск от свежего мира.\n\n"
             "Якоря практики: минимальный критерий (Soros et al., ALIFE 2016), POET "
             "(Lehman, Stanley 2019), наследование копированием с шумом (Tierra, Ray 1992).\n\n"
             "SKI: M=%d, T=%d, K=%d поколений %d; CHEM: M=%d, T=%d, K=%d поколений %d, p=%.2f.\n"
             % (MU, MU, MU2, M_SKI, T_SKI, K, G_SKI, M_CHEM, T_CHEM, K, G_CHEM, P)]
    ds = load(SKI_STATE, None)
    if ds and ds["rows"]:
        h1, h2, lines = _ski_table(ds)
        parts.append("## SKI: форма -> сеянцы -> отбор\n\n" + h1 + "\n" + h2 + "\n"
                     + "\n".join(lines) + "\n\n"
                     + "Базовая линия свежих миров (тот же T): %s, мед. %.1f\n"
                     % (ds["baseline"], st.median(ds["baseline"]))
                     + "Смертей породы: отбор %d, контроль %d. Сеянцев всего: %d; "
                       "сеянцев со строгой формой: %d\n\n"
                     % (ds["deaths_s"], ds["deaths_c"], ds["seedlings"], ds["strict_hits"]))
    dc = load(CHEM_STATE, None)
    if dc and dc["rows"]:
        h1, h2, lines = _chem_table(dc)
        parts.append("## CHEM: та же процедура на строках (независимая реализация)\n\n"
                     + h1 + "\n" + h2 + "\n" + "\n".join(lines) + "\n\n"
                     + "Базовая линия свежих миров: %s\n" % (dc["baseline"],)
                     + "Смертей породы: отбор %d, контроль %d\n\n" % (dc["deaths_s"], dc["deaths_c"]))
    parts.append(_verdict(ds, dc))
    open(RESULTS, "w", encoding="utf-8").write("\n".join(parts))
    print("written:", RESULTS)


def _verdict(ds, dc):
    out = ["## Вердикт (по байтам)\n"]
    if ds and ds["rows"]:
        sel_next = [r["sel"]["next"] for r in ds["rows"]]
        ctl_next = [r["ctl"]["next"] for r in ds["rows"]]
        base_med = st.median(ds["baseline"])
        out.append("- SKI |F| линии: мед. отбора %.1f (последняя %d), контроль мед. %.1f "
                   "(последняя %d), базовая линия свежих миров мед. %.1f."
                   % (st.median(sel_next) if sel_next else 0, sel_next[-1] if sel_next else 0,
                      st.median(ctl_next) if ctl_next else 0, ctl_next[-1] if ctl_next else 0,
                      base_med))
        out.append("- SKI строгие формы: %d сеянцев из %d содержали строгую форму "
                   "(в статичном мире: 0/20)." % (ds["strict_hits"], ds["seedlings"]))
        out.append("- SKI смерти породы: отбор %d, контроль %d (критерий |F|>=2 жёсткий)."
                   % (ds["deaths_s"], ds["deaths_c"]))
    if dc and dc["rows"]:
        sel_next = [r["sel"]["next"] for r in dc["rows"]]
        ctl_next = [r["ctl"]["next"] for r in dc["rows"]]
        out.append("- CHEM |F| линии: мед. отбора %.1f, контроль мед. %.1f, "
                   "базовая линия %s; смерти: %d против %d."
                   % (st.median(sel_next) if sel_next else 0,
                      st.median(ctl_next) if ctl_next else 0, dc["baseline"],
                      dc["deaths_s"], dc["deaths_c"]))
    return "\n".join(out) + "\n"


def main():
    a = sys.argv[1].upper()
    if a == "SKI":
        cmd = sys.argv[2].upper()
        if cmd == "INIT":
            ski_init()
        elif cmd == "STEP":
            ski_step(int(sys.argv[3]))
        elif cmd == "REPORT":
            report()
        else:
            raise SystemExit("SKI INIT | SKI STEP n | SKI REPORT")
    elif a == "CHEM":
        chem_run()
    elif a == "REPORT":
        report()
    else:
        raise SystemExit("SKI INIT|STEP|REPORT, CHEM RUN, REPORT")
    print("PART DONE:", a)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ФАКТУМ — КОЭВОЛЮЦИЯ СРЕДЫ И ФОРМЫ (POET-стиль; открытый пункт §9 MODEL.md).

v1.1 показала (generations.py, GENERATIONS_RESULTS.md): форма — аттрактор
(0 смертей породы за 336 сеянцев в SKI+CHEM), но отбор размера не даёт подъёма
|𝔉| (SKI 4.5 против контроля 4.0; CHEM 18.5 против 20.0). §9 оставил открытым:
«условия подъёма: больший T, отбор по новизне/строгости, отбор среды вместе
с формой — POET-стиль». Этот скрипт закрывает третий пункт: СРЕДА — вторая
единица отбора, она наследуется (мутация генома) и отбирается вместе с формой.

Механика (геном = РЕАЛЬНЫЕ параметры конструктора chem.Chem):
  геном среды e = (p, ρ, L, T):
    p  — вероятность катализа (Chem(p=...)); 0.01 — мёртвая зона (CHEM_RESULTS.md);
    ρ  — приток еды (Chem(inflow=...)) — открытая система;
    L  — предел длины строк (Chem(L=...));
    T  — бюджет тиков Chem.run(T) — «перемешивание» среды (больший T — §9).
  Ёмкость M фиксирована (M=300 = M_CHEM generations.py): она задаёт размер мира,
  одинаковый для обеих линий, и в геном не входит.

Линия POET (коэволюция среды с формой):
  1. источник среды — СЛУЧАЙНАЯ пара (среда, форма) архива; среда-кандидат =
     мутация её генома гауссовым шумом (σ — доля диапазона каждого гена);
  2. сеянцы: K копий текущей формы с шумом копирования — та же процедура v1.1
     (MU=0.05, MU2=0.02, вызов generations.chem_seedling), каждый сеянец
     прокручивается в среде-кандидате T тиков;
  3. минимальный критерий: сеянец жив, если |𝔉|>=2 (Soros et al., ALIFE 2016);
  4. POET-критерий продвижения среды: контур жив И среда минимально-новая —
     нормированное евклидово расстояние генома до КАЖДОЙ архивированной среды
     >= theta (архив попарно разнесён — расширение без дубликатов);
  5. продвижение пишет пару (среда, форма) в архив; форма продолжает линию
     в любом случае (отбор лучшего живого сеянца, как в v1.1) — среда и форма
     поднимаются вместе, не порознь;
  6. смерть породы (все сеянцы мертвы) — перезапуск от свежего мира В ТОЙ ЖЕ
     предложенной среде (tries попыток), как «смерть породы» в v1.1.

КОНТРОЛЬ (тот же бюджет, случайные среды без селектора новизны):
  та же процедура (K сеянцев, тот же T, тот же перезапуск), но среда каждого
  поколения — СЛУЧАЙНАЯ точка генома (равномерно по диапазонам, без
  наследования), продвижение в архив — только по минимальному критерию
  (жива — значит в архив), БЕЗ проверки новизны. Единственная разница линий —
  селектор среды: наследование+новизна против случайного поиска.

Главный вопрос: даёт ли коэволюция подъём |𝔉| и/или расширение архива живых
сред против контроля? Меры: |𝔉| продолжающей формы, число живых сред в архиве,
покрытие генома (нормированный объём bbox архива в [0,1]^4).

Соты: POET_LOG.md — append-only, каждая строка данных несёт sha256 предыдущей
СЫРОЙ строки (12 hex); prev первой строки = sha256('POET')[:12]. Строки пишет
только автомат (ночной крон); в репозитории файл лежит с ТОЛЬКО шапкой.
Смоук-прогоны пишут в POET_LOG_smoke.md — репо-соты не засоряют.

Детерминизм: полный прогон с заданным --seed воспроизводим байт-в-байт
(кроме колонки UTC и prev, растущей из неё): сеянцы — seeds 100000*g+1000*line+17*k+5
(схема v1.1), предложения сред — rng от (seed, g), перезапуски — 9000+10*g (POET)
и 9500+10*g (контроль). organization() возвращает set — формы канонизованы sorted()
(иначе порядок зависел бы от хеш-сида Python; класс дефекта v0.4, MODEL.md §5).
Возобновление (state + тот же seed) тоже воспроизводимо.

Якоря практики: POET (Lehman, Stanley, GECCO 2019 — порождение задач вместе
с агентами), минимальный критерий (Soros, Cheney, Stanley, ALIFE 2016),
наследование копированием с шумом (Tierra, Ray 1992).

CLI:
  python3 poet.py                 # ночной прогон (по умолчанию: 30 поколений)
  python3 poet.py --smoke         # крошечные бюджеты: проверка петли, НЕ результат
  python3 poet.py --seed 20261125 --gens 10
  python3 poet.py --verify        # целость хеш-цепочки сот
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import random
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import chem as H
import generations as G          # chem_seedling: копия формы с шумом — процедура v1.1

ANCHOR = "POET"                  # якорь хеш-цепочки сот (как GENESIS/PULSE в репо)

JOURNAL_MAIN = os.path.join(HERE, "POET_LOG.md")
JOURNAL_SMOKE = os.path.join(HERE, "POET_LOG_smoke.md")
STATE_MAIN = os.path.join(HERE, "poet_state.json")
STATE_SMOKE = os.path.join(HERE, "poet_state_smoke.json")

# ---------- геном среды: реальные параметры chem.Chem ----------

GENES = ("p", "rho", "L", "T")
# Диапазоны по байтам CHEM_RESULTS.md (p=0.01 мертва, 0.12 — лучший режим) и
# GENERATIONS_RESULTS.md (T=20000); верх T — «больший T» из §9.
RANGES_NIGHT = {"p": (0.02, 0.15), "rho": (0.0, 0.30), "L": (4, 8), "T": (10000, 40000)}
# Смоук: только проверка петли (минуты); p не ниже 0.05, чтобы живые контуры
# гарантированно встречались при крошечных T — ЧИСЛА СМОУКА НЕ РЕЗУЛЬТАТ.
RANGES_SMOKE = {"p": (0.05, 0.15), "rho": (0.05, 0.25), "L": (5, 7), "T": (1200, 2600)}

BASE_ENV = {"p": 0.12, "rho": 0.1, "L": 6, "T": 20000}   # лучший режим CHEM_RESULTS.md

NIGHT_DEFS = {"gens": 30, "K": 4, "theta": 0.18, "sigma": 0.18, "tries": 5}
SMOKE_DEFS = {"gens": 4, "K": 2, "theta": 0.30, "sigma": 0.25, "tries": 3}


# ---------- метрики генома: новизна и покрытие ----------

def norm_env(env, ranges):
    """Геном -> нормированный вектор [0,1]^4 (метрика новизны без размерностей)."""
    return tuple((env[g] - ranges[g][0]) / (ranges[g][1] - ranges[g][0]) for g in GENES)


def env_dist(e1, e2, ranges):
    """Евклидово расстояние между геномами в нормированном пространстве."""
    a, b = norm_env(e1, ranges), norm_env(e2, ranges)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def mutate_env(env, rng, ranges, sigma):
    """Среда-потомок: гауссов шум по каждому гену (sigma — доля диапазона), кламп."""
    e = {}
    for g in GENES:
        lo, hi = ranges[g]
        v = env[g] + rng.gauss(0.0, sigma * (hi - lo))
        e[g] = int(round(clamp(v, lo, hi))) if g in ("L", "T") else round(clamp(v, lo, hi), 4)
    return e


def rand_env(rng, ranges):
    """Случайная среда КОНТРОЛЯ: равномерная точка генома, без наследования."""
    e = {}
    for g in GENES:
        lo, hi = ranges[g]
        v = lo + rng.random() * (hi - lo)
        e[g] = int(round(v)) if g in ("L", "T") else round(v, 4)
    return e


def env_str(e):
    return "p=%.3f/ρ=%.3f/T=%d/L=%d" % (e["p"], e["rho"], e["T"], e["L"])


def is_novel(env, archive, ranges, theta):
    """Минимально-новая: расстояние до КАЖДОЙ архивированной среды >= theta."""
    return all(env_dist(env, pr["env"], ranges) >= theta for pr in archive)


def bbox_volume(archive, ranges):
    """Покрытие генома архивом: нормированный объём bbox в [0,1]^4 (0 — одна точка)."""
    if len(archive) < 2:
        return 0.0
    vol = 1.0
    for g in GENES:
        vs = [pr["env"][g] for pr in archive]
        lo, hi = ranges[g]
        vol *= clamp((max(vs) - min(vs)) / (hi - lo), 0.0, 1.0)
    return vol


# ---------- миры: реальный код chem.py ----------

def run_world(env, seed, w0=None):
    """Прокрутить мир chem.py в среде env. w0 — посев формой (как в chem_litter v1.1)."""
    c = H.Chem(seed=seed, p=env["p"], L=env["L"], inflow=env["rho"], memory=True)
    if w0 is not None:
        c.W = w0                     # тот же приём, что в generations.chem_litter
    c.run(env["T"])
    return c


def seedling_w0(form, seed):
    """Посев: копия формы с шумом копирования (MU=0.05, MU2=0.02 — процедура v1.1)."""
    return G.chem_seedling(form, random.Random(seed))


def litter(form, env, g, line, K):
    """K сеянцев формы в среде env. -> (список |𝔉|, лучшая живая форма или None)."""
    sizes, best = [], None
    for k in range(K):
        seed = 100000 * g + 1000 * line + 17 * k + 5   # та же схема seeds, что в v1.1
        f = sorted(run_world(env, seed, seedling_w0(form, seed)).organization())
        sizes.append(len(f))
        if len(f) >= 2 and (best is None or len(f) > len(best)):
            best = f
    return sizes, best


def fresh_form(env, seed_start, tries):
    """Перезапуск породы: первый свежий мир среды env с живой формой (|𝔉|>=2)."""
    for s in range(tries):
        f = sorted(run_world(env, seed_start + s).organization())
        if len(f) >= 2:
            return f
    return None


# ---------- соты: POET_LOG.md (append-only, prev = sha256 сырой строки) ----------

def line_hash(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


HEADER = (
    "# ЖУРНАЛ КОЭВОЛЮЦИИ СРЕДЫ И ФОРМЫ (append-only; POET-стиль, §9 MODEL.md)\n"
    "\n"
    "Соты: факт = строка. Каждая строка данных несёт sha256 предыдущей СЫРОЙ строки\n"
    "(колонка prev, первые 12 hex); для первой строки prev = sha256('POET')[:12].\n"
    "Подмена любой строки ловится СЛЕДУЮЩЕЙ строкой (и коммитом git — внешний якорь):\n"
    "проверка `python3 poet.py --verify`. Строки пишет автомат poet.py (ночной крон\n"
    "poet.yml); в репозитории файл лежит с ТОЛЬКО шапкой, без строк данных.\n"
    "Смоук-прогоны (`--smoke`) идут в POET_LOG_smoke.md и в эти соты не попадают.\n"
    "\n"
    "Колонки: среда — геном среды-кандидата линии POET (p — катализ, ρ — приток еды,\n"
    "T — тики, L — предел длины строк: параметры chem.py); |F| лучшей — размер формы,\n"
    "продолжающей линию (лучшая живая из сеянцев; при смерти породы — из перезапуска\n"
    "от свежего мира); живых сред — размер архива пар (среда, форма) линии POET;\n"
    "контроль — живых_сред/|F| линии КОНТРОЛЯ (случайные среды без селектора\n"
    "новизны, тот же бюджет); вердикт: ПРОДВИНУТА — среда жива И минимально-нова\n"
    "(пара в архиве), ЖИВАЯ — жива, но не нова (мимо архива), ТИШИНА — контур не\n"
    "поднялся даже от перезапуска; «·перезапуск» — порода умерла в этом поколении.\n"
    "\n"
    "| # | UTC | поколение | среда(p,T) | \\|F\\| лучшей | живых сред | контроль | вердикт | prev |\n"
    "|---|---|---|---|---|---|---|---|---|\n"
)


def data_rows(text):
    return [l for l in text.splitlines() if l.startswith("| ") and not l.startswith("| #")]


def read_raws(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return data_rows(f.read())


def verify_journal(path):
    """Цепочка: prev[i] == line_hash(сырой строки i-1); prev[0] == line_hash('POET')."""
    raws = read_raws(path)
    prev_raw = ANCHOR
    for i, row in enumerate(raws):
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) != 9:
            return False, i + 1, "строка %d: %d колонок вместо 9" % (i + 1, len(cells))
        if cells[-1] != line_hash(prev_raw):
            return False, i + 1, "строка %d: хеш-цепочка порвана" % (i + 1)
        prev_raw = row
    return True, len(raws), "цепочка цела"


def append_row(path, cells):
    """Ячейка сот: prev = sha256 предыдущей СЫРОЙ строки; первая — от якоря 'POET'."""
    raws = read_raws(path)
    prev = line_hash(raws[-1]) if raws else line_hash(ANCHOR)
    num = int(raws[-1].strip().strip("|").split("|")[0]) + 1 if raws else 1
    row = "| " + " | ".join([str(num)] + cells + [prev]) + " |"
    if not raws:
        with open(path, "w", encoding="utf-8") as f:
            f.write(HEADER)
    with open(path, "a", encoding="utf-8") as f:      # только append, никогда не вперёд
        f.write(row + "\n")
    return row


# ---------- состояние (архив пар среда+форма переживает крон-запуски) ----------

def load_state(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_state(path, d):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)


def init_state(seed, params):
    """f0 в базовой среде (p=0.12, ρ=0.1 — лучший режим CHEM_RESULTS.md); обе линии от него."""
    f0 = None
    for s in range(20):
        # sorted: organization() возвращает set, порядок list() зависел бы от хеш-сида
        # Python (класс дефекта v0.4, фикс в MODEL.md §5) — канонизуем порядок формы
        f = sorted(run_world(BASE_ENV, 777 + s).organization())
        if len(f) >= 2:
            f0 = f
            break
    assert f0, "f0 не найден за 20 попыток в базовой среде"
    pair0 = {"env": dict(BASE_ENV), "form": f0, "f": len(f0), "born_g": None}
    return {
        "version": "poet/v1.0",
        "seed": seed,
        "g": 0,
        "archive": [pair0],            # архив пар (среда, форма) линии POET
        "ctl_archive": [dict(pair0)],  # архив линии КОНТРОЛЯ
        "form_cur": f0,                # текущая форма линии POET (единица отбора формы)
        "form_ctl": f0,                # текущая форма контроля
        "deaths_s": 0,                 # смертей породы (перезапусков) POET
        "deaths_c": 0,                 # смертей породы контроля
        "hist_s": [],                  # |𝔉| продолжающей формы POET по поколениям
        "hist_c": [],                  # то же для контроля
        "params": params,
    }


def final_verdict(d, ranges):
    """Сводка: подъём |𝔉| и расширение архива живых сред против контроля."""
    hs, hc = d["hist_s"], d["hist_c"]
    # средний T архива: сравнение |𝔉| линий смещено распределением T (контроль
    # сэмплирует T равномерно, POET наследует T) — оговорка должна быть измеримой
    mt = lambda arch: sum(pr["env"]["T"] for pr in arch) / len(arch) if arch else 0.0
    return {
        "gens": len(hs),
        "med_f_poet": st.median(hs) if hs else 0.0,
        "med_f_ctl": st.median(hc) if hc else 0.0,
        "max_f_poet": max(hs) if hs else 0,
        "max_f_ctl": max(hc) if hc else 0,
        "live_envs_poet": len(d["archive"]),
        "live_envs_ctl": len(d["ctl_archive"]),
        "bbox_poet": round(bbox_volume(d["archive"], ranges), 4),
        "bbox_ctl": round(bbox_volume(d["ctl_archive"], ranges), 4),
        "mean_t_poet": round(mt(d["archive"]), 1),
        "mean_t_ctl": round(mt(d["ctl_archive"]), 1),
        "deaths_poet": d["deaths_s"],
        "deaths_ctl": d["deaths_c"],
    }


def print_verdict(v, smoke):
    print("-- СВОДКА ПРОГОНА %s--" % ("(СМОУК: проверка механизма, НЕ научный результат) " if smoke else ""))
    print("|F| линии: мед. POET %.1f против контроля %.1f (макс %d против %d)"
          % (v["med_f_poet"], v["med_f_ctl"], v["max_f_poet"], v["max_f_ctl"]))
    print("живых сред в архиве: POET %d против контроля %d; покрытие bbox: %.3f против %.3f"
          % (v["live_envs_poet"], v["live_envs_ctl"], v["bbox_poet"], v["bbox_ctl"]))
    print("средний T архива: POET %.0f против контроля %.0f (оговорка сравнения |F|)"
          % (v["mean_t_poet"], v["mean_t_ctl"]))
    print("смертей породы (перезапусков): POET %d, контроль %d" % (v["deaths_poet"], v["deaths_ctl"]))


# ---------- основной цикл коэволюции ----------

def run(args, journal, state):
    ranges = RANGES_SMOKE if args.smoke else RANGES_NIGHT
    defs = dict(SMOKE_DEFS if args.smoke else NIGHT_DEFS)
    params = {
        "gens": args.gens if args.gens is not None else defs["gens"],
        "K": args.k if args.k is not None else defs["K"],
        "theta": args.theta if args.theta is not None else defs["theta"],
        "sigma": args.sigma if args.sigma is not None else defs["sigma"],
        "tries": args.tries if args.tries is not None else defs["tries"],
        "ranges": {g: list(ranges[g]) for g in GENES},
    }
    # seed: как у сердца (factum.py) — UTC-дата; с заданным --seed прогон воспроизводим
    seed = args.seed if args.seed is not None else int(
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d"))
    params["seed"] = seed

    d = load_state(state)
    if d is None:
        d = init_state(seed, params)
        print("f0: |F|=%d; базовая среда %s; режим %s"
              % (len(d["form_cur"]), env_str(BASE_ENV), "СМОУК" if args.smoke else "НОЧЬ"))
    d["params"] = params             # параметры последнего запуска (прозрачность)

    K, theta, sigma, tries = params["K"], params["theta"], params["sigma"], params["tries"]

    for _ in range(params["gens"]):
        g = d["g"]

        # ---- линия POET: среда-потомок от случайной пары архива ----
        rng_g = random.Random((seed * 1000003 + g) & 0xFFFFFFFF)
        src = d["archive"][rng_g.randrange(len(d["archive"]))]   # источник среды — архивная пара
        env2 = mutate_env(src["env"], rng_g, ranges, sigma)      # среда наследуется и мутирует
        sizes, best = litter(d["form_cur"], env2, g, line=0, K=K)
        died = best is None
        if died:
            d["deaths_s"] += 1
            best = fresh_form(env2, 9000 + 10 * g, tries)        # перезапуск В предложенной среде
        promoted = False
        if best is not None:
            promoted = is_novel(env2, d["archive"], ranges, theta)   # POET-критерий: жив И минимально-нов
            if promoted:
                d["archive"].append({"env": env2, "form": best, "f": len(best), "born_g": g})
            d["form_cur"] = best     # форма продолжается: отбор лучшего сеянца (как v1.1)
        f_s = len(best) if best is not None else 0
        d["hist_s"].append(f_s)
        verdict = "ТИШИНА" if best is None else ("ПРОДВИНУТА" if promoted else "ЖИВАЯ")
        if died:
            verdict += " ·перезапуск"

        # ---- линия КОНТРОЛЯ: случайная среда, продвижение без селектора новизны ----
        rng_c = random.Random((seed * 1000003 + g + 777) & 0xFFFFFFFF)
        env2c = rand_env(rng_c, ranges)
        sizes_c, best_c = litter(d["form_ctl"], env2c, g, line=1, K=K)
        died_c = best_c is None
        if died_c:
            d["deaths_c"] += 1
            best_c = fresh_form(env2c, 9500 + 10 * g, tries)
        if best_c is not None:
            # жива — значит в архив: НИКАКОЙ проверки новизны (селектор среды выключен)
            d["ctl_archive"].append({"env": env2c, "form": best_c, "f": len(best_c), "born_g": g})
            d["form_ctl"] = best_c
        f_c = len(best_c) if best_c is not None else 0
        d["hist_c"].append(f_c)

        row = append_row(journal, [utc_now(), str(g), env_str(env2), str(f_s),
                                   str(len(d["archive"])),
                                   "%d/%d" % (len(d["ctl_archive"]), f_c),
                                   verdict])
        print("gen %d: POET %s сеянцы=%s |F|=%d живых=%d [%s] | КОНТРОЛЬ живых=%d |F|=%d%s"
              % (g, env_str(env2), sizes, f_s, len(d["archive"]), verdict,
                 len(d["ctl_archive"]), f_c, " (перезапуск)" if died_c else ""))
        d["g"] = g + 1
        save_state(state, d)         # состояние после каждого поколения (крон может умереть)

    v = final_verdict(d, ranges)
    d["verdict"] = v
    save_state(state, d)
    print_verdict(v, args.smoke)
    print("соты: %s (+%d строк); состояние: %s" % (journal, params["gens"], state))


def main():
    ap = argparse.ArgumentParser(
        description="ФАКТУМ — коэволюция среды и формы (POET-стиль, §9 MODEL.md)")
    ap.add_argument("--smoke", action="store_true",
                    help="крошечные бюджеты: проверка петли (минуты), НЕ научный результат")
    ap.add_argument("--seed", type=int, default=None,
                    help="seed (по умолчанию UTC-дата; с заданным seed прогон воспроизводим)")
    ap.add_argument("--gens", type=int, default=None,
                    help="поколений в этом запуске (ночь: %d, смоук: %d)"
                         % (NIGHT_DEFS["gens"], SMOKE_DEFS["gens"]))
    ap.add_argument("--k", type=int, default=None,
                    help="сеянцев на породу (ночь: %d, смоук: %d)"
                         % (NIGHT_DEFS["K"], SMOKE_DEFS["K"]))
    ap.add_argument("--theta", type=float, default=None,
                    help="порог новизны среды (норм. евклидово расстояние; ночь: %.2f, смоук: %.2f)"
                         % (NIGHT_DEFS["theta"], SMOKE_DEFS["theta"]))
    ap.add_argument("--sigma", type=float, default=None,
                    help="сила шума среды, доля диапазона гена (ночь: %.2f, смоук: %.2f)"
                         % (NIGHT_DEFS["sigma"], SMOKE_DEFS["sigma"]))
    ap.add_argument("--tries", type=int, default=None,
                    help="попыток перезапуска от свежего мира при смерти породы (ночь: %d, смоук: %d)"
                         % (NIGHT_DEFS["tries"], SMOKE_DEFS["tries"]))
    ap.add_argument("--journal", default=None,
                    help="путь к сотам (по умолчанию POET_LOG.md; в смоук POET_LOG_smoke.md)")
    ap.add_argument("--state", default=None,
                    help="путь к состоянию архива (poet_state.json / poet_state_smoke.json)")
    ap.add_argument("--verify", action="store_true", help="проверить хеш-цепочку сот и выйти")
    a = ap.parse_args()

    if a.verify:
        path = a.journal or (JOURNAL_SMOKE if a.smoke else JOURNAL_MAIN)
        ok, n, msg = verify_journal(path)
        print("POET_LOG: %d строк данных; %s" % (n, msg))
        sys.exit(0 if ok else 1)

    # смоук никогда не пишет в репо-соты: путь по умолчанию подменяется на *_smoke
    journal = a.journal or (JOURNAL_SMOKE if a.smoke else JOURNAL_MAIN)
    state = a.state or (STATE_SMOKE if a.smoke else STATE_MAIN)
    run(a, journal, state)
    print("PART DONE: POET")


if __name__ == "__main__":
    main()

"""
ЭКСПЕРИМЕНТ v0.4 §1: SKI против BCI (линейный базис) — проверка гипотезы 5.2 v0.3
«форма возникает, когда ⋆ не вырождается в проекцию».

Запуск частями (каждая укладывается в лимит времени инструмента):
  python3 linear_experiment.py SKI       # таблица 1, движок SKI (режимы v0.3, 20 seed, T=3000)
  python3 linear_experiment.py BCI       # таблица 1, движок BCI
  python3 linear_experiment.py DIAG      # диагностика отказов ⋆ (оба движка, 3 открытых мира)
Результат: LINEAR_RESULTS.md (собирается из частей, инкрементально).
"""
import statistics as st
import sys
import json
import os
import emergent as E
import bci as L

sys.setrecursionlimit(200000)

T = 3000
MODES = [("открытая, память ВКЛ", 0.5, True),
         ("открытая, память ВЫКЛ", 0.5, False),
         ("закрытая, память ВЫКЛ", 0.0, False)]
STATE = 'linear_state.json'


def load():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"rows": [], "rows2": [], "done": []}


def save(st_):
    json.dump(st_, open(STATE, 'w'))


def dump(st_):
    hdr = ["| движок | режим | доля с формой (обычная) | мед. |F| | доля с формой (strict) | мед. |F| strict | мед. типов | доля определённых звёзд | N1 | N2 | N3 |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    hdr2 = ["| движок | отказов при budget(150,50) | проверено больших бюджетом | сошлись | истинных несхождений |",
            "|---|---|---|---|---|"]
    open('LINEAR_RESULTS.md', 'w').write(
        "# SKI против BCI (20 seed, T=3000; режимы redteam1 v0.3)\n\n"
        "BCI = линейная комбинаторная логика: B f g x = f (g x), C f g x = f x g, I x = x.\n"
        "K (отмена) и S (дублирование) выброшены. Доля определённых звёзд = defined/attempts.\n\n"
        + "\n".join(hdr + st_["rows"]) + "\n\n"
        "## Диагностика неопределённых звёзд: бюджет или истинное несхождение?\n\n"
        "Отказавшие пары (fuel=150, size=50) пересчитаны с fuel=10^5, size=10^4.\n"
        "Диагностика: 3 открытых мира (seed 1-3), T=3000, максимум 400 отказавших пар на движок.\n"
        "Истинное несхождение = не сошлось даже при большом бюджете (в SKI это S-циклы и раздувание дерева;\n"
        "RecursionError при подсчёте размера классифицируется как раздувание).\n\n"
        + "\n".join(hdr2 + st_["rows2"]) + "\n")


def big_app(mod, a, b):
    try:
        return mod.app(a, b, 10 ** 5, 10 ** 4)
    except RecursionError:
        return None


def table(engine):
    st_ = load()
    if engine in st_["done"]:
        print("already done:", engine); return
    mod = E if engine == "SKI" else L
    for name, inf, mem in MODES:
        fn, fs, ty, df, n1, n2, n3 = [], [], [], [], [], [], []
        for sd in range(1, 21):
            w = mod.World(seed=sd, inflow=inf, memory=mem).run(T)
            fn.append(len(w.organization()))
            fs.append(len(w.organization(strict=True)))
            ty.append(len(set(w.W)))
            df.append(w.defined / w.attempts)
            nv = mod.novelty_vector(w)
            n1.append(nv[1]); n2.append(nv[2]); n3.append(nv[3])
        st_["rows"].append(f"| {engine} | {name} | {sum(x >= 2 for x in fn)}/20 | {st.median(fn)} | "
                           f"{sum(x >= 2 for x in fs)}/20 | {st.median(fs)} | {st.median(ty)} | "
                           f"{st.median(df):.2f} | {st.median(n1)} | {st.median(n2)} | {st.median(n3)} |")
        print(st_["rows"][-1], flush=True)
    st_["done"].append(engine)
    save(st_); dump(st_)


def diag():
    st_ = load()
    if "DIAG" in st_["done"]:
        print("already done: DIAG"); return
    for engine in ("SKI", "BCI"):
        mod = E if engine == "SKI" else L
        nfail = 0; nconv = 0; nchecked = 0
        for sd in (1, 2, 3):
            w = mod.World(seed=sd, inflow=0.5, memory=True)
            for _ in range(T):
                a, b = w.rng.choice(w.W), w.rng.choice(w.W)
                r = mod.app(a, b, w.fuel, w.max_size)
                w.t += 1; w.attempts += 1
                if r is None:
                    nfail += 1
                    if nfail <= 400:
                        nchecked += 1
                        if big_app(mod, a, b) is not None:
                            nconv += 1
                    continue
                w.defined += 1
                w.credit[r] += 1
                w.W[w.rng.choices(range(w.M), weights=[1.0 / (1 + w.credit[x]) if w.memory else 1.0 for x in w.W])[0]] = r
                if w.rng.random() < w.inflow:
                    w.W[w.rng.randrange(w.M)] = mod.rand_term(w.inflow_rng, 2)
        st_["rows2"].append(f"| {engine} | {nfail} | {nchecked} | {nconv} | {nchecked - nconv} |")
        print(st_["rows2"][-1], flush=True)
    st_["done"].append("DIAG")
    save(st_); dump(st_)


if __name__ == '__main__':
    arg = sys.argv[1].upper()
    if arg == 'DIAG':
        diag()
    else:
        table(arg)
    print("PART DONE:", arg)

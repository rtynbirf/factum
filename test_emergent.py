import emergent as E

def test_reducer():
    assert E.app('I', 'K') == 'K'
    assert E.app(('K', 'S'), 'I') == 'S'
    # S K K x = x
    assert E.reduce_(((( 'S','K'),'K'),'I')) == 'I'

def test_comp_semantics():
    for a, b in [('I','K'), (('K','S'),'I'), (('S','K'),'K')]:
        for z in E.PROBES:
            inner = E.app(b, z); 
            left = E.app(E.comp(a, b), z)
            right = None if inner is None else E.app(a, inner)
            assert left == right

def test_no_new_symbols():          # N4 = ΔΣ = 0 (граница формализации, S4-b)
    w = E.World(seed=1).run(1500)
    assert w.sigma_used() <= {'S','K','I'}

def test_determinism():
    a = E.World(seed=7, inflow=0.5).run(800); b = E.World(seed=7, inflow=0.5).run(800)
    assert a.W == b.W

def test_path_dependence():         # одно W0, разные истории -> разные формы
    w0 = E.World(seed=0).W
    a = E.World(seed=1, w0=w0, inflow=0.5).run(2500); b = E.World(seed=2, w0=w0, inflow=0.5).run(2500)
    assert set(a.W) != set(b.W)

def test_closure_theorem():         # S5-b: любой результат ∈ Cl(S,K,I)
    w = E.World(seed=3).run(1200)
    assert all(E.symbols(x) <= {'S','K','I'} for _, x, _ in w.events)

def test_org_is_self_producing():
    w = E.World(seed=4, inflow=0.5).run(2500)
    X = w.organization()
    P = set()
    for a in X:
        for b in X:
            r = E.app(a, b)
            if r is not None: P.add(r)
    assert X <= P

def test_closed_system_collapses():   # без притока — монокультура (контроль «ограничение без порождения»)
    w = E.World(seed=1, inflow=0.0).run(3000)
    assert len(set(w.W)) <= 3

def test_open_system_has_organization():
    ok = sum(1 for sd in range(1, 6) if len(E.World(seed=sd, inflow=0.5).run(3000).organization()) >= 2)
    assert ok >= 3

# ---- реакционная сеть ----
import chem

def test_chem_determinism():
    a = chem.Chem(seed=3, p=0.05).run(20000); b = chem.Chem(seed=3, p=0.05).run(20000)
    assert a.W == b.W

def test_chem_no_catalysis_no_novelty():     # без катализа новых видов нет
    c = chem.Chem(seed=1, p=0.0).run(30000)
    assert c.new == 0 and len(c.organization()) == 0

def test_chem_threshold_monotone():          # форма чаще при высоком катализе
    lo = sum(len(chem.Chem(seed=s, p=0.01).run(60000).organization()) >= 2 for s in range(1, 9))
    hi = sum(len(chem.Chem(seed=s, p=0.12).run(60000).organization()) >= 2 for s in range(1, 9))
    assert hi > lo

def test_chem_alphabet_closed():             # ΔΣ=0: только символы 0/1
    c = chem.Chem(seed=2, p=0.08).run(40000)
    assert all(set(x) <= {'0', '1'} for x in c.seen)

def test_ski_forms_are_projections():          # красная проверка: строгая форма в SKI отсутствует
    n = sum(len(E.World(seed=s, inflow=0.5).run(2000).organization(strict=True)) >= 2 for s in range(1, 6))
    assert n == 0

def test_chem_strict_form_exists():            # а в сети строгая форма есть
    n = sum(len(chem.Chem(seed=s, p=0.12).run(100000).organization(cleave=False)) >= 2 for s in range(1, 6))
    assert n >= 3

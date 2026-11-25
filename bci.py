"""
EMERGENT CORE v0.4 — линейный мир BCI (эксперимент §5.2 MODEL.md v0.3).

Гипотеза v0.3 (п.5.2): форма возникает, когда ⋆ не вырождается в проекцию.
SKI это опровергает сам себя: K и I — проекции, S — дублирование аргумента.
Линейный базис BCI = {B, C, I} (линейная комбинаторная логика):
  B f g x = f (g x)        композиция: все аргументы использованы ровно один раз
  C f g x = f x g          перестановка: все аргументы использованы ровно один раз
  I x = x                  тождество (ЕДИНСТВЕННАЯ оставшаяся проекция)
Отброшены: K (отмена аргумента) и S (дублирование аргумента).
Следствие теории (проверено кодом в тестах): в BCI невозможно самоприменение
(нельзя использовать терм дважды), значит нет неподвижных точек и циклов —
редукция всегда останавливается, ⋆ тотален. Это проверяется счётчиком
attempts/defined: доля определённых применений должна быть 1.00.

Та же динамика, что и в SKI-мире (emergent.py v0.4): kappa, память, приток,
gfp-форма с strict-критерием (результат не подтерм реагентов).
"""
import random
from collections import defaultdict

PROBES = ['B', 'C', 'I', ('B', 'I'), ('C', 'I'), ('B', 'C'), ('C', 'B'), (('B', 'C'), 'I')]


def size(t):
    return 1 if isinstance(t, str) else size(t[0]) + size(t[1])


def step(t):
    """Один шаг редукции линейных комбинаторов; None — нормальная форма."""
    if isinstance(t, str):
        return None
    a, b = t
    if a == 'I':                          # I x → x  (проекция; x использован один раз)
        return b
    if isinstance(a, tuple):
        h = a[0]
        if isinstance(h, tuple) and h[0] == 'B':   # B f g x → f (g x)
            return (h[1], (a[1], b))
        if isinstance(h, tuple) and h[0] == 'C':   # C f g x → f x g
            return ((h[1], b), a[1])
    r = step(a)
    if r is not None:
        return (r, b)
    r = step(b)
    if r is not None:
        return (a, r)
    return None


def reduce_(t, fuel=150, max_size=50):
    """Нормальная форма за бюджет fuel; None если не остановилось/раздулось."""
    for _ in range(fuel):
        n = step(t)
        if n is None:
            return t
        t = n
        if size(t) > max_size:
            return None
    return None


def app(a, b, fuel=150, max_size=50):
    return reduce_((a, b), fuel, max_size)   # допустимость = остановка (имманентно)


def comp(a, b):
    return (('B', a), b)                     # comp(a,b) z = a(b z)


def rand_term(rng, depth):
    if depth == 0 or rng.random() < 0.25:
        return rng.choice('BCI')
    return (rand_term(rng, depth - 1), rand_term(rng, depth - 1))


_SIG = {}


def set_probes(p):
    global PROBES
    PROBES = list(p); _SIG.clear()


def contains(t, x):
    return t == x or (isinstance(t, tuple) and (contains(t[0], x) or contains(t[1], x)))


def sig(x):
    v = _SIG.get(x)
    if v is None:
        v = _SIG[x] = tuple(app(x, p) for p in PROBES)
    return v


def symbols(t, acc=None):
    acc = set() if acc is None else acc
    if isinstance(t, str):
        acc.add(t)
    else:
        symbols(t[0], acc); symbols(t[1], acc)
    return acc


class World:
    """Та же динамика kappa/память/приток, что и в emergent.World v0.4."""
    def __init__(self, seed=0, M=150, depth=3, w0=None, fuel=150, max_size=50, inflow=0.05, memory=True, cap=70):
        self.rng = random.Random(seed)
        self.M, self.fuel, self.max_size, self.inflow = M, fuel, max_size, inflow
        self.inflow_rng = random.Random(999 + seed)
        self.memory = memory
        self.cap = cap
        r0 = random.Random(12345) if w0 is None else None
        self.W = list(w0) if w0 is not None else [rand_term(r0, depth) for _ in range(M)]
        self.credit = defaultdict(int)
        self.seen = set(self.W)
        self.seen_sigs = set(); self.reps = []
        self.compsigs = set()
        self.t = 0
        self.events = []
        self.attempts = 0
        self.defined = 0
        seen0 = []                            # детерминизм: порядок первого вхождения
        for x in self.W:
            if x not in seen0:
                seen0.append(x)
        for x in seen0:
            self._register(x)

    def _register(self, x, cap=None):
        cap = self.cap if cap is None else cap
        s = sig(x)
        if s in self.seen_sigs:
            return
        self.seen_sigs.add(s)
        if cap is not None and len(self.reps) >= cap:
            return
        for r in self.reps:
            self.compsigs.add(sig(comp(x, r)))
            self.compsigs.add(sig(comp(r, x)))
        self.compsigs.add(sig(comp(x, x)))
        self.reps.append(x)

    def level(self, x):
        if x in self.seen:
            return 0
        s = sig(x)
        if s in self.seen_sigs:
            return 1
        if s in self.compsigs:
            return 2
        return 3

    def tick(self):
        a, b = self.rng.choice(self.W), self.rng.choice(self.W)
        r = app(a, b, self.fuel, self.max_size)
        self.t += 1
        self.attempts += 1
        if r is None:
            return None
        self.defined += 1
        self.credit[r] += 1
        lv = self.level(r)
        if lv > 0:
            self.seen.add(r)
            self._register(r)
            self.events.append((self.t, r, lv))
        w = [1.0 / (1 + self.credit[x]) if self.memory else 1.0 for x in self.W]
        i = self.rng.choices(range(self.M), weights=w)[0]
        self.W[i] = r
        if self.rng.random() < self.inflow:
            j = self.rng.randrange(self.M)
            fresh = rand_term(self.inflow_rng, 2)
            self.W[j] = fresh
            if fresh not in self.seen:
                self.seen.add(fresh); self._register(fresh)
        return r

    def run(self, T):
        for _ in range(T):
            self.tick()
        return self

    def organization(self, cap=60, strict=False):
        """F = gfp{X⊆types : X⊆X·X}; strict: результат не подтерм реагентов."""
        cnt = defaultdict(int)
        for x in self.W:
            cnt[x] += 1
        types = [x for x, _ in sorted(cnt.items(), key=lambda kv: -kv[1])][:cap]
        prod = {}
        for a in types:
            for b in types:
                r = app(a, b, self.fuel, self.max_size)
                if r is not None:
                    prod[(a, b)] = r
        X = set(types)
        while True:
            P = {prod[(a, b)] for a in X for b in X if (a, b) in prod and prod[(a, b)] not in (a, b)
                 and not (strict and (contains(a, prod[(a, b)]) or contains(b, prod[(a, b)])))}
            Y = X & P
            if Y == X:
                return X
            X = Y

    def sigma_used(self):
        s = set()
        for x in self.seen:
            symbols(x, s)
        return s


def novelty_vector(world):
    v = [0, 0, 0, 0]
    for _, _, lv in world.events:
        v[lv] += 1
    return v

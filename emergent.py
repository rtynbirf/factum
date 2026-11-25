"""
EMERGENT CORE v0.4 — SKI-мир. Изменения против v0.3:
  1. Детерминированная регистрация представителей при инициализации
     (v0.3 регистрировал `for x in set(W)` — порядок зависел от хеш-сида
     Python, из-за чего N2/N3 плавали между запусками; найдено верификацией).
  2. cap=None разрешён: Cl₁ строится по ВСЕМ представителям без предела
     (определение новизны без cap — открытый пункт §8 v0.3).

Один тип объектов: термы над {S,K,I} (комбинаторная логика).
Элемент = операция (терм a применим к терму b). Нет отдельных уровней C/T/G.
  W_{t+1} = kappa( W_t ∪ { a·b : a,b∈W_t, a·b halts in fuel } | H_t )
  H_{t+1} = H_t ⊕ W_{t+1}     (память входит в динамику: защита воспроизводимого)
  F_t     = gfp{ X⊆W_t : ∀x∈X ∃a,b∈X: a·b=x, x∉{a,b} }  (форма = коллективное самопроизводство)
  E(t)    = вектор новизны (N0..N3), N4 = ΔΣ (=0 по построению, см. тесты)
"""
import random
from collections import defaultdict

PROBES = ['S', 'K', 'I', ('K', 'I'), ('S', 'K'), ('S', 'I'), ('K', 'K'), (('S', 'K'), 'K')]

def size(t):
    return 1 if isinstance(t, str) else size(t[0]) + size(t[1])

def step(t):
    if isinstance(t, str):
        return None
    f, x = t
    if f == 'I':
        return x
    if isinstance(f, tuple):
        if f[0] == 'K':
            return f[1]
        if isinstance(f[0], tuple) and f[0][0] == 'S':
            return ((f[0][1], x), (f[1], x))
    r = step(f)
    if r is not None:
        return (r, x)
    r = step(x)
    if r is not None:
        return (f, r)
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
    return (('S', ('K', a)), b)              # comp(a,b) z = a(b z)

def rand_term(rng, depth):
    if depth == 0 or rng.random() < 0.25:
        return rng.choice('SKI')
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
    def __init__(self, seed=0, M=150, depth=3, w0=None, fuel=150, max_size=50, inflow=0.05, memory=True, cap=70):
        self.rng = random.Random(seed)
        self.M, self.fuel, self.max_size, self.inflow = M, fuel, max_size, inflow
        self.inflow_rng = random.Random(999 + seed)
        self.memory = memory
        self.cap = cap
        r0 = random.Random(12345) if w0 is None else None
        self.W = list(w0) if w0 is not None else [rand_term(r0, depth) for _ in range(M)]
        self.credit = defaultdict(int)        # часть H: сколько раз терм воспроизведён
        self.seen = set(self.W)               # история элементов
        self.seen_sigs = set(); self.reps = []
        self.compsigs = set()
        self.t = 0
        self.events = []                      # (t, term, level)
        self.attempts = 0                     # попытки применения (для доли определённых)
        self.defined = 0
        seen0 = []
        for x in self.W:                      # ДЕТЕРМИНИЗМ: порядок первого вхождения в W,
            if x not in seen0:                # не порядок итерации множества (фикс v0.4)
                seen0.append(x)
        for x in seen0:
            self._register(x)

    def _register(self, x, cap=None):
        """Представители = по одному на различное поведение. Cl₁ строится по ним.
        cap=None (v0.4) = без предела: определение новизны не зависит от cap."""
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
        """Новизна x относительно истории H (N1..N3 для операций; N0 = не новый терм)."""
        if x in self.seen:
            return 0
        s = sig(x)
        if s in self.seen_sigs:
            return 1                           # новый элемент, поведение уже было
        if s in self.compsigs:
            return 2                           # композиция известных операций (∈Cl₁)
        return 3                               # поведение вне Cl₁ истории

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
            lv_new = lv
            self._register(r)
            self.events.append((self.t, r, lv_new))
        # kappa: фиксированная ёмкость M; реакция потребляет реагент (хим. сохранение);
        # защищено то, что воспроизводится (память H); открытая система: приток сырья.
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
        """F = gfp{X⊆types : X⊆X·X}. Типы по частоте, не более cap."""
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

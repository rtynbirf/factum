"""
Та же формула, другая реализация (независимая от SKI):
 объекты = двоичные строки (≤L); ⋆(a,b|c) = лигирование a+b, катализируемое c∈W
 (катализ = фиксированная псевдослучайная таблица с вероятностью p, как в моделях Кауфмана);
 расщепление x -> x[:k]+x[k:] катализируется так же.
 κ: ёмкость M, приток еды ρ, защита воспроизводимого (память); 𝔉 = gfp (RAF-подобное самопроизводство).
"""
import random, zlib
from collections import defaultdict

FOOD = ['0', '1', '00', '01', '10', '11']

def cat(seed, c, a, b, p):
    h = zlib.crc32(f"{seed}|{c}|{a}|{b}".encode()) & 0xFFFFFF
    return h < p * 0x1000000

class Chem:
    def __init__(self, seed=0, M=300, L=6, p=0.01, inflow=0.1, memory=True):
        self.rng = random.Random(seed)
        self.seed, self.M, self.L, self.p, self.inflow, self.memory = seed, M, L, p, inflow, memory
        self.W = [self.rng.choice(FOOD) for _ in range(M)]
        self.credit = defaultdict(int)
        self.seen = set(self.W)
        self.new = 0
        self.t = 0

    def _replace(self, x):
        w = [1.0 / (1 + self.credit[y]) if self.memory else 1.0 for y in self.W]
        i = self.rng.choices(range(self.M), weights=w)[0]
        self.W[i] = x

    def tick(self):
        self.t += 1
        r = self.rng
        c = r.choice(self.W)
        if r.random() < 0.3:                       # расщепление
            x = r.choice(self.W)
            if len(x) < 2: return
            k = r.randrange(1, len(x))
            if cat(self.seed, c, x, '|%d' % k, self.p):
                for y in (x[:k], x[k:]):
                    self.credit[y] += 1
                    if y not in self.seen: self.seen.add(y); self.new += 1
                    self._replace(y)
        else:                                      # лигирование
            a, b = r.choice(self.W), r.choice(self.W)
            if len(a) + len(b) <= self.L and cat(self.seed, c, a, b, self.p):
                y = a + b
                self.credit[y] += 1
                if y not in self.seen: self.seen.add(y); self.new += 1
                self._replace(y)
        if r.random() < self.inflow:               # открытая система
            self.W[r.randrange(self.M)] = r.choice(FOOD)

    def run(self, T):
        for _ in range(T): self.tick()
        return self

    def organization(self, cap=50, cleave=True):
        cnt = defaultdict(int)
        for x in self.W:
            if len(x) > 2: cnt[x] += 1
        X = set(x for x, _ in sorted(cnt.items(), key=lambda kv: -kv[1])[:cap])
        while X:
            U = X | set(FOOD)
            P = set()
            for a in U:
                for b in U:
                    if len(a) + len(b) <= self.L:
                        y = a + b
                        if y in X and y not in (a, b) and any(cat(self.seed, c, a, b, self.p) for c in X):
                            P.add(y)
            for x in (X if cleave else ()):
                for k in range(1, len(x)):
                    if any(cat(self.seed, c, x, '|%d' % k, self.p) for c in X):
                        for y in (x[:k], x[k:]):
                            if y in X and y != x: P.add(y)
            Y = X & P
            if Y == X: return X
            X = Y
        return X

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ФАКТУМ v1.0 — ФСМ-автомат сердца улья.

Принцип ФСМ-механизмов: работающий автомат, не декларация.
Один удар сердца = полный цикл явного автомата:

    IDLE -> RECON -> IGNITE -> MEASURE -> RECORD -> IDLE

  RECON   — субстрат жив: движок импортируется, соты на месте, хеш-цепочка цела
  IGNITE  — мир создаётся (seed = UTC-дата, детерминированно) и прокручивается
  MEASURE — метрики: типы, F (gfp-организация), F_str (строгая), доля звёзд, N1/N2/N3
  RECORD  — факт = строка в JOURNAL.md (append-only, prev = sha256 предыдущей строки)

Закон #2: факт = байты. Каждая строка журнала — факт, который можно проверить.

CLI:
  python3 factum.py --heartbeat               # один удар: SKI + BCI + CHEM
  python3 factum.py --heartbeat --world SKI   # один удар одного мира
  python3 factum.py --verify                  # целость хеш-цепочки сот
"""
import argparse
import datetime
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

JOURNAL = os.path.join(HERE, "JOURNAL.md")

HEADER = (
    "# ЖУРНАЛ СЕРДЦЕБИЕНИЙ ФАКТУМА (append-only; FACTUM v1.0)\n"
    "\n"
    "Соты: факт = строка. Каждая строка данных несёт sha256 предыдущей строки данных\n"
    "(колонка prev); для первой строки предыдущей считается строка-якорь GENESIS,\n"
    "т.е. prev[1] = sha256('GENESIS'). Подмена любой строки ловится СЛЕДУЮЩЕЙ строкой\n"
    "(а каждый удар ещё и коммитом git — внешний якорь): проверка `python3 factum.py --verify`.\n"
    "\n"
    "Критерий вердикта FORM: SKI/BCI — F_str > 0 (эйгенформа: результат не подтерм\n"
    "реагентов); CHEM — F >= 2 (RAF-подобное самопроизводство, критерий |F|>=2).\n"
    "\n"
    "| # | UTC | мир | seed | шаги | типы | F | F_str | доля звёзд | N1 | N2 | N3 | вердикт | prev |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)

STATES = ("IDLE", "RECON", "IGNITE", "MEASURE", "RECORD")
NEXT = {"IDLE": "RECON", "RECON": "IGNITE", "IGNITE": "MEASURE", "MEASURE": "RECORD", "RECORD": "IDLE"}


def line_hash(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt(v, kind="s"):
    if v is None:
        return "-"
    if kind == "f":
        return "%.2f" % v
    return str(v)


def module_for(name):
    if name == "SKI":
        import emergent as mod
    elif name == "BCI":
        import bci as mod
    else:
        raise ValueError("нет такого мира: %s (есть SKI, BCI, CHEM)" % name)
    return mod


def data_rows(text):
    rows = []
    for line in text.splitlines():
        if line.startswith("| ") and not line.startswith("| #"):
            rows.append(line)
    return rows


def read_journal(path=JOURNAL):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def verify_journal(path=JOURNAL):
    """Цепочка: prev[i] == line_hash(row[i-1]); prev[0] == 'GENESIS'. -> (ok, n, msg)."""
    rows = data_rows(read_journal(path))
    prev_raw = "GENESIS"
    for i, row in enumerate(rows):
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) != 14:
            return False, i + 1, "строка %d: %d колонок вместо 14" % (i + 1, len(cells))
        if cells[-1] != line_hash(prev_raw):
            return False, i + 1, "строка %d: хеш-цепочка порвана" % (i + 1)
        prev_raw = row
    return True, len(rows), "цепочка цела"


class FactumFSM:
    """Один экземпляр = один удар сердца. Состояния и переходы явные (ФСМ, не декларация)."""

    def __init__(self, world_name="SKI", steps=1000, chem_steps=150000, seed=None, journal=JOURNAL):
        self.world_name = world_name
        self.steps = steps
        self.chem_steps = chem_steps
        self.seed = int(datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")) if seed is None else seed
        self.journal = journal
        self.state = "IDLE"
        self.trace = ["IDLE"]
        self.mod = None
        self.world = None
        self.metrics = None
        self.error = None

    def heartbeat(self):
        self.trace = ["IDLE"]
        self.state = "IDLE"
        try:
            for _ in STATES:
                self._advance()
        except Exception as e:                # факт отказа тоже факт
            self.error = "%s: %s" % (type(e).__name__, e)
        return self

    def _advance(self):
        nxt = NEXT[self.state]
        self.trace.append(nxt)
        self.state = nxt
        getattr(self, "_on_" + nxt.lower())()

    # ---- состояния ----

    def _on_idle(self):
        pass

    def _on_recon(self):
        self.mod = module_for(self.world_name) if self.world_name != "CHEM" else None
        if not os.path.exists(self.journal):          # соты создаёт сам автомат
            with open(self.journal, "w", encoding="utf-8") as f:
                f.write(HEADER)
        ok, n, msg = verify_journal(self.journal)
        if not ok:
            raise RuntimeError("соты порваны до удара: " + msg)
        self.rows_before = n

    def _on_ignite(self):
        if self.world_name == "CHEM":
            import chem
            self.world = chem.Chem(seed=self.seed, p=0.12, inflow=0.1, memory=True).run(self.chem_steps)
        else:
            self.world = self.mod.World(seed=self.seed, inflow=0.5, memory=True).run(self.steps)

    def _on_measure(self):
        w = self.world
        if self.world_name == "CHEM":
            self.metrics = {
                "utc": utc_now(), "world": "CHEM", "seed": self.seed, "steps": self.chem_steps,
                "types": len(set(w.W)), "F": len(w.organization()), "F_str": None,
                "share": None, "N1": None, "N2": None, "N3": None, "new": w.new,
            }
            self.metrics["verdict"] = "FORM" if self.metrics["F"] >= 2 else "SILENT"
        else:
            nv = self.mod.novelty_vector(w)
            self.metrics = {
                "utc": utc_now(), "world": self.world_name, "seed": self.seed, "steps": self.steps,
                "types": len(set(w.W)), "F": len(w.organization()),
                "F_str": len(w.organization(strict=True)),
                "share": round(w.defined / w.attempts, 2) if w.attempts else 0.0,
                "N1": nv[1], "N2": nv[2], "N3": nv[3],
            }
            self.metrics["verdict"] = "FORM" if self.metrics["F_str"] > 0 else "SILENT"

    def _on_record(self):
        rows = data_rows(read_journal(self.journal))
        prev_raw = rows[-1] if rows else "GENESIS"    # якорь хешируется по тому же правилу
        prev = line_hash(prev_raw)
        num = int(rows[-1].strip().strip("|").split("|")[0]) + 1 if rows else 1
        m = self.metrics
        row = ("| %d | %s | %s | %d | %d | %d | %s | %s | %s | %s | %s | %s | %s | %s |"
               % (num, m["utc"], m["world"], m["seed"], m["steps"], m["types"],
                  _fmt(m["F"]), _fmt(m["F_str"]), _fmt(m["share"], "f"),
                  _fmt(m["N1"]), _fmt(m["N2"]), _fmt(m["N3"]), m["verdict"], prev))
        with open(self.journal, "a", encoding="utf-8") as f:   # только append, никогда не вперёд
            f.write(row + "\n")
        self.row_written = row


def main():
    ap = argparse.ArgumentParser(description="ФАКТУМ — ФСМ-автомат сердца улья")
    ap.add_argument("--heartbeat", action="store_true", help="один удар сердца")
    ap.add_argument("--world", default="ALL", choices=["ALL", "SKI", "BCI", "CHEM"])
    ap.add_argument("--steps", type=int, default=1000, help="шагов SKI/BCI-мира за удар")
    ap.add_argument("--chem-steps", type=int, default=150000, help="шагов химии за удар")
    ap.add_argument("--seed", type=int, default=None, help="seed (по умолчанию UTC-дата)")
    ap.add_argument("--verify", action="store_true", help="проверить хеш-цепочку сот")
    a = ap.parse_args()

    if a.verify:
        ok, n, msg = verify_journal()
        print("JOURNAL: %d строк данных; %s" % (n, msg))
        sys.exit(0 if ok else 1)

    if a.heartbeat:
        worlds = ["SKI", "BCI", "CHEM"] if a.world == "ALL" else [a.world]
        for wn in worlds:
            f = FactumFSM(wn, steps=a.steps, chem_steps=a.chem_steps, seed=a.seed).heartbeat()
            if f.error:
                print("FACTUM %s: СБОЙ АВТОМАТА: %s" % (wn, f.error))
                sys.exit(1)
            m = f.metrics
            extra = "" if wn != "CHEM" else " new=%d" % m["new"]
            print("FACTUM %s: %s | seed=%d types=%s F=%s F_str=%s share=%s verdict=%s%s | %s"
                  % (wn, m["utc"], m["seed"], m["types"], _fmt(m["F"]), _fmt(m["F_str"]),
                     _fmt(m["share"], "f"), m["verdict"], extra, "->".join(f.trace)))
        ok, n, msg = verify_journal()
        print("JOURNAL: %d строк данных; %s" % (n, msg))
        sys.exit(0 if ok else 1)

    ap.print_help()


if __name__ == "__main__":
    main()

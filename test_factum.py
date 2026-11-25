# -*- coding: utf-8 -*-
"""Тесты ФСМ-автомата ФАКТУМА: цикл, соты, хеш-цепочка, детерминизм, тотальность BCI."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import factum as F


def _run(world, tmp_path, **kw):
    j = str(tmp_path / ("JOURNAL_%s.md" % world))
    params = dict(world_name=world, steps=150, chem_steps=3000, seed=777, journal=j)
    params.update(kw)
    f = F.FactumFSM(**params).heartbeat()
    assert f.error is None, "сбой автомата: %s" % f.error
    return f, j


def test_fsm_full_cycle(tmp_path):
    f, j = _run("SKI", tmp_path)
    assert f.state == "IDLE"
    assert f.trace == ["IDLE", "RECON", "IGNITE", "MEASURE", "RECORD", "IDLE"]
    assert f.metrics["verdict"] in ("FORM", "SILENT")


def test_journal_grows_exactly_one_row(tmp_path):
    f, j = _run("SKI", tmp_path)
    rows = F.data_rows(F.read_journal(j))
    assert len(rows) == 1
    cells = [c.strip() for c in rows[0].strip().strip("|").split("|")]
    assert cells[0] == "1" and cells[2] == "SKI" and cells[-1] == F.line_hash("GENESIS")
    # второй удар: номер строки продолжается
    f2 = F.FactumFSM("SKI", steps=150, chem_steps=3000, seed=778, journal=j).heartbeat()
    assert f2.error is None
    rows = F.data_rows(F.read_journal(j))
    assert len(rows) == 2 and int(rows[1].strip().strip("|").split("|")[0]) == 2


def test_hash_chain_and_tamper(tmp_path):
    j = str(tmp_path / "JOURNAL_SKI.md")
    F.FactumFSM("SKI", steps=150, chem_steps=3000, seed=777, journal=j).heartbeat()
    F.FactumFSM("SKI", steps=150, chem_steps=3000, seed=778, journal=j).heartbeat()
    ok, n, msg = F.verify_journal(j)
    assert ok and n == 2, msg
    # подмена байтов в строке 1 рвётся строкой 2 (prev[2] = sha256(строка 1))
    lines = F.read_journal(j).splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("| 1 "):
            lines[i] = ln.replace("| 777 |", "| 776 |")
    text = "\n".join(lines) + "\n"
    open(j, "w", encoding="utf-8").write(text)
    ok, n, msg = F.verify_journal(j)
    assert not ok, "подмена не обнаружена"


def test_determinism_same_seed(tmp_path):
    f1, _ = _run("SKI", tmp_path)
    f2, j2 = _run("SKI", tmp_path)  # тот же seed=777, тот же tmp-суффикс имени
    assert f2.error is None
    strip = lambda m: {k: v for k, v in m.items() if k != "utc"}
    assert strip(f1.metrics) == strip(f2.metrics)


def test_bci_totality(tmp_path):
    f, j = _run("BCI", tmp_path)
    assert f.metrics["share"] == 1.0, "BCI тотален: каждое применение определено"


def test_chem_beat(tmp_path):
    f, j = _run("CHEM", tmp_path)
    assert f.metrics["verdict"] in ("FORM", "SILENT")
    assert f.metrics["F"] >= 0
    cells = [c.strip() for c in F.data_rows(F.read_journal(j))[0].strip().strip("|").split("|")]
    assert cells[2] == "CHEM" and cells[7] == "-"  # строгого критерия в химии нет

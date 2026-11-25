# -*- coding: utf-8 -*-
"""Тесты эксперимента поколений: сериализация термов, форма сеянцев, мини-поколения."""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import generations as G


def test_jterm_pterm_roundtrip():
    for t in ['I', ('S', 'K'), (('S', ('K', 'I')), ('I', 'S'))]:
        assert G.pterm(G.jterm(t)) == t


def test_ski_seedling_shape():
    form = [('S', 'K'), 'I', (('K', 'I'), 'S')]
    w0 = G.ski_seedling(form, random.Random(1))
    assert len(w0) == G.M_SKI
    assert all(isinstance(x, str) or isinstance(x, tuple) for x in w0)


def test_chem_seedling_shape():
    form = ['010', '1011', '001011']
    w0 = G.chem_seedling(form, random.Random(2))
    assert len(w0) == G.M_CHEM
    assert all(len(x) <= 6 for x in w0)          # L=6 не превышено
    assert all(set(x) <= {'0', '1'} for x in w0)  # алфавит замкнут (N4=0)


def test_mini_generation_ski(monkeypatch):
    monkeypatch.setattr(G, "T_SKI", 100)
    cands, nxt = G.ski_litter([('S', 'K'), 'I'], 0, line=0)
    assert len(cands) == G.K
    assert nxt is None or isinstance(nxt, list)
    ccands, cnxt = G.ski_control([('S', 'K'), 'I'], 0)
    assert len(ccands) == G.K


def test_mini_generation_chem(monkeypatch):
    monkeypatch.setattr(G, "T_CHEM", 2000)
    cands, nxt = G.chem_litter(['010', '1011'], 0, line=0)
    assert len(cands) == G.K
    assert nxt is None or all(len(x) <= 6 for x in nxt)

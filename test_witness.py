#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты СВИДЕТЕЛЯ ФАКТУМА — соты, цепочка, вердикты, отказоустойчивость.

Запуск:
  python3 -m pytest -q test_witness.py
  python3 test_witness.py
"""
import hashlib
import importlib.util
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _load_witness():
    spec = importlib.util.spec_from_file_location("witness", os.path.join(HERE, "witness.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


W = _load_witness()


def _make_log(path, rows_text, header=W.LOG_HEADER):
    """Создать соты с заголовком + строками."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(rows_text)


class WitnessChainTests(unittest.TestCase):
    """Цепочка сот свидетеля: якорь 'WITNESS', prev = sha256(prev raw)[:12]."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
        self.tmp.close()
        self.path = self.tmp.name

    def tearDown(self):
        os.unlink(self.path)

    def _row(self, num, prev_hash, verdict="LIVE_WITNESSED"):
        return (f"| {num} | 2026-11-27T13:24:18Z | Z-AI/witness/v1.0 | LIVE | 4.72 | 8 | ✓ | 84 | 16 | {verdict} | {prev_hash} |\n")

    def test_empty_log_fails_verify(self):
        ok, msg = W.verify_witness_chain(self.path)
        self.assertFalse(ok)
        self.assertIn("пусты", msg)

    def test_anchor_hash_is_sha256_WITNESS_12(self):
        h = W.line_hash("WITNESS")
        self.assertEqual(h, hashlib.sha256(b"WITNESS").hexdigest()[:12])
        self.assertEqual(len(h), 12)

    def test_single_row_chain_intact(self):
        anchor = W.line_hash("WITNESS")
        _make_log(self.path, self._row(1, anchor))
        ok, msg = W.verify_witness_chain(self.path)
        self.assertTrue(ok, msg)
        self.assertIn("1 строк", msg)

    def test_two_row_chain_intact(self):
        anchor = W.line_hash("WITNESS")
        r1 = self._row(1, anchor).rstrip("\n")
        r2 = self._row(2, W.line_hash(r1))
        _make_log(self.path, r1 + "\n" + r2)
        ok, msg = W.verify_witness_chain(self.path)
        self.assertTrue(ok, msg)
        self.assertIn("2 строк", msg)

    def test_tampered_row_breaks_chain(self):
        anchor = W.line_hash("WITNESS")
        r1 = self._row(1, anchor)
        # подменим вердикт в первой строке — её хеш изменится, prev во второй не сойдётся
        r1_tampered = r1.replace("LIVE_WITNESSED", "BROKEN_WITNESSED", 1)
        r2 = self._row(2, W.line_hash(r1.rstrip("\n")))  # prev считает по НЕподменённой
        _make_log(self.path, r1_tampered + r2)
        ok, msg = W.verify_witness_chain(self.path)
        self.assertFalse(ok)
        self.assertIn("разорвана", msg)

    def test_wrong_anchor_breaks_first_row(self):
        _make_log(self.path, self._row(1, "deadbeefdead"))
        ok, msg = W.verify_witness_chain(self.path)
        self.assertFalse(ok)
        self.assertIn("разорвана", msg)


class WitnessVerdictTests(unittest.TestCase):
    """Вердикты свидетеля — честные (правило 6: красное — честно красное)."""

    def test_verdicts_four_states(self):
        self.assertEqual(
            {"LIVE_WITNESSED", "STALE_WITNESSED", "BROKEN_WITNESSED", "UNAVAILABLE"},
            set(W.LABELS.keys()),
        )
        self.assertEqual(set(W.LABELS.keys()), set(W.COLORS.keys()))

    def test_unavailable_label_is_red_honest(self):
        # UNAVAILABLE — серый/красный, но НЕ зелёный (правило 6)
        self.assertNotEqual(W.COLORS["UNAVAILABLE"], "#2ea043")

    def test_broken_is_red(self):
        self.assertEqual(W.COLORS["BROKEN_WITNESSED"], "#f85149")


class WitnessMeasureTests(unittest.TestCase):
    """Измерение свидетеля — структурный контракт (07_DATA профиля)."""

    def test_measure_contract_keys(self):
        # без токена GitHub API — мера упадёт на UNAVAILABLE или на LIVE_WITNESSED,
        # но контракт всегда несёт обязательные ключи
        c = W.measure(token=None)
        for k in ("metric_id", "unit", "definition", "source", "scope",
                  "method_version", "generated_at", "pulse_status", "status",
                  "journal_chain_ok", "witness_chain_ok"):
            self.assertIn(k, c, f"ключ {k} отсутствует")
        self.assertEqual(c["metric_id"], "factum.witness")
        self.assertEqual(c["method_version"], "witness/v1.0")

    def test_measure_status_in_four_states(self):
        c = W.measure(token=None)
        self.assertIn(c["status"], W.LABELS.keys())


class WitnessRecordTests(unittest.TestCase):
    """Запись факта — append-only, никогда не вперёд (правило храповика)."""

    def setUp(self):
        self.tmp_w = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
        self.tmp_w.close()
        # подменим WITNESS_LOG на временный
        self._orig = W.WITNESS_LOG
        W.WITNESS_LOG = self.tmp_w.name

    def tearDown(self):
        W.WITNESS_LOG = self._orig
        os.unlink(self.tmp_w.name)

    def test_first_record_uses_anchor(self):
        c = {"generated_at": "2026-11-27T13:24:18Z", "pulse_status": "LIVE",
             "pulse_age_hours": 4.72, "journal_beats": 8, "journal_chain_ok": True,
             "apiary_ok": True, "apiary_repos_total": 84, "apiary_fat_repos": 16,
             "status": "LIVE_WITNESSED"}
        W.record(c)
        with open(self.tmp_w.name) as f:
            content = f.read()
        self.assertIn("| 1 |", content)
        self.assertIn(W.line_hash("WITNESS"), content)
        ok, _ = W.verify_witness_chain(self.tmp_w.name)
        self.assertTrue(ok)

    def test_second_record_chains_to_first(self):
        c = {"generated_at": "2026-11-27T13:25:00Z", "pulse_status": "LIVE",
             "pulse_age_hours": 4.73, "journal_beats": 8, "journal_chain_ok": True,
             "apiary_ok": True, "apiary_repos_total": 84, "apiary_fat_repos": 16,
             "status": "LIVE_WITNESSED"}
        W.record(c)
        W.record(c)  # второй удар
        ok, msg = W.verify_witness_chain(self.tmp_w.name)
        self.assertTrue(ok, msg)


class WitnessApiaryTests(unittest.TestCase):
    """Внешняя диспозиция пасеки — отказоустойчивость (UNAVAILABLE — честно)."""

    def test_fetch_apiary_no_token_returns_dict(self):
        # без токена и без сети — словарь с ошибкой или с ok=True
        # (на CI с сетью public API работает и без токона, но в rate-limit; честно受け)
        d = W.fetch_apiary(token="__invalid_token_for_test__")
        # либо ok=True с repos_total, либо error (401/403) — оба валидны
        self.assertTrue("ok" in d or "error" in d, f"непонятный ответ: {d}")

    def test_fat_threshold_is_10mib(self):
        # 10 MiB = 10240 KiB — таймер-бомбы, не просто .git-история
        self.assertEqual(W.FAT_KIB, 10240)


if __name__ == "__main__":
    unittest.main(verbosity=2)

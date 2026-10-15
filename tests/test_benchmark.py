"""Doğruluk regresyon kapısı: benchmark'taki sızıntı oranı ve yanlış pozitifler."""

import importlib.util
from pathlib import Path


def _bench():
    p = Path(__file__).resolve().parents[1] / "benchmarks" / "run.py"
    spec = importlib.util.spec_from_file_location("bench", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_leak_rate_and_false_positives():
    tp, fn, fp, leaks, total, _, neg_fp = _bench().evaluate(1500)
    leak_rate = sum(leaks.values()) / sum(total.values())
    assert leak_rate < 0.03, f"sızıntı oranı {leak_rate:.2%}"
    assert neg_fp == [], neg_fp
    assert sum(fp.values()) == 0
    # Doğrulayıcısı olan türlerde kaçak olmamalı
    for kind in ("TCKN", "IBAN", "CARD", "VKN", "PHONE", "PLATE", "EMAIL", "IP", "MAC", "PASSWORD"):
        assert leaks[kind] == 0, kind

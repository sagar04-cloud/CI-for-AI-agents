"""Tests for Phase 7 DoneBench suite."""

from __future__ import annotations

from pathlib import Path

from bench.run import run_benchmark
from bench.tasks import TASKS


def test_donebench_has_12_tasks_and_4_languages() -> None:
    assert len(TASKS) >= 12
    assert len({t.language for t in TASKS}) >= 4


def test_donebench_mock_run_reduces_false_done(tmp_path: Path) -> None:
    out_md = tmp_path / "results.md"
    metrics = run_benchmark(agent="mock", output_path=out_md)
    assert out_md.is_file()
    text = out_md.read_text(encoding="utf-8")
    assert "Overall Summary" in text
    assert "Per-Language Breakdown" in text

    baseline = [m for m in metrics if m.mode == "baseline"]
    gated = [m for m in metrics if m.mode == "donegate"]
    assert sum(1 for m in baseline if m.false_done) > 0
    assert sum(1 for m in gated if m.false_done) == 0
    assert all(m.truly_passed for m in gated)

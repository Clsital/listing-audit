"""评测跑批测试：CSV 解析与准确率汇总（不调用模型）。"""
import csv
from pathlib import Path

from app.eval_runner import EvalResult, read_manifest, summarize


def write_csv(path: Path, rows: list[dict]):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_read_manifest_handles_bom_and_bool(tmp_path: Path):
    manifest = tmp_path / "compliance_cases.csv"
    write_csv(
        manifest,
        [
            {"title": "正常羽绒服", "points": "保暖;轻便", "expected_clean": "1"},
            {"title": "全网第一羽绒服", "points": "顶级", "expected_clean": "0"},
        ],
    )
    rows = read_manifest(manifest)
    assert len(rows) == 2
    assert rows[1]["expected_clean"] == "0"


def test_summarize_counts_accuracy_and_failures():
    results = [
        EvalResult(inputs={"title": "a"}, expected=True, actual=True, detail={}),
        EvalResult(inputs={"title": "b"}, expected=False, actual=False, detail={}),
        EvalResult(inputs={"title": "c"}, expected=True, actual=False, detail={"error": "x"}),
    ]
    report = summarize("compliance", results)
    assert report.total == 3
    assert report.correct == 2
    assert report.accuracy == 0.6667
    assert len(report.failures) == 1
    assert report.failures[0].inputs["title"] == "c"


def test_summarize_empty():
    report = summarize("vision", [])
    assert report.total == 0
    assert report.accuracy == 0.0

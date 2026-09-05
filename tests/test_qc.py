"""出图质检测试：verdict 分级策略与解析容错。"""
import json

import pytest

from app.llm import AuditError, parse_qc_report
from app.qc import apply_verdict_policy, QcIssue, QcReport

QC_BASE = {
    "issues": [],
    "summary": "整图无可见问题",
}


def make_raw(issues: list[dict], summary: str = "发现问题") -> str:
    return json.dumps({"issues": issues, "summary": summary}, ensure_ascii=False)


def test_parse_qc_clean_report_is_usable():
    report = parse_qc_report(make_raw([], "整图无可见问题"))
    assert report.verdict == "usable"
    assert report.issues == []


def test_parse_qc_blocker_means_regenerate():
    raw = make_raw(
        [
            {
                "category": "body",
                "severity": "blocker",
                "location": "右手手指",
                "finding": "右手出现六根手指",
                "suggestion": "重生成时降低手部姿态自由度",
                "confidence": 0.97,
            }
        ]
    )
    report = parse_qc_report(raw)
    assert report.verdict == "regenerate"


def test_parse_qc_major_means_retouch():
    raw = make_raw(
        [
            {
                "category": "garment",
                "severity": "major",
                "location": "裙摆蕾丝边",
                "finding": "蕾丝纹路与商品描述的镂空花纹不一致，被 AI 重绘为印花",
                "suggestion": "局部重绘裙摆，锁定领口与袖型",
                "confidence": 0.9,
            }
        ]
    )
    report = parse_qc_report(raw)
    assert report.verdict == "retouch"


def test_parse_qc_minor_only_still_usable():
    raw = make_raw(
        [
            {
                "category": "artifact",
                "severity": "minor",
                "location": "背景窗帘",
                "finding": "窗帘褶皱有轻微纹理重复",
                "confidence": 0.7,
            }
        ]
    )
    report = parse_qc_report(raw)
    assert report.verdict == "usable"


def test_parse_qc_rejects_unknown_category():
    raw = make_raw(
        [{"category": "magic", "severity": "major", "location": "x", "finding": "y"}]
    )
    with pytest.raises(AuditError, match="schema"):
        parse_qc_report(raw)


def test_verdict_policy_is_idempotent():
    report = QcReport(
        issues=[QcIssue(category="body", severity="major", location="左腿", finding="关节反折")],
        summary="需修图",
    )
    assert apply_verdict_policy(report).verdict == "retouch"
    assert apply_verdict_policy(apply_verdict_policy(report)).verdict == "retouch"

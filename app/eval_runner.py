"""评测跑批：从 manifest.csv 读用例，逐条调用审核，输出准确率报告。

manifest 格式（UTF-8 CSV，可带 BOM）：
- 图文一致性：image,expected_consistent,title,category,color,selling_points
  （expected_consistent: 1=相符, 0=不符；image 为相对 eval/ 的图片路径）
- 文案合规：title,points,expected_clean
  （expected_clean: 1=应无违规, 0=应检出违规）
"""
import csv
from datetime import datetime
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from app.schemas import ProductInfo


class EvalCase(BaseModel):
    inputs: dict
    expected: bool


class EvalResult(BaseModel):
    inputs: dict
    expected: bool
    # None 表示该条运行失败（模型/网络异常），按未命中计
    actual: bool | None
    detail: dict


class EvalReport(BaseModel):
    eval_type: str
    ran_at: str
    total: int
    correct: int
    accuracy: float
    failures: list[EvalResult]


def read_manifest(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _to_bool(value: str) -> bool:
    return value.strip() in ("1", "true", "True", "是")


def summarize(eval_type: str, results: list[EvalResult]) -> EvalReport:
    correct = sum(1 for r in results if r.expected == r.actual)
    total = len(results)
    return EvalReport(
        eval_type=eval_type,
        ran_at=datetime.now().isoformat(timespec="seconds"),
        total=total,
        correct=correct,
        accuracy=round(correct / total, 4) if total else 0.0,
        failures=[r for r in results if r.expected != r.actual],
    )


def run_vision_eval(
    manifest_path: Path,
    auditor: Callable[[str, ProductInfo], dict],
    image_dir: Path | None = None,
    limit: int | None = None,
) -> EvalReport:
    """auditor(image_path_str, product) -> dict，需含 consistent 字段。"""
    import base64
    import mimetypes

    root = image_dir or manifest_path.parent
    results: list[EvalResult] = []
    rows = read_manifest(manifest_path)
    if limit:
        rows = rows[:limit]
    for row in rows:
        image_path = root / row["image"]
        content_type = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
        data_url = "data:%s;base64,%s" % (
            content_type,
            base64.b64encode(image_path.read_bytes()).decode("ascii"),
        )
        product = ProductInfo(
            title=row["title"],
            category=row.get("category", ""),
            color=row.get("color", ""),
            selling_points=row.get("selling_points", ""),
        )
        expected = _to_bool(row["expected_consistent"])
        try:
            report = auditor(data_url, product)
            if hasattr(report, "model_dump"):
                report = report.model_dump()
            actual = report["consistent"]
            detail = {"risk_level": report.get("risk_level", "")}
        except Exception as e:  # noqa: BLE001 - 单条失败计入结果，不中断跑批
            actual = None
            detail = {"error": str(e)}
        results.append(
            EvalResult(
                inputs={k: row.get(k, "") for k in ("image", "title", "category", "color")},
                expected=expected,
                actual=actual,
                detail=detail,
            )
        )
    return summarize("vision", results)


def run_compliance_eval(
    manifest_path: Path,
    checker: Callable[[ProductInfo], dict],
    limit: int | None = None,
) -> EvalReport:
    """checker(product) -> dict，需含 clean 字段。"""
    results: list[EvalResult] = []
    rows = read_manifest(manifest_path)
    if limit:
        rows = rows[:limit]
    for row in rows:
        product = ProductInfo(
            title=row["title"], selling_points=row.get("points", "")
        )
        expected = _to_bool(row["expected_clean"])
        try:
            report = checker(product)
            if hasattr(report, "model_dump"):
                report = report.model_dump()
            actual = report["clean"]
            detail = {"terms": [v["term"] for v in report.get("violations", [])]}
        except Exception as e:  # noqa: BLE001
            actual = None
            detail = {"error": str(e)}
        results.append(
            EvalResult(
                inputs={"title": row["title"]},
                expected=expected,
                actual=actual,
                detail=detail,
            )
        )
    return summarize("compliance", results)

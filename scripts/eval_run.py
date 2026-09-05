"""评测跑批 CLI。

用法：
  uv run python scripts/eval_run.py compliance --manifest eval/compliance_cases.csv
  uv run python scripts/eval_run.py vision --manifest eval/manifest.csv --limit 5
结果打印到终端并写入 eval/results/eval-report-<type>.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.compliance import audit_copy  # noqa: E402
from app.eval_runner import run_compliance_eval, run_vision_eval  # noqa: E402
from app.llm import OpenAICompatVisionClient, audit_listing  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="评测跑批")
    parser.add_argument("type", choices=["compliance", "vision"])
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 条（试跑用）")
    args = parser.parse_args()

    manifest = Path(args.manifest)
    if not manifest.exists():
        print(f"manifest 不存在: {manifest}", file=sys.stderr)
        return 1

    if args.type == "compliance":
        client = OpenAICompatVisionClient()
        report = run_compliance_eval(manifest, lambda product: audit_copy(product, client))
    else:
        client = OpenAICompatVisionClient()

        def auditor(data_url, product):
            return audit_listing(data_url, product, client).model_dump()

        report = run_vision_eval(manifest, auditor)

    out_path = Path("eval/results") / f"eval-report-{args.type}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"类型: {report.eval_type}  用例: {report.total}  正确: {report.correct}  准确率: {report.accuracy:.1%}")
    if report.failures:
        print("未命中用例：")
        for f in report.failures:
            print(f"  期望={f.expected} 实际={f.actual} 输入={f.inputs} 详情={f.detail}")
    print(f"报告已写入: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

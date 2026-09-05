"""文案合规检测 CLI（极限词/违禁词）。

用法：
  python scripts/compliance_cli.py --title "2026 全网第一羽绒服" --points-file 卖点.txt
  python scripts/compliance_cli.py --title "法式连衣裙" --points "雪纺面料;收腰显瘦"
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.compliance import ComplianceError, audit_copy  # noqa: E402
from app.llm import OpenAICompatVisionClient  # noqa: E402
from app.schemas import ProductInfo  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="商品文案合规检测（极限词/违禁词）")
    parser.add_argument("--title", required=True)
    parser.add_argument("--points", default="", help="卖点文案，可含换行")
    parser.add_argument("--points-file", help="从文件读取卖点文案（推荐用于多行真实格式）")
    args = parser.parse_args()

    points = args.points
    if args.points_file:
        points = Path(args.points_file).read_text(encoding="utf-8")

    try:
        report = audit_copy(
            ProductInfo(title=args.title, selling_points=points),
            OpenAICompatVisionClient(),
        )
    except ComplianceError as e:
        print(f"检测失败: {e}", file=sys.stderr)
        return 2

    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

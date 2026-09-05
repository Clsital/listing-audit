"""AIGC 出图质检 CLI。

用法：
  python scripts/qc_cli.py 生成图.webp --title "方领泡泡袖连衣裙" --category 连衣裙 --color 浅粉色 --points "系带;蕾丝裙摆"
"""
import argparse
import json
import mimetypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm import (  # noqa: E402
    AuditError,
    OpenAICompatVisionClient,
    image_to_data_url,
    qc_image,
)
from app.schemas import ProductInfo  # noqa: E402

VERDICT_LABELS = {"usable": "✓ 可直接用", "retouch": "✎ 需修图", "regenerate": "↻ 建议重生成"}


def main() -> int:
    parser = argparse.ArgumentParser(description="AIGC 出图质检")
    parser.add_argument("image", help="AIGC 生成图路径")
    parser.add_argument("--title", default="")
    parser.add_argument("--category", default="")
    parser.add_argument("--color", default="")
    parser.add_argument("--points", default="")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"图片不存在: {image_path}", file=sys.stderr)
        return 1
    content_type = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"

    try:
        report = qc_image(
            image_to_data_url(image_path.read_bytes(), content_type),
            ProductInfo(
                title=args.title,
                category=args.category,
                color=args.color,
                selling_points=args.points,
            ),
            OpenAICompatVisionClient(),
        )
    except AuditError as e:
        print(f"质检失败: {e}", file=sys.stderr)
        return 2

    print(f"判定: {VERDICT_LABELS[report.verdict]}")
    print(f"结论: {report.summary}")
    for issue in report.issues:
        print(
            f"  [{issue.severity}] {issue.location}: {issue.finding}"
            + (f"（建议: {issue.suggestion}）" if issue.suggestion else "")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

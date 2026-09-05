"""命令行跑通审核链路（不依赖前端）。

用法：
  python scripts/audit_cli.py 商品图.jpg --title "法式连衣裙" --category 连衣裙 --color 米白色 --points "雪纺;收腰"
环境变量：LLM_API_KEY、LLM_BASE_URL、LLM_MODEL
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
    audit_listing,
    image_to_data_url,
)
from app.schemas import ProductInfo  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="电商图文一致性审核")
    parser.add_argument("image", help="商品图路径")
    parser.add_argument("--title", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--color", required=True)
    parser.add_argument("--points", default="")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"图片不存在: {image_path}", file=sys.stderr)
        return 1
    content_type = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"

    try:
        client = OpenAICompatVisionClient()
        report = audit_listing(
            image_to_data_url(image_path.read_bytes(), content_type),
            ProductInfo(
                title=args.title,
                category=args.category,
                color=args.color,
                selling_points=args.points,
            ),
            client,
        )
    except AuditError as e:
        print(f"审核失败: {e}", file=sys.stderr)
        return 2

    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

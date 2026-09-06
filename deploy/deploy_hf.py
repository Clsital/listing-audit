"""一键部署到 Hugging Face Space（Docker SDK）。

用法（在项目根目录）：
  uv run --with huggingface_hub python deploy/deploy_hf.py --repo-id <你的用户名>/listing-audit

Token 获取：https://huggingface.co/settings/tokens → New token → 权限选 Write。
脚本会按以下顺序读取 token：--token 参数 → HF_TOKEN 环境变量 → 交互输入（隐藏回显）。

网络：默认走本机代理 http://127.0.0.1:7890；无代理时用 --no-proxy 直连，
或 --endpoint https://hf-mirror.com 走镜像。
"""
import argparse
import getpass
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENDPOINT = "https://huggingface.co"
DEFAULT_PROXY = "http://127.0.0.1:7890"

# 上传到 Space 的内容；README 会被加上 HF 需要的 front-matter
IGNORE_DIRS = {
    ".git", ".venv", "__pycache__", ".pytest_cache",
    "web/node_modules", "web/dist",
    "eval/samples", "eval/results", "eval/__pycache__",
}
IGNORE_FILES = {".env", ".dockerignore", "deploy/space-README-header.md"}

FRONT_MATTER = """---
title: AIGC 出图质检台
emoji: 🧵
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8000
pinned: false
---
"""


def collect_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        parts = rel.split("/")
        if any(part in IGNORE_DIRS for part in parts):
            continue
        if rel in IGNORE_FILES or rel.startswith(".pytest_cache"):
            continue
        if rel.endswith(".pyc"):
            continue
        files.append(path)
    return files


def build_staging(files: list[Path]) -> Path:
    staging = Path(tempfile.mkdtemp(prefix="listing-audit-space-"))
    for src in files:
        rel = src.relative_to(ROOT)
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    readme = staging / "README.md"
    readme.write_text(FRONT_MATTER + "\n" + readme.read_text(encoding="utf-8"), encoding="utf-8")
    return staging


def load_env_keys() -> dict[str, str]:
    """从环境变量或根目录 .env 读取需要写入 Space Secrets 的键。"""
    wanted = [
        "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
        "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST",
    ]
    values: dict[str, str] = {k: os.environ.get(k, "") for k in wanted}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" not in line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("'\"")
            if key in wanted and key not in values or (key in values and not values[key]):
                values[key] = value
    return {k: v for k, v in values.items() if v}


def main() -> int:
    parser = argparse.ArgumentParser(description="部署 listing-audit 到 Hugging Face Space")
    parser.add_argument("--repo-id", required=True, help="如：你的用户名/listing-audit")
    parser.add_argument("--token", default=os.environ.get("HF_TOKEN", ""))
    parser.add_argument("--endpoint", default=os.environ.get("HF_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--proxy", default=DEFAULT_PROXY, help="HTTP 代理；--no-proxy 直连")
    parser.add_argument("--no-proxy", action="store_true", help="不使用代理直连")
    parser.add_argument("--dry-run", action="store_true", help="只打印将上传的文件，不实际部署")
    args = parser.parse_args()

    if not args.no_proxy and args.proxy:
        os.environ["HTTPS_PROXY"] = os.environ["HTTP_PROXY"] = args.proxy
        print(f"使用代理: {args.proxy}")

    files = collect_files()
    print(f"将上传 {len(files)} 个文件（已排除虚拟环境/依赖/评测样本等）：")
    for f in files:
        print(f"  {f.relative_to(ROOT).as_posix()}")
    if args.dry_run:
        return 0

    token = args.token or getpass.getpass("粘贴 HF Write Token（输入不回显）: ")
    if not token:
        print("未提供 token，中止", file=sys.stderr)
        return 1

    from huggingface_hub import HfApi

    api = HfApi(endpoint=args.endpoint, token=token)
    print(f"创建 Space：{args.repo_id}（sdk=docker, endpoint={args.endpoint}）")
    api.create_repo(repo_id=args.repo_id, repo_type="space", space_sdk="docker", exist_ok=True)

    staging = build_staging(files)
    print("上传文件…")
    api.upload_folder(
        folder_path=str(staging),
        repo_id=args.repo_id,
        repo_type="space",
        commit_message="deploy: listing-audit",
    )
    shutil.rmtree(staging, ignore_errors=True)

    secrets = load_env_keys()
    for key, value in secrets.items():
        api.add_space_secret(repo_id=args.repo_id, key=key, value=value)
        print(f"已写入 Secret: {key}")
    missing = [k for k in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL") if k not in secrets]
    if missing:
        print(f"警告：以下必需 Secrets 未在 .env/环境中找到，需手动在 Space Settings 添加：{missing}")

    print("\n部署完成！构建约需 2-5 分钟，之后访问（你的浏览器需能访问 HF，可开代理）：")
    print(f"  https://huggingface.co/spaces/{args.repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

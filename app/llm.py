"""视觉模型调用与输出解析。

不依赖特定厂商 SDK：任何 OpenAI 兼容的 chat/completions 端点
（DashScope Qwen-VL、GLM-4V、豆包等）都可通过环境变量接入。
"""
import base64
import json
import os
import re
import time
from typing import Protocol

import httpx

from app.prompt import build_audit_prompt
from app.schemas import AuditError, AuditReport, ProductInfo, apply_risk_policy

DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_ATTEMPTS = 3
RETRY_SLEEP_SECONDS = 1.0


def _load_dotenv(path: str = ".env") -> None:
    """把 .env 的 KEY=VALUE 注入进程环境；已存在的环境变量优先。"""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
    except FileNotFoundError:
        pass


class VisionClient(Protocol):
    def chat(self, image_data_url: str, prompt: str) -> str: ...


class OpenAICompatVisionClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        _load_dotenv()
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.base_url = (
            base_url or os.environ.get("LLM_BASE_URL", "")
        ).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL", "")
        self.timeout = timeout
        if not (self.api_key and self.base_url and self.model):
            raise AuditError(
                "缺少模型配置：请设置 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL 环境变量"
            )

    def chat(self, image_data_url: str, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                }
            ],
            "temperature": 0.2,
            "max_tokens": 2048,
        }
        return self._post(payload)

    def chat_text(self, prompt: str) -> str:
        """纯文本调用（文案合规等不需要图片的场景）。"""
        return self._post(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 2048,
            }
        )

    def _post(self, payload: dict) -> str:
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise AuditError(f"模型接口调用失败: {e}") from e
        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise AuditError(f"模型响应结构异常: {e}") from e


def image_to_data_url(image_bytes: bytes, content_type: str) -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{content_type};base64,{b64}"


def extract_json_object(raw: str) -> dict:
    """从模型输出中提取 JSON 对象。容忍 markdown 代码块包裹。"""
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AuditError("输出中未找到 JSON 对象")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise AuditError(f"JSON 解析失败: {e}") from e


def parse_report(raw: str) -> AuditReport:
    """从模型输出中提取 JSON 并校验。容忍 markdown 代码块包裹。"""
    data = extract_json_object(raw)
    try:
        return apply_risk_policy(AuditReport.model_validate(data))
    except AuditError:
        raise
    except Exception as e:
        raise AuditError(f"不符合报告 schema: {e}") from e


def audit_listing(
    image_data_url: str,
    product: ProductInfo,
    client: VisionClient,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> AuditReport:
    last_error = ""
    for attempt in range(max_attempts):
        prompt = build_audit_prompt(product, error_hint=last_error or None)
        try:
            raw = client.chat(image_data_url, prompt)
            report = parse_report(raw)
        except AuditError as e:
            last_error = str(e)
            if attempt < max_attempts - 1:
                time.sleep(RETRY_SLEEP_SECONDS)
            continue
        return report
    raise AuditError(f"重试 {max_attempts} 次后仍未获得合法报告，最后一次错误: {last_error}")

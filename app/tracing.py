"""可选的 Langfuse 追踪。

配置 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY（可选 LANGFUSE_HOST，
默认 https://cloud.langfuse.com）后自动开启；未配置时全部调用为 no-op，
不影响本地使用与测试。
"""
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_client: Any = None
_client_checked = False


def get_langfuse() -> Any | None:
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return None
    try:
        from langfuse import Langfuse

        _client = Langfuse()
    except Exception as e:  # noqa: BLE001 - 追踪失败不能影响业务
        logger.warning("Langfuse 初始化失败，追踪已停用: %s", e)
        _client = None
    return _client


def trace_llm_call(
    *,
    name: str,
    model: str,
    input_payload: Any,
    output: str | None = None,
    usage: dict | None = None,
    latency_ms: int | None = None,
    error: str | None = None,
) -> None:
    """记录一次 LLM 调用。任何失败都静默吞掉——追踪永远不能弄挂业务。"""
    lf = get_langfuse()
    if lf is None:
        return
    try:
        generation = lf.start_generation(
            name=name,
            model=model,
            input=input_payload,
            metadata={"latency_ms": latency_ms} if latency_ms is not None else None,
        )
        generation.end(
            output=output,
            usage=usage,
            level="ERROR" if error else "DEFAULT",
            status_message=error,
        )
        lf.flush()
    except Exception as e:  # noqa: BLE001
        logger.warning("Langfuse 记录失败: %s", e)

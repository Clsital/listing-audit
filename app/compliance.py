"""文案合规模块：广告法极限词/违禁词检测。

双层设计：
1. 词表精确匹配（确定性，零成本，必命中）——覆盖常见极限词；
2. LLM 上下文判断——捕获词表外的风险表述（如"医美级面料"）。
两层结果由代码去重合并，clean 与最终列表以合并结果为准。
"""
import json
import time
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.prompt import build_compliance_prompt
from app.schemas import ProductInfo

WORDLIST_PATH = Path(__file__).parent / "data" / "extreme_words.json"

DEFAULT_MAX_ATTEMPTS = 3
RETRY_SLEEP_SECONDS = 1.0

SUGGESTIONS: dict[str, str] = {
    "绝对化用语": "删除该词，或改为可验证的客观描述（如'精选面料'）",
    "权威背书": "删除无凭证的权威性表述；确有证书时改为可查证的具名认证",
    "虚假承诺": "改为有条件、可履行的表述，避免绝对化承诺",
    "虚假夸大": "改为可验证的事实描述，或补充数据来源",
}


class ComplianceError(RuntimeError):
    """LLM 调用或输出解析在重试后仍失败。"""


class Violation(BaseModel):
    term: str = Field(min_length=1, description="违规词")
    category: str = Field(min_length=1, description="风险类别")
    location: Literal["title", "selling_points"] = Field(description="出现位置")
    context: str = Field(min_length=1, description="原文片段")
    suggestion: str = Field(min_length=1, description="整改建议")
    source: Literal["wordlist", "llm"] = Field(description="检出来源")
    confidence: float = Field(ge=0, le=1, default=1.0)


class ComplianceReport(BaseModel):
    clean: bool = Field(description="是否无违规风险")
    violations: list[Violation]
    summary: str = Field(min_length=1, description="面向商家的一句话总结")


class TextClient(Protocol):
    def chat_text(self, prompt: str) -> str: ...


def load_wordlist(path: Path = WORDLIST_PATH) -> dict[str, list[str]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _context_snippet(text: str, start: int, end: int, width: int = 12) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(text) else ""
    return f"{prefix}{text[left:right]}{suffix}"


def scan_wordlist(product: ProductInfo, wordlist: dict[str, list[str]]) -> list[Violation]:
    """在标题与卖点中精确匹配词表，逐个命中位置生成 Violation。"""
    fields: list[tuple[Literal["title", "selling_points"], str]] = [
        ("title", product.title),
        ("selling_points", product.selling_points),
    ]
    hits: list[Violation] = []
    for location, text in fields:
        if not text:
            continue
        for category, terms in wordlist.items():
            for term in terms:
                start = 0
                while (found := text.find(term, start)) != -1:
                    hits.append(
                        Violation(
                            term=term,
                            category=category,
                            location=location,
                            context=_context_snippet(text, found, found + len(term)),
                            suggestion=SUGGESTIONS.get(category, "删除或改为可验证的客观描述"),
                            source="wordlist",
                            confidence=1.0,
                        )
                    )
                    start = found + len(term)
    return hits


def parse_llm_compliance(raw: str) -> tuple[list[Violation], str]:
    """解析 LLM 的合规输出：{"violations": [...], "summary": "..."}。容忍 markdown 围栏。"""
    from app.llm import extract_json_object

    data = extract_json_object(raw)
    summary = str(data.get("summary", "")).strip()
    violations: list[Violation] = []
    for item in data.get("violations", []):
        item = dict(item)
        item.setdefault("source", "llm")
        item.setdefault("confidence", 0.8)
        try:
            violations.append(Violation.model_validate(item))
        except Exception as e:
            raise ComplianceError(f"LLM 违规项不符合 schema: {e}") from e
    return violations, summary or "未发现违规风险表述"


def merge_violations(
    wordlist_hits: list[Violation], llm_violations: list[Violation]
) -> list[Violation]:
    """词表命中优先；LLM 结果中与词表命中同词/包含关系的项去重。"""
    merged = list(wordlist_hits)
    wordlist_terms = {v.term for v in wordlist_hits}
    for v in llm_violations:
        if any(v.term in t or t in v.term for t in wordlist_terms):
            continue
        merged.append(v)
    return merged


def audit_copy(
    product: ProductInfo,
    client: TextClient,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> ComplianceReport:
    """词表扫描 + LLM 上下文判断，合并输出合规报告。"""
    wordlist_hits = scan_wordlist(product, load_wordlist())
    wordlist_terms = {v.term for v in wordlist_hits}

    last_error = ""
    llm_violations: list[Violation] = []
    summary = ""
    llm_failed = False
    for attempt in range(max_attempts):
        prompt = build_compliance_prompt(product, error_hint=last_error or None)
        try:
            raw = client.chat_text(prompt)
            llm_violations, summary = parse_llm_compliance(raw)
        except Exception as e:  # noqa: BLE001 - 任何失败都重试
            last_error = str(e)
            if attempt < max_attempts - 1:
                time.sleep(RETRY_SLEEP_SECONDS)
            continue
        break
    else:
        # LLM 耗尽重试：降级为纯词表结果，不让整次审核失败
        llm_failed = True

    merged = merge_violations(wordlist_hits, llm_violations)
    if not merged:
        return ComplianceReport(
            clean=True,
            violations=[],
            summary="未发现违规风险表述（词表 + LLM 上下文均未命中）",
        )
    categories = sorted({v.category for v in merged})
    note = "；LLM 上下文判断暂不可用，结果仅来自词表" if llm_failed and not llm_violations else ""
    return ComplianceReport(
        clean=False,
        violations=merged,
        summary=f"发现 {len(merged)} 处风险表述，涉及类别：{'、'.join(categories)}{note}",
    )

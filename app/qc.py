"""AIGC 出图质检：设计师生成候选图后的自动初筛。

检查清单来自设计师人工质检经验：人体结构、服装保真、光影构图、
AI 伪影、文字、场景合理性。verdict（可用/需修图/建议重生成）由代码
按确定性规则计算，模型只负责"看"和描述问题。
"""
from typing import Literal

from pydantic import BaseModel, Field

IssueCategory = Literal[
    "body",      # 人体结构：手指/四肢/面部/牙齿
    "garment",   # 服装保真：颜色/款式/细节与商品信息一致性
    "lighting",  # 光影构图：光源方向/投影/曝光
    "artifact",  # AI 伪影：纹理重复/边缘融蚀/背景扭曲
    "text",      # 文字：乱码/无意义字符
    "scene",     # 场景：背景道具变形/不合理元素
]
Severity = Literal["blocker", "major", "minor"]
Verdict = Literal["usable", "retouch", "regenerate"]


class QcIssue(BaseModel):
    category: IssueCategory = Field(description="问题类别")
    severity: Severity = Field(description="严重程度")
    location: str = Field(min_length=1, description="图中位置，如'右手手指'")
    finding: str = Field(min_length=1, description="具体问题，引用图中可见证据")
    suggestion: str | None = Field(default=None, description="修图/重生成建议")
    confidence: float = Field(default=0.8, ge=0, le=1)


class QcReport(BaseModel):
    # verdict 由 apply_verdict_policy 计算，默认值仅为解析容错
    verdict: Verdict = Field(default="usable")
    issues: list[QcIssue] = Field(default_factory=list)
    summary: str = Field(min_length=1, description="面向设计师的一句话结论")


def apply_verdict_policy(report: QcReport) -> QcReport:
    """blocker → 建议重生成；存在 major → 需修图；其余 → 可直接用。"""
    severities = {issue.severity for issue in report.issues}
    if "blocker" in severities:
        verdict: Verdict = "regenerate"
    elif "major" in severities:
        verdict = "retouch"
    else:
        verdict = "usable"
    return report.model_copy(update={"verdict": verdict})

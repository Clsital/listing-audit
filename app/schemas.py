"""审核报告的结构化定义。

风险等级不交给模型自由发挥，由代码根据检查项确定性计算——
这是本项目的核心设计决策：模型只负责"看"，判定规则留在代码里。
"""
from typing import Literal

from pydantic import BaseModel, Field

CheckDimension = Literal["color", "style", "detail", "copy", "category"]
CheckStatus = Literal["pass", "mismatch", "not_verifiable"]


class ProductInfo(BaseModel):
    """待审核商品的结构化信息，来自商家后台或用户填写。"""

    title: str = Field(description="商品标题")
    category: str = Field(description="类目，如：连衣裙")
    color: str = Field(description="商品颜色，如：米白色")
    selling_points: str = Field(default="", description="卖点文案，分号分隔，可为空")


class CheckItem(BaseModel):
    dimension: CheckDimension = Field(description="检查维度")
    status: CheckStatus = Field(description="检查结果")
    finding: str = Field(min_length=1, description="具体发现，引用图中可见证据")
    suggestion: str | None = Field(default=None, description="mismatch 时给出整改建议")
    confidence: float = Field(ge=0, le=1, description="该条检查的置信度 0-1")


class AuditReport(BaseModel):
    # 以下两个字段由 apply_risk_policy 按确定性规则计算，默认值仅为解析容错
    consistent: bool = Field(default=True, description="图文是否总体相符")
    risk_level: Literal["low", "medium", "high"] = Field(
        default="low", description="客诉风险等级"
    )
    checks: list[CheckItem] = Field(min_length=1)
    summary: str = Field(min_length=1, description="一句话总结，面向商家")


class AuditError(RuntimeError):
    """模型调用或输出解析在重试后仍失败。"""


def apply_risk_policy(report: AuditReport) -> AuditReport:
    """按确定性规则计算 consistent 与 risk_level，覆盖模型给出的同类字段。

    high：颜色或款式不符且置信度 >= 0.7（直接构成客诉风险）；
    medium：存在其他 mismatch；
    low：无 mismatch。
    """
    mismatches = [c for c in report.checks if c.status == "mismatch"]
    high_risk = any(
        c.dimension in ("color", "style") and c.confidence >= 0.7 for c in mismatches
    )
    if high_risk:
        risk = "high"
    elif mismatches:
        risk = "medium"
    else:
        risk = "low"
    return report.model_copy(
        update={"consistent": not mismatches, "risk_level": risk}
    )

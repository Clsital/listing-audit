"""审核提示词。只允许模型输出 JSON，且禁止在信息不足时猜测。"""
from app.schemas import ProductInfo

_PROMPT_TEMPLATE = """你是电商平台的图文一致性审核员。下面是一件商品的 structured 信息和一张商品图。
请逐项核对图片与商品信息是否相符，只输出一个 JSON 对象，不要输出任何其他文字。

检查维度（dimension 取值固定为以下五个）：
- color：图中商品颜色是否与 color 字段一致
- style：款式/版型/品类是否与标题描述一致
- detail：图案、配件、面料质感等细节是否与卖点文案矛盾
- copy：卖点文案是否存在图中无法支持的夸大表述
- category：图片场景是否与类目匹配（如泳衣出现在冬装场景）

每个维度输出一个检查项：
- status："pass"（相符）/ "mismatch"（不符）/ "not_verifiable"（图片无法判断）
- finding：具体发现，必须引用图中可见的证据，用中文
- suggestion：仅 mismatch 时给出整改建议，其余为 null
- confidence：0 到 1 之间的置信度

规则：
1. 图片或商品信息无法支持判断时，status 必须填 not_verifiable，禁止猜测。
2. 找不到任何问题时，checks 也必须覆盖全部五个维度（status 为 pass）。
3. 只输出 JSON：{{"checks": [{{...}}], "summary": "一句话总结，面向商家"}}

商品信息：
- 标题：{title}
- 类目：{category}
- 颜色：{color}
- 卖点：{selling_points}
"""

_RETRY_HINT = """
你上一次的输出未通过校验：{error}
请修正问题，仍然只输出一个符合要求的 JSON 对象。
"""


def build_audit_prompt(product: ProductInfo, error_hint: str | None = None) -> str:
    prompt = _PROMPT_TEMPLATE.format(
        title=product.title,
        category=product.category,
        color=product.color,
        selling_points=product.selling_points or "（无）",
    )
    if error_hint:
        prompt += _RETRY_HINT.format(error=error_hint)
    return prompt

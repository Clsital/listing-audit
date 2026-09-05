"""审核提示词。只允许模型输出 JSON，且禁止在信息不足时猜测。"""
from app.schemas import ProductInfo

_PROMPT_TEMPLATE = """你是电商平台的图文一致性审核员。下面是一件商品的 structured 信息和一张商品图。
请逐项核对图片与商品信息是否相符，只输出一个 JSON 对象，不要输出任何其他文字。

检查维度（dimension 取值固定为以下四个必检项 + 一个条件项）：
- color：图中商品颜色是否与 color 字段一致
- style：款式/版型/品类是否与标题描述一致
- detail：图案、配件、面料质感等细节是否与卖点文案矛盾
- category：图片场景是否与类目匹配（如泳衣出现在冬装场景）
- copy：仅当卖点文案与图中可见内容明显矛盾时（如宣称真丝但图片明显为棉质）才输出此项；文案本身的合规性由专门模块负责，这里不要检查

每个维度输出一个检查项：
- status："pass"（相符）/ "mismatch"（不符）/ "not_verifiable"（图片无法判断）
- finding：具体发现，必须引用图中可见的证据，用中文
- suggestion：仅 mismatch 时给出整改建议，其余为 null
- confidence：0 到 1 之间的置信度

规则：
1. 图片或商品信息无法支持判断时，status 必须填 not_verifiable，禁止猜测。
2. 找不到任何问题时，checks 必须覆盖 color、style、detail、category 四个必检维度（status 为 pass）。
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

_COMPLIANCE_TEMPLATE = """你是电商平台的文案合规审核员。下面是一件商品的标题和卖点文案（多行结构化格式）。
请依据《中华人民共和国广告法》和电商平台规则，找出有违规风险的表述，只输出一个 JSON 对象。

重点检查以下风险类别：
- 绝对化用语：最好、第一、顶级、唯一、完美等
- 权威背书：国家级、驰名商标、官方认证等无凭证表述
- 虚假承诺：100%、永不、绝对、零风险等无法履行的承诺
- 虚假夸大：纯天然、销量冠军、之王等无依据表述
- 词表之外的风险表述：结合上下文判断（如"医美级""欧洲标准"等暗示功效或权威的措辞）

注意：
1. 正常的功能性描述（如"显瘦""保暖""可脱卸""一衣两穿"）不属于违规，不要误报。
2. 服装类目不涉及医疗功效表述，除非文案明示治疗/治愈功能。
3. 每个风险项输出：term（违规词原文）、category（上述类别之一）、location（"title" 或 "selling_points"）、context（原文片段）、suggestion（给出可直接替换的合规改写）、confidence（0-1）。
4. 只输出 JSON：{{"violations": [{{...}}], "summary": "面向商家的一句话总结"}}

商品文案：
- 标题：{title}
- 卖点文案：
{selling_points}
"""


def build_compliance_prompt(product: ProductInfo, error_hint: str | None = None) -> str:
    prompt = _COMPLIANCE_TEMPLATE.format(
        title=product.title,
        selling_points=product.selling_points or "（无）",
    )
    if error_hint:
        prompt += _RETRY_HINT.format(error=error_hint)
    return prompt


_QC_TEMPLATE = """你是资深电商视觉设计师的质检助手。下面这张图是 AIGC 工具生成的服装模特候选图，
请按设计师的人工质检清单逐项检查，找出问题并给出处理判定，只输出一个 JSON 对象。

检查类别（category 固定取值）与要点：
- body 人体结构：手指数量与形态、四肢关节、面部五官与对称性、牙齿、耳朵——放大看细节
- garment 服装保真：颜色、款式（领型/袖型/长短）、纽扣/印花/蕾丝等细节、面料质感是否与商品信息一致；生成图最常见的失败是服装被"AI 重绘"导致细节漂移
- lighting 光影构图：光源方向是否自洽、投影是否正确、是否存在过曝/死黑
- artifact AI 伪影：布料纹理重复、发丝/边缘融蚀、背景元素扭曲融化、皮肤塑料感
- text 文字：图中任何文字（品牌 logo、吊牌、背景招牌）是否乱码或无意义字符
- scene 场景：背景与道具是否合理（家具/植物/地面透视是否变形）

严重程度（severity）：
- blocker：消费者一眼可见的硬伤（六指、面部扭曲、文字乱码）——必须重新生成
- major：需要修图的明确问题（服装细节漂移、局部伪影）——可以修图解决
- minor：可接受的轻微瑕疵（轻微纹理重复、背景小瑕疵）

每个问题输出：category、severity、location（图中位置，如"右手手指"）、finding（引用图中可见证据，中文）、suggestion（修图思路或重生成时 prompt 要避开什么）、confidence（0-1）。
没有问题的类别不要输出；全部通过时 issues 为空数组。
只输出 JSON：{{"issues": [{{...}}], "summary": "面向设计师的一句话结论，说明这张图能不能用、重点修哪里"}}

商品信息（用于服装保真核对）：
- 标题：{title}
- 类目：{category}
- 颜色：{color}
- 卖点：{selling_points}
"""


def build_qc_prompt(product: ProductInfo, error_hint: str | None = None) -> str:
    prompt = _QC_TEMPLATE.format(
        title=product.title or "（未提供）",
        category=product.category or "（未提供）",
        color=product.color or "（未提供）",
        selling_points=product.selling_points or "（未提供）",
    )
    if error_hint:
        prompt += _RETRY_HINT.format(error=error_hint)
    return prompt


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

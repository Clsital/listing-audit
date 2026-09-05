"""FastAPI 入口：POST /api/audit 接收商品图与信息，返回结构化风险报告。"""
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile

from app.llm import OpenAICompatVisionClient, audit_listing, image_to_data_url
from app.schemas import AuditError, AuditReport, ProductInfo

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

app = FastAPI(title="listing-audit", version="0.1.0")


def get_auditor():
    """返回审核函数；测试通过 dependency_overrides 注入假实现。

    模型客户端延迟到首次调用时构造，避免无配置环境下依赖解析即失败。
    """

    def auditor(image_data_url: str, product: ProductInfo) -> AuditReport:
        client = OpenAICompatVisionClient()
        return audit_listing(image_data_url, product, client)

    return auditor


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/audit", response_model=AuditReport)
async def audit(
    image: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form(...),
    color: str = Form(...),
    selling_points: str = Form(""),
    auditor=Depends(get_auditor),
) -> AuditReport:
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, detail=f"仅支持 {sorted(ALLOWED_IMAGE_TYPES)}")
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(400, detail="图片内容为空")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(413, detail="图片超过 10MB 上限")
    product = ProductInfo(
        title=title, category=category, color=color, selling_points=selling_points
    )
    image_data_url = image_to_data_url(image_bytes, image.content_type)
    try:
        return auditor(image_data_url, product)
    except AuditError as e:
        raise HTTPException(502, detail=str(e)) from e

"""FastAPI 入口：图文一致性审核 + 文案合规检测。"""
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.compliance import ComplianceError, audit_copy
from app.llm import OpenAICompatVisionClient, audit_listing, image_to_data_url
from app.schemas import AuditError, AuditReport, ProductInfo

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

app = FastAPI(title="listing-audit", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_client() -> OpenAICompatVisionClient:
    # 延迟构造，避免无配置环境下依赖解析即失败
    return OpenAICompatVisionClient()


def get_auditor():
    """返回审核函数；测试通过 dependency_overrides 注入假实现。"""

    def auditor(image_data_url: str, product: ProductInfo) -> AuditReport:
        return audit_listing(image_data_url, product, get_client())

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


@app.post("/api/compliance", response_model=object)
async def compliance(
    title: str = Form(...),
    selling_points: str = Form(""),
    client: OpenAICompatVisionClient = Depends(get_client),
) -> dict:
    product = ProductInfo(title=title, selling_points=selling_points)
    try:
        return audit_copy(product, client)
    except ComplianceError as e:
        raise HTTPException(502, detail=str(e)) from e

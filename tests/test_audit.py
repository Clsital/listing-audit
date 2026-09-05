"""单元测试：不依赖真实模型 API，全部用假客户端。"""
import json

import pytest
from fastapi.testclient import TestClient

from app.llm import AuditError, VisionClient, audit_listing, image_to_data_url, parse_report
from app.main import app, get_auditor
from app.schemas import ProductInfo

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d49444154789c626001000000ffff030000060005"
    "57bfabd40000000049454e44ae426082"
)

REPORT_TEMPLATE = {
    "checks": [
        {"dimension": "color", "status": "pass", "finding": "图中为米白色连衣裙", "confidence": 0.9},
        {"dimension": "style", "status": "pass", "finding": "款式为收腰连衣裙", "confidence": 0.85},
        {"dimension": "detail", "status": "pass", "finding": "无夸大细节", "confidence": 0.8},
        {"dimension": "category", "status": "pass", "finding": "场景匹配女装类目", "confidence": 0.9},
    ],
    "summary": "图文相符，无明显客诉风险",
}


def make_raw_report(**overrides) -> str:
    data = json.loads(json.dumps(REPORT_TEMPLATE))
    for key, value in overrides.items():
        data[key] = value
    return json.dumps(data, ensure_ascii=False)


class FakeClient(VisionClient):
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def chat(self, image_data_url: str, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


PRODUCT = ProductInfo(
    title="法式收腰碎花连衣裙", category="连衣裙", color="米白色", selling_points="雪纺;收腰显瘦"
)


def test_parse_report_and_risk_policy_all_pass():
    report = parse_report(make_raw_report())
    assert report.consistent is True
    assert report.risk_level == "low"
    assert len(report.checks) == 4


def test_parse_report_high_risk_on_color_mismatch():
    raw = make_raw_report(
        checks=json.loads(
            json.dumps(REPORT_TEMPLATE["checks"], ensure_ascii=False)
            .replace("米白色连衣裙", "深蓝色连衣裙")
        )
    )
    # 把第一条 color 改为 mismatch
    data = json.loads(raw)
    data["checks"][0]["status"] = "mismatch"
    report = parse_report(json.dumps(data, ensure_ascii=False))
    assert report.consistent is False
    assert report.risk_level == "high"


def test_parse_report_accepts_markdown_fence():
    report = parse_report(f"以下是审核结果：\n```json\n{make_raw_report()}\n```\n请查收")
    assert report.risk_level == "low"


def test_parse_report_rejects_missing_summary():
    data = json.loads(make_raw_report())
    del data["summary"]
    with pytest.raises(AuditError, match="schema"):
        parse_report(json.dumps(data, ensure_ascii=False))


def test_audit_listing_valid_json_first_try():
    client = FakeClient([make_raw_report()])
    report = audit_listing(image_to_data_url(PNG_1PX, "image/png"), PRODUCT, client)
    assert report.risk_level == "low"
    assert len(client.prompts) == 1


def test_audit_listing_retries_with_error_hint_then_succeeds():
    client = FakeClient(
        [make_raw_report().replace('"summary"', '"summaries"'), make_raw_report()]
    )
    report = audit_listing(image_to_data_url(PNG_1PX, "image/png"), PRODUCT, client)
    assert report.risk_level == "low"
    assert len(client.prompts) == 2
    assert "未通过校验" in client.prompts[1]


def test_audit_listing_gives_up_after_max_attempts():
    client = FakeClient(["不是 JSON"] * 3)
    with pytest.raises(AuditError, match="重试 3 次"):
        audit_listing(image_to_data_url(PNG_1PX, "image/png"), PRODUCT, client)
    assert len(client.prompts) == 3


def test_api_endpoint_returns_structured_report():
    client = FakeClient([make_raw_report()])
    app.dependency_overrides[get_auditor] = lambda: (
        lambda image_data_url, product: audit_listing(image_data_url, product, client)
    )
    try:
        with TestClient(app) as test_client:
            resp = test_client.post(
                "/api/audit",
                files={"image": ("product.png", PNG_1PX, "image/png")},
                data={
                    "title": "法式收腰碎花连衣裙",
                    "category": "连衣裙",
                    "color": "米白色",
                    "selling_points": "雪纺;收腰显瘦",
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["consistent"] is True
    assert body["risk_level"] == "low"
    assert len(body["checks"]) == 4


def test_api_endpoint_rejects_non_image():
    with TestClient(app) as test_client:
        resp = test_client.post(
            "/api/audit",
            files={"image": ("a.txt", b"hello", "text/plain")},
            data={"title": "t", "category": "c", "color": "米白色"},
        )
    assert resp.status_code == 415

"""文案合规模块测试：词表扫描、LLM 合并去重、重试降级、API 端点。"""
import json

from fastapi.testclient import TestClient

from app.compliance import (
    ComplianceError,
    audit_copy,
    load_wordlist,
    parse_llm_compliance,
    scan_wordlist,
)
from app.main import app, get_client
from app.schemas import ProductInfo

# 用户在艾莱依时期的真实多行卖点格式（合规样例）
REAL_COPY = """卖点文案	可脱卸连帽 一衣两穿
戴上时挡风保暖 轻松应对户外 脱下时 简约干练
细节卖点文案	丰富衣身视觉层次感-拼接设计
随时切换造型 适合多场景穿着-橡筋抽绳
卖点文案2	"H"OR"X"随意切换 造型多变
H版廓形 适合多体型穿着 抽紧时为X廓形 修饰腰身曲线"""


def make_llm_raw(violations: list[dict], summary: str = "发现风险表述") -> str:
    return json.dumps({"violations": violations, "summary": summary}, ensure_ascii=False)


class FakeTextClient:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def chat_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def test_wordlist_scan_hits_title_and_points():
    product = ProductInfo(
        title="2026 全网第一 顶级羽绒服",
        selling_points="永久防绒;100%白鸭绒",
    )
    hits = scan_wordlist(product, load_wordlist())
    terms = {(v.term, v.location) for v in hits}
    assert ("第一", "title") in terms
    assert ("顶级", "title") in terms
    assert ("永久", "selling_points") in terms
    assert ("100%", "selling_points") in terms
    for v in hits:
        assert v.source == "wordlist"
        assert v.confidence == 1.0


def test_wordlist_scan_clean_copy_no_false_positive():
    product = ProductInfo(title="可脱卸连帽羽绒服 一衣两穿", selling_points=REAL_COPY)
    assert scan_wordlist(product, load_wordlist()) == []


def test_parse_llm_compliance_adds_source():
    raw = make_llm_raw(
        [
            {
                "term": "医美级面料",
                "category": "虚假夸大",
                "location": "selling_points",
                "context": "…医美级面料…",
                "suggestion": "改为客观面料描述",
            }
        ]
    )
    violations, _ = parse_llm_compliance(raw)
    assert len(violations) == 1
    assert violations[0].source == "llm"


def test_audit_copy_merges_and_dedupes():
    product = ProductInfo(title="顶级羽绒服 第一", selling_points="医美级面料填充")
    client = FakeTextClient(
        [
            make_llm_raw(
                [
                    {  # 与词表命中重复，应被去重
                        "term": "顶级",
                        "category": "绝对化用语",
                        "location": "title",
                        "context": "顶级羽绒服",
                        "suggestion": "删除",
                    },
                    {  # 词表外的新发现
                        "term": "医美级",
                        "category": "虚假夸大",
                        "location": "selling_points",
                        "context": "…医美级面料…",
                        "suggestion": "改为客观面料描述",
                    },
                ]
            )
        ]
    )
    report = audit_copy(product, client)
    assert report.clean is False
    terms = sorted(v.term for v in report.violations)
    assert terms == ["医美级", "第一", "顶级"]
    assert "3 处风险表述" in report.summary


def test_audit_copy_clean_copy_reports_clean():
    product = ProductInfo(title="可脱卸连帽羽绒服", selling_points=REAL_COPY)
    client = FakeTextClient([make_llm_raw([], "未发现违规风险表述")])
    report = audit_copy(product, client)
    assert report.clean is True
    assert report.violations == []


def test_audit_copy_llm_downgrades_to_wordlist_only():
    product = ProductInfo(title="顶级羽绒服", selling_points="")
    client = FakeTextClient(["不是 JSON"] * 3)
    report = audit_copy(product, client)
    assert report.clean is False
    assert [v.term for v in report.violations] == ["顶级"]
    assert all(v.source == "wordlist" for v in report.violations)
    assert "仅来自词表" in report.summary


def test_audit_copy_retries_with_error_hint():
    product = ProductInfo(title="普通羽绒服", selling_points="")
    client = FakeTextClient(["不是 JSON", make_llm_raw([], "未发现违规风险表述")])
    report = audit_copy(product, client)
    assert report.clean is True
    assert len(client.prompts) == 2
    assert "未通过校验" in client.prompts[1]


def test_compliance_api_endpoint():
    client = FakeTextClient([make_llm_raw([], "未发现违规风险表述")])
    app.dependency_overrides[get_client] = lambda: client
    try:
        with TestClient(app) as test_client:
            resp = test_client.post(
                "/api/compliance",
                data={"title": "可脱卸连帽羽绒服", "selling_points": REAL_COPY},
            )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["clean"] is True

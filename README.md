# listing-audit · 电商上架前检查台

上架前双检：**文案合规**（广告法极限词/违禁词，词表 + LLM 双层）+ **图文属性一致性**（商品图 vs SKU 属性，视觉模型）——用于在商品上架前拦截违规文案与图文不符，降低平台处罚与客诉风险。

> 背景：作者在电商视觉岗位上的真实工作流程——靠肉眼核对样衣/大货与页面图片防止客诉、关注文案违规风险。这个项目把该流程工程化。

## 架构

```
React 前端（第 2 周）          CLI / curl
        │                        │
        ▼                        ▼
FastAPI
├── POST /api/compliance   ──►  文案合规：词表精确匹配 + LLM 上下文判断，去重合并
└── POST /api/audit        ──►  图文一致性：JSON schema 约束 + pydantic 校验 + 失败重试
        │
        ▼
模型（任意 OpenAI 兼容端点：DeepSeek / Qwen-VL / GLM-4V / 豆包 …）
        │
        ▼
Langfuse 调用追踪（第 3 周接入）
```

## 核心设计决策

1. **错误来源分层**：文案违规由文案合规模块负责（纯文本即可）；SKU 属性填写错误由图文审核负责（需要看图）；卖点文案与图片的"夸大"检查降级为条件项——因为文案有专门岗位把关，误报成本高。
2. **合规检测双层**：词表命中是确定性的（confidence=1.0）；LLM 负责词表外的上下文风险（如"医美级面料"），结果与词表去重合并；LLM 不可用时降级为纯词表结果，不让审核整体失败。
3. **风险分级规则在代码里，不在模型里**：模型只输出各维度检查项，`consistent` 与 `risk_level` 由 `apply_risk_policy` 按确定性规则计算（颜色/款式 mismatch 且置信度 ≥ 0.7 → high）。
4. **禁止猜测**：视觉审核强制模型在无法判断时输出 `not_verifiable`，而不是编造结论。
5. **不信任模型输出**：JSON 提取（容忍 markdown 围栏）→ pydantic 校验 → 失败时把校验错误回填提示词重试。
6. **厂商无关**：直接调 OpenAI 兼容协议，不绑定 SDK，换模型只改环境变量。

## 快速开始

```bash
uv sync

# 配置任一 OpenAI 兼容模型（视觉审核需视觉模型；合规检测纯文本模型即可）
# 项目根目录建 .env（参考 .env.example），或直接设环境变量：
set LLM_API_KEY=sk-xxx
set LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
set LLM_MODEL=qwen-vl-plus

# 启动 API（Swagger 文档在 /docs）
uv run uvicorn app.main:app --reload

# 文案合规检测（支持多行真实卖点格式）
uv run python scripts/compliance_cli.py --title "2026销量冠军羽绒服" --points-file 卖点.txt

# 图文一致性审核
uv run python scripts/audit_cli.py 商品图.jpg --title "法式连衣裙" --category 连衣裙 --color 米白色 --points "雪纺;收腰"
```

## 测试

```bash
uv run pytest -v
```

17 个测试，不依赖真实模型：词表扫描、LLM 合并去重、重试与降级、风险分级规则、两个 API 端点。

## 评测

`eval/results/` 记录冒烟测试实证：
- `smoke-000`：图文相符基线 → 全 pass
- `smoke-001`：对抗样例（颜色写错）→ color mismatch @0.99，risk=high
- `smoke-002`：合规双实测 → 真实文案 0 误报；注入 6 类违规全部命中（5 词表 + 1 LLM 上下文捕获"医美级面料"）

第 2-3 周扩展为 12-20 张自标注图的跑批准确率表。

## 路线图

- [x] 第 1 周：图文一致性后端（schema 约束、重试、风险分级、CLI、单元测试）
- [x] 第 2 周：文案合规模块（词表 + LLM 双层、去重合并、降级策略）；React 双检工作台；评测跑批脚本
- [ ] 第 3 周：评测集扩充（12-20 条）+ 公网部署 + Langfuse 追踪接入 + README 评测结果表
- [ ] 加餐：图 vs 图对比（主图 vs 白底图，检测大货改版未更新素材）；竞品主图拆解

## 前端开发

```bash
# 终端 1：后端
uv run uvicorn app.main:app --reload
# 终端 2：前端（/api 自动代理到 8000 端口）
cd web && npm install && npm run dev
# 打开 http://localhost:5173
```

## 诚实声明

本项目由 AI 编程协作完成，仓库作者负责问题定义、方案设计决策、验证标准与结果把关，并理解全部代码逻辑。

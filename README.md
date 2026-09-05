# listing-audit · 电商图文一致性审核助手

上传商品图 + 商品信息（标题/类目/颜色/卖点），视觉模型逐项核对图文是否相符，输出结构化风险报告——用于在商品上架前发现"图文不符"问题，降低客诉风险。

> 背景作者在电商视觉岗位上的真实工作流程：过去靠肉眼核对样衣/大货与页面图片是否一致。这个项目把该流程工程化。

## 架构

```
React 前端（第 2 周）          CLI / curl
        │                        │
        ▼                        ▼
FastAPI  POST /api/audit  ──►  结构化输出约束（JSON schema + pydantic 校验 + 失败重试）
        │
        ▼
视觉模型（任意 OpenAI 兼容端点：Qwen-VL / GLM-4V / 豆包 …）
        │
        ▼
Langfuse 调用追踪（第 3 周接入）
```

## 核心设计决策

1. **风险分级规则在代码里，不在模型里**：模型只输出各维度检查项，`consistent` 与 `risk_level` 由 `apply_risk_policy` 按确定性规则计算（颜色/款式 mismatch 且置信度 ≥ 0.7 → high）。模型负责"看"，判定规则可测试、可解释。
2. **禁止猜测**：提示词强制模型在无法判断时输出 `not_verifiable`，而不是编造结论。
3. **不信任模型输出**：JSON 提取（容忍 markdown 围栏）→ pydantic 校验 → 失败时把校验错误回填提示词重试，最多 3 次。
4. **厂商无关**：直接调 OpenAI 兼容协议，不绑定 SDK，换模型只改环境变量。

## 快速开始

```bash
uv sync

# 配置任一 OpenAI 兼容视觉模型
set LLM_API_KEY=sk-xxx
set LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
set LLM_MODEL=qwen-vl-plus

# 启动 API
uv run uvicorn app.main:app --reload

# 或先用命令行跑通
uv run python scripts/audit_cli.py 商品图.jpg --title "法式连衣裙" --category 连衣裙 --color 米白色 --points "雪纺;收腰"
```

## 测试

```bash
uv run pytest -v
```

测试不依赖真实模型：用假客户端覆盖 JSON 解析容错、重试与错误回填、风险分级规则、API 上传校验。

## 评测计划（第 2 周）

在 `eval/` 放 12-20 张自行标注的商品图（`manifest.csv`：图片路径 + 人工标注的 consistent 标签），跑批后输出准确率表。样例格式见 `eval/manifest.example.csv`。

## 路线图

- [x] 第 1 周：后端核心链路（schema 约束、重试、风险分级、CLI、单元测试）
- [ ] 第 2 周：React 上传页 + 评测集跑批 + 准确率表
- [ ] 第 3 周：公网部署 + Langfuse 追踪接入 + README 评测结果
- [ ] 加餐：竞品主图拆解（同一后端换 prompt 与 schema）

## 诚实声明

本项目由 AI 编程协作完成，仓库作者负责问题定义、方案设计决策、验证标准与结果把关，并理解全部代码逻辑。

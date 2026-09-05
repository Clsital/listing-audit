# listing-audit · AIGC 出图质检台

设计师的自用工具：**AIGC 生成图自动初筛**（人体结构/服装保真/AI 伪影 → 可直接用 / 需修图 / 建议重生成）+ **上架前图文核对** + **文案合规**（极限词双层检测）。

> 背景：作者是电商视觉设计师，日常用绘蛙/即梦等 AIGC 工具生成模特图后需要人工逐张质检（手部畸形、服装细节漂移、纹理融蚀、投影断层）。这个项目把个人质检经验写成机器可执行的检查清单，再让视觉模型执行它。

## 架构

```
React 前端（web/）             CLI / curl
        │                        │
        ▼                        ▼
FastAPI
├── POST /api/qc           ──►  出图质检：六类缺陷清单（人体/服装/光影/伪影/文字/场景）
├── POST /api/compliance   ──►  文案合规：词表精确匹配 + LLM 上下文判断，去重合并
└── POST /api/audit        ──►  图文核对：JSON schema 约束 + pydantic 校验 + 失败重试
        │
        ▼
模型（任意 OpenAI 兼容端点：DeepSeek / Qwen-VL / GLM-4V / 豆包 …）
        │
        ▼
Langfuse 调用追踪（接入中）
```

## 核心设计决策

1. **判定规则在代码里，不在模型里**：质检 verdict（可直接用/需修图/建议重生成）由 `apply_verdict_policy` 按确定性规则计算——blocker→重生成、major→修图、其余可用；模型只负责"看"和描述问题。
2. **检查清单来自一线质检经验**：六类缺陷与严重程度定义就是设计师人工初筛的 checklist，模型照单执行。
3. **禁止猜测**：视觉审核强制模型在无法判断时输出 `not_verifiable`，而不是编造结论。
4. **合规检测双层**：词表命中确定性（confidence=1.0）；LLM 负责词表外的上下文风险（如"医美级面料"），去重合并；LLM 不可用时降级为纯词表结果。
5. **不信任模型输出**：JSON 提取（容忍 markdown 围栏）→ pydantic 校验 → 失败时把校验错误回填提示词重试。
6. **厂商无关**：直接调 OpenAI 兼容协议，换模型只改环境变量。

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

26 个测试，不依赖真实模型：QC 判定策略、词表扫描、LLM 合并去重、重试与降级、风险分级、三个 API 端点。

## 评测

`eval/results/` 记录冒烟测试实证：
- `smoke-000`：图文相符基线 → 全 pass
- `smoke-001`：对抗样例（颜色写错）→ color mismatch @0.99，risk=high
- `smoke-002`：合规双实测 → 真实文案 0 误报；注入 6 类违规全命中（5 词表 + 1 LLM 上下文捕获"医美级面料"）
- `smoke-003`：出图质检首测 → 命中手部粘连、蕾丝纹理漂移、投影断层等 AIGC 经典缺陷，判定"需修图"并给出可执行修图建议

## 路线图

- [x] 图文一致性后端（schema 约束、重试、风险分级、CLI、单元测试）
- [x] 文案合规模块（词表 + LLM 双层、去重合并、降级策略）
- [x] React 三标签工作台（深色主题）+ 评测跑批脚本
- [x] 出图质检模块（六类缺陷清单、verdict 分级策略）+ 首测命中 AIGC 经典缺陷
- [ ] 评测集扩充（QC 用 AIGC 生成图自标注）+ 公网部署 + Langfuse 追踪 + 准确率表
- [ ] 加餐：图 vs 图对比（生成图 vs 白底图服装保真）；竞品主图拆解 brief

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

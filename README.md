# 魔饮咖啡工作台（求职作品）

面向咖啡代工企业（ODM/OEM）的**货品申领与审批工作台**：提交单据 → AI 辅助校验 → 生产经理审批 → 全程留痕，并内置一套可检索、可引用、按密级过滤的**制度知识库**。

> 这是一个**求职作品**，业务场景基于咖啡代工行业的公开信息（冷萃液 / 冻干 / 闪萃三条产线、出口合规）搭建，页面数据均为虚构，与企业内部系统无关。仓库中的制度语料、部署配置与演示口令均已移除，说明见下文「开源说明」。

---

## 一、功能

| 页面 | 路由 | 做了什么 |
|---|---|---|
| 登录 | `/login` | 工号登录；角色一键切换 |
| 工作台首页 | `/` | 单据统计、最近单据、知识库入口 |
| 单据提交 | `/claims/new` | 多明细行表单、草稿保存、AI 摘要、AI 合规校验、提交前拦截 |
| 我的单据 / 待我审批 | `/claims`、`/pending` | 分页、按状态 / 车间 / 日期 / 关键字筛选；窄屏自动切换为卡片列表 |
| 单据详情 | `/claims/:id` | 状态流转条、单据信息、货品明细、审批历史四段留痕、右侧 Agent 侧栏（SSE 流式） |
| 制度知识库 | `/kb` | 条款级检索、引用出处、密级拦截提示、制度目录、全文预览抽屉 |
| 项目说明 | `/about` | 岗位对照、架构、技术取舍、已完成 / 未完成，无需登录 |

**AI 的三处用法**（都带降级，LLM 超时不阻断业务）：

1. 建单时生成摘要（提示词输入整张单据）
2. 提交前做规则 + 模型双重校验，给出可执行的修改建议
3. 单据详情侧栏对话，SSE 逐字返回，支持多轮

## 二、技术栈

- 前端：Vite 5 + React 18 + TypeScript + Tailwind CSS 3，自建 shadcn 风格组件（无额外 UI 依赖）
- 后端：FastAPI + SQLAlchemy 2.0 Async + Pydantic v2
- Agent：LangChain 0.3 ReAct + 通义千问 Qwen-Plus（对话与向量化共用一把百炼 Key）
- 数据：SQLite（开发 / 演示）→ PostgreSQL（生产，`POSTGRES_*` 环境变量）
- 鉴权：JWT（python-jose）+ bcrypt；接口限流：slowapi + 自研 ASGI 中间件

## 三、架构要点

**单端口**：前端 `dist` 由 FastAPI 直接托管，一个进程同时提供页面与 API，省掉单独的静态服务器和 Nginx 反向代理。`/api/*`、`/docs` 等前缀保留 JSON 404，不会被 SPA 路由吞掉。

**零迁移适配层**：Agent 后端原有模型只有 `title` / `content` 两个业务字段，前端需要的是结构化申领单。做法是在 `Document.content` 里存 JSON 信封（`{"v":1, code, workshop, items, urgency, events}`），由 `server/backend/app/routes/claims.py`（约 560 行、11 个接口）负责双向映射，**不改 models.py、不改 agent/**，老数据（纯文本 content）也能读。

**三道检索门控**（`server/rag/`）：

| 门控 | 规则 |
|---|---|
| 时效 | 只返回 `status=active` 且 `effective_date ≤ 今天` 的条款，废止 / 未生效一律不出现 |
| 密级 | 提交人 = public + internal；审批人 + restricted；涉密仅管理员 |
| 车间 | 冻干曲线不会出现在萃取车间的检索结果里 |

## 四、目录结构

```
魔饮咖啡工作台/
├── src/                     前端源码
│   ├── pages/               7 个页面（登录 / 首页 / 建单 / 列表 / 详情 / 知识库 / 说明）
│   ├── components/          UI 组件、布局、Agent 面板、制度全文渲染器
│   └── lib/                 api.ts（接口层与 SSE 解析）、types.ts、auth.ts、mock.ts
├── server/                  后端
│   ├── backend/app/         FastAPI 应用：routes/（claims、kb、agent、documents…）、models、middleware
│   ├── rag/                 知识库框架：loader、splitter、filters、retriever（语料未随仓库发布）
│   ├── agent/               LangChain ReAct Agent 与工具
│   └── tests/               54 项自动化测试
└── scripts/build_deploy.py  生成独立部署包（产物目录不入库）
```

## 五、本地启动

需要 Node 18+、Python 3.11+（本项目在 Node 22 / Python 3.13 验证）。

**后端**

```bash
cd server
python -m venv .venv
./.venv/Scripts/activate           # Windows；macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt -i https://pypi.org/simple
cp .env.example .env               # 填入 LLM API Key，可选配置 JWT_SIGNING_KEY / DEMO_SEED_PASSWORD
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --reload
```

启动时自动建表并写入两个种子账号（工号 `0001` 员工、`1001` 审批人）。**演示口令不写在代码里**：通过环境变量 `DEMO_SEED_PASSWORD` 指定；不设置时每次首次启动随机生成并打印在日志里。接口文档：<http://127.0.0.1:8001/docs>

**前端**

```bash
npm install
npm run dev                        # http://localhost:5173，/api 代理到 8001
```

`.env` 中 `VITE_API_BASE_URL=/api/v1`、`VITE_USE_MOCK=false`；把 `VITE_USE_MOCK` 设为 `true` 可脱离后端看纯前端效果。

## 六、测试

```bash
cd server
./.venv/Scripts/python.exe -m pytest tests/ -v
```

54 项覆盖：知识库门控（时效 / 密级 / ACL / 车间 / 切分 / front-matter）、知识库接口（统计、目录、检索、全文预览 403）、pgvector 门控 SQL 与混合检索 RRF 融合、限流中间件与单端口路由、单据删除回归、登录态回归（签发/校验同一把钥匙、login→me 全链路、网关改写 Authorization 头场景）、LLM 成本护栏（日配额、预算熔断、跨天归零、日志不含密钥）、Agent 对话的单据上下文注入（归属校验 / 400 / 404）。

## 七、知识库语料（需自备）

知识库的**框架代码随仓库发布，制度语料不随仓库发布**。`server/rag/corpus/` 目前为空目录，放入你自己的制度 Markdown（带 front-matter）即可使用：

```
doc_id: MO-SOP-001
version: v1.0
effective_date: 2026-01-01
status: active
confidentiality: internal        # public / internal / restricted / secret
acl_roles: [submitter, approver]
related_claims: []
---
条款正文……
```

配套工具：

```bash
cd server
./.venv/Scripts/python.exe -m rag.loader              # 盘点：覆盖率、缺口、元数据问题
./.venv/Scripts/python.exe -m rag.retriever "检索词"   # 检索验证
```

## 八、开源说明（哪些内容没有发布）

- **制度语料**：`server/rag/corpus/` 中的企业内部制度文档（质量合规、生产 SOP、配方保密、人事、财务等）不随仓库发布，仅保留知识库框架代码与 `test_rag_gates.py` 自建的临时语料夹具
- **部署包**：`deploy/` 构建产物不入库，需要时运行 `python scripts/build_deploy.py` 自行生成
- **演示站点**：不提供公网演示地址；请按第五节在本地启动
- **凭据**：LLM API Key 通过 `server/.env` 注入（见 `.env.example`，键位留空）；JWT 签名密钥通过 `JWT_SIGNING_KEY` 环境变量配置，多副本部署必须统一
- **演示口令**：通过 `DEMO_SEED_PASSWORD` 环境变量设置，不写死在代码里

## 九、已知限制

- 检索后端分环境：本地 `RAG_BACKEND=hybrid`（关键词 + pgvector 向量，RRF 融合），托管环境用 `keyword`（平台不提供外部数据库）。两条路径都已在 `RetrieverFactory` 兜底，向量库初始化失败自动降级为关键词而非报错
- 向量库需离线重建：语料变更后跑 `python -m rag.pgvector_store rebuild`，否则检索仍命中旧版本
- AI 校验以本地规则为主，尚未把知识库条款引用回填到提示语
- Agent 工具仍是示例级（计算器、模拟搜索），未接真实库存 / ERP
- 演示环境为 SQLite，实例重启后数据回到初始状态

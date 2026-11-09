# 知识库（RAG / 制度库）

魔饮咖啡（青岛）有限公司内部制度知识库。**当前阶段只做"备料 + 检索"**，
向量化后端接口已留好但未启用。

## 目录结构

```
rag/
├── corpus/                      制度正文（唯一需要人工维护的地方）
│   ├── manifest.yaml            台账：该收哪些制度、收没收齐
│   ├── _TEMPLATE.md             新文档模板（含 front-matter 规范）
│   ├── 01_制度流程/             P0 单据与审批规则
│   ├── 02_质量合规/             P1 HACCP、追溯、出口合规
│   ├── 03_生产SOP/              P2 三条产线作业指导
│   ├── 04_供应链与客户/         P3 配方保密、客诉、BOM
│   ├── 05_人事培训/             P2 培训手册、安全
│   ├── 06_财务采购/             P3 采购、报销
│   └── _archive/                废止文档归档（status=archived）
├── schema.py                    元数据模型 DocMeta + 枚举
├── filters.py                   检索门控（时效 / 密级 / 车间）
├── splitter.py                  按「章-条」切分，保留条款号
├── loader.py                    扫描 + front-matter 校验 + 覆盖率盘点
├── retriever.py                 关键词检索（现用）/ 向量检索（预留）
└── vector_store.py              Chroma 实现（未启用）
```

## 新增一份制度

1. 从 `corpus/_TEMPLATE.md` 复制，按 `<doc_id>_<标题>_<版本>.md` 命名，
   放进 `corpus/` 下对应目录。
2. 在 `corpus/manifest.yaml` 里把该条目的 `status` 改成 `delivered`。
3. 校验：

```bash
cd server
python -m rag.loader                              # 元数据校验 + 覆盖率
python -m rag.retriever "加急单谁能批"              # 检索验证
python -m rag.retriever "驳回要不要写意见"
```

## 三道检索闸门（filters.py）

| 闸门 | 规则 | 为什么需要 |
|---|---|---|
| 时效 | `status=active` 且 `effective_date ≤ today` 且未过期 | 防止 Agent 引用废止条文做审批判断 |
| 密级 | `conf_level ≤ 角色权限`（submitter 1 / approver 2 / admin 3） | 配方、报价、薪酬不进通用检索池 |
| 范围 | 文档 `related_workshops` 为空=全厂，否则需与当前车间有交集 | 避免冻干车间拿到萃取车间的参数标准 |

日期在 Chroma 里以整数 `YYYYMMDD` 冗余存储（`effective_int` / `expire_int`），
因为 Chroma 的 `where` 不支持日期字符串比较。

## 启用向量检索

### 方式一：PostgreSQL + pgvector（推荐，生产同构）

```bash
pip install "psycopg[binary]"
docker compose up -d postgres           # pgvector/pgvector:pg16 镜像，init-db.sql 自动建表
python -m rag.pgvector_store rebuild    # 全量向量化入库（通义 text-embedding-v3, 1024 维）
python -m rag.pgvector_store            # 查看 chunk 数 / 覆盖文档数
```

然后把 `.env` 的 `RAG_BACKEND` 改成 `pgvector`（或 `hybrid`）重启后端。
上层 Agent 接口不变（`retriever.as_context(query, viewer)`）。

- 门控（时效/密级/车间）在 SQL 里下推执行（`filters.build_pg_where`），
  与 keyword/Chroma 版共用同一份 `post_filter` 兜底，口径不会漂移
- `RAG_BACKEND=hybrid` 启用关键词+向量双路召回，RRF 融合：
  关键词路精确命中制度术语，向量路接住口语化提问

### 方式二：Chroma（备选，未启用）

```bash
pip install chromadb -i https://pypi.org/simple
python -m rag.vector_store rebuild        # 全量建集合
python -m rag.vector_store                # 查看 chunk 数
```

然后把 `RetrieverFactory.get(backend="vector")` 用起来即可。上层 Agent
接口不变（`retriever.as_context(query, viewer)`）。

## 保密红线（不要入池）

- 客户配方比例、工艺参数现值 → 放 `confidentiality: secret` + `acl_roles: [admin]`
- 客户合同与报价 → 不入知识库，只留 `MO-SCM-002` 的处理流程
- 员工身份证、薪酬明细、体检报告 → 不入知识库
- 未生效草案 → `status: draft`，检索自动排除

## 与工作台的关系

| 场景 | 用法 |
|---|---|
| 表单页 AI 校验 | `/agent/claims/validate` 命中条款后，把「缺什么/不符合哪条」回填到提示里 |
| 审批人提问 | 详情页 Agent 侧栏检索，回答必须带《制度名》+ 版本 + 条款号 |
| 超时预警 | 检索 MO-SOP-003 的时限数值，与单据时间戳比对 |

**AI 校验结论只是参考**，制度里已明确审批责任在审批人（MO-SOP-002 第 4.1 条）。

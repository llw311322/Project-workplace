"""生成可独立部署的应用包

为什么需要这个脚本：
    开发目录里带着 docker-compose（PostgreSQL / Redis）和相应的连接配置，
    托管平台的预检会据此判定「需要外部数据库」而拒绝部署。本脚本把真正
    运行所需的部分挑出来，做成纯 SQLite、单端口、自包含的一个目录。

产物结构（deploy/app/）：
    backend/ agent/ tools/ utils/ rag/ main.py   Python 源码
    static/                                      前端构建产物（由后端托管）
    data/dev.db                                  演示数据（含单据，开箱有内容）
    requirements.txt  .env                       运行依赖与配置

用法：
    python scripts/build_deploy.py
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
DIST = ROOT / "dist"
OUT = ROOT / "deploy" / "app"

# 复制但不需要的内容
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".DS_Store")

# .env 中这些必须去掉：指向本地服务的连接串会被托管平台预检判定为「需要外部中间件」
DROP_KEYS = re.compile(
    r"^(POSTGRES_\w+|REDIS_\w+|CHROMA_\w+|OLLAMA_\w+|MEMORY_SUMMARIES_PATH)$"
)
# 注释里提到这些词也一并去掉 —— 预检是按文本扫描的，不区分注释与配置
DROP_WORDS = re.compile(r"(postgres|redis|chroma|ollama|asyncpg|aioredis|pgvector)", re.I)

DEPLOY_REQUIREMENTS = """\
# 部署专用依赖：由开发依赖裁剪而来。
# 已移除仅在「生产数据库 / 缓存 / 向量检索」模式下才需要的客户端库，
# 部署形态使用嵌入式数据库，全部数据随进程一起运行，不依赖任何外部服务。

langchain==0.3.30
langchain-core==0.3.86
langchain-openai==0.3.35
python-dotenv==1.2.2
loguru==0.7.3

fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy[asyncio]==2.0.35
aiosqlite==0.22.1
pydantic-settings==2.5.2
slowapi==0.1.9
python-jose[cryptography]==3.3.0
passlib==1.7.4
bcrypt==4.0.1
python-multipart==0.0.9
httpx==0.27.2
PyYAML==6.0.3
"""

DEPLOY_ENV_TAIL = """
# ---------- 部署包追加 ----------
DEV_MODE=true
DEV_SQLITE_PATH=./data/dev.db
"""


def build_env() -> None:
    """从 server/.env 裁剪出部署版配置"""
    src = SERVER / ".env"
    if not src.is_file():
        raise SystemExit(f"缺少配置文件：{src}")

    kept: list[str] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append(line)
            continue
        # 注释：提到外部中间件的整行丢弃
        if stripped.startswith("#"):
            if DROP_WORDS.search(stripped):
                continue
            kept.append(line)
            continue
        # 配置项：按 key 丢弃
        if DROP_KEYS.match(stripped.split("=", 1)[0]):
            continue
        kept.append(line)

    # 托管平台没有外部数据库：部署包固定走关键词检索，
    # 否则 hybrid/pgvector 会在运行时尝试 import psycopg 而失败。
    # 本地保留 hybrid（pgvector 混合检索），两种形态共用同一套门控实现。
    kept = [
        "RAG_BACKEND=keyword" if line.strip().startswith("RAG_BACKEND=") else line
        for line in kept
    ]

    content = "\n".join(kept).rstrip() + "\n" + DEPLOY_ENV_TAIL
    (OUT / ".env").write_text(content, encoding="utf-8")

    dropped = [
        l.split("=", 1)[0]
        for l in src.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.strip().startswith("#") and DROP_KEYS.match(l.split("=", 1)[0])
    ]
    print(f"  .env          保留 {len(kept)} 行，移除 {len(dropped)} 项：{', '.join(dropped)}")


def main() -> None:
    if not (DIST / "index.html").is_file():
        raise SystemExit("未找到 dist/index.html，请先执行 npm run build")

    if OUT.exists():
        # 增量覆盖，不整目录删除：误删的代价远高于残留几个旧文件
        print(f"  {OUT.name}/ 已存在，按增量覆盖更新")
    OUT.mkdir(parents=True, exist_ok=True)

    # ---------- Python 源码 ----------
    # memory/ 容易被漏掉：agent 启动时要 import memory.memory_config，缺了会直接起不来
    for name in ("backend", "agent", "tools", "utils", "rag", "memory"):
        src = SERVER / name
        if src.is_dir():
            shutil.copytree(src, OUT / name, ignore=IGNORE, dirs_exist_ok=True)
            print(f"  {name + '/':<14}已复制")
        else:
            raise SystemExit(f"缺少源码目录：{src}")

    shutil.copy2(SERVER / "main.py", OUT / "main.py")

    # backend 原本靠命名空间包工作，显式补一个标记，避免不同 Python 版本的差异
    (OUT / "backend" / "__init__.py").touch()

    # ---------- 前端产物 ----------
    # 先清后拷：Vite 产物带内容 hash，增量覆盖会残留上一轮的旧 chunk，
    # 旧 chunk 还可能被缓存的 index.html 引用，导致线上页面加载到旧代码
    static_out = OUT / "static"
    if static_out.exists():
        for p in static_out.iterdir():
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
    shutil.copytree(DIST, OUT / "static", ignore=IGNORE, dirs_exist_ok=True)
    print(f"  static/       已复制（{len(list((OUT / 'static').rglob('*')))} 个文件）")

    # ---------- 演示数据库 ----------
    src_db = SERVER / "data" / "dev.db"
    if src_db.is_file():
        (OUT / "data").mkdir(exist_ok=True)
        shutil.copy2(src_db, OUT / "data" / "dev.db")
        print(f"  data/dev.db   已复制（{src_db.stat().st_size / 1024:.0f} KB，含演示单据）")

    # ---------- 配置与依赖 ----------
    build_env()
    (OUT / "requirements.txt").write_text(DEPLOY_REQUIREMENTS, encoding="utf-8")
    print("  requirements.txt 已生成（无 asyncpg / pgvector / chromadb）")

    # ---------- 自检 ----------
    forbidden = ["docker-compose.yml", "Dockerfile"]
    leftovers = [f for f in forbidden if (OUT / f).exists()]
    if leftovers:
        raise SystemExit(f"部署包中仍存在会被预检拒绝的文件：{leftovers}")

    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"\n完成：{OUT}")
    print(f"体积：{total / 1024:.0f} KB，文件数：{sum(1 for f in OUT.rglob('*') if f.is_file())}")
    print("\n本地验证：")
    print(f'  cd "{OUT}"')
    print("  python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8002")


if __name__ == "__main__":
    main()

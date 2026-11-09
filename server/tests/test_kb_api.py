"""
知识库接口的进程内测试。

不经过 HTTP 登录：直接覆盖 get_current_user 依赖，
这样既能验证密级逻辑，又不需要在测试里存账号密码。
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from backend.app.dependencies import get_current_user  # noqa: E402
from backend.app.main import app  # noqa: E402

SUBMITTER = SimpleNamespace(id=1, role="submitter", username="submitter01")
APPROVER = SimpleNamespace(id=2, role="approver", username="approver01")
ADMIN = SimpleNamespace(id=3, role="admin", username="admin01")


@pytest.fixture()
def client():
    """按角色返回不同身份的 TestClient 工厂"""
    def _make(user):
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def test_stats_shape(client):
    res = client(APPROVER).get("/api/v1/kb/stats")
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["available"] is True
    assert data["total_loaded"] > 0
    assert data["chunks"] > 0
    assert len(data["categories"]) >= 5
    assert data["visible_docs"] <= data["total_docs"]


def test_docs_list_marks_restricted(client):
    res = client(SUBMITTER).get("/api/v1/kb/docs")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total"] > 0
    # 提交人看得到清单，但涉密文档标记为不可读
    restricted = [d for d in data["list"] if not d["readable"]]
    assert restricted, "提交人应至少有一份不可读制度（客户配方类）"
    assert data["visible"] == data["total"] - len(restricted)


def test_search_returns_citation(client):
    res = client(APPROVER).post("/api/v1/kb/search", json={"query": "驳回必须写意见吗", "top_k": 5})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total"] > 0
    top = data["hits"][0]
    # 必须带可回溯的引用路径，否则审批人不会信
    assert "《" in top["breadcrumb"]
    assert top["clause"]
    assert top["text"]
    assert top["doc_id"].startswith("MO-")


def test_search_recall_specific_clause(client):
    """已知答案的查询要能命中对应制度"""
    res = client(ADMIN).post("/api/v1/kb/search", json={"query": "加急单需要谁加签", "top_k": 8})
    data = res.json()["data"]
    doc_ids = {h["doc_id"] for h in data["hits"]}
    assert "MO-SOP-005" in doc_ids or "MO-SOP-002" in doc_ids


def test_clearance_hides_secret_from_submitter(client):
    """同一句话：管理员查得到配方规定，提交人查不到"""
    q = "A客户的配方能不能给B客户用"

    admin_data = client(ADMIN).post("/api/v1/kb/search", json={"query": q, "top_k": 6}).json()["data"]
    assert any(h["doc_id"] == "MO-SCM-001" for h in admin_data["hits"]), "管理员应命中配方保密规定"

    sub_data = client(SUBMITTER).post("/api/v1/kb/search", json={"query": q, "top_k": 6}).json()["data"]
    assert all(h["doc_id"] != "MO-SCM-001" for h in sub_data["hits"]), "提交人不该看到配方保密规定"
    # 并且要有被拦下的计数，供前端说明
    assert sub_data["suppressed_docs"] >= 1


def test_empty_query_rejected(client):
    res = client(APPROVER).post("/api/v1/kb/search", json={"query": "", "top_k": 5})
    assert res.status_code == 422


# --------------------------------------------------- 全文预览与权限范围


def test_approver_sees_every_document(client):
    """审批人（李四）拥有全部制度的查看权限"""
    data = client(APPROVER).get("/api/v1/kb/docs").json()["data"]
    assert data["visible"] == data["total"], "审批人应能看到全部制度"
    assert all(d["readable"] for d in data["list"])


def test_submitter_sees_only_employee_level(client):
    """员工（张三）只能看员工类制度：公开 + 内部"""
    data = client(SUBMITTER).get("/api/v1/kb/docs").json()["data"]
    readable = [d for d in data["list"] if d["readable"]]
    assert readable, "员工至少能看到内部制度"
    assert all(d["confidentiality"] in ("public", "internal") for d in readable)
    assert data["visible"] < data["total"]


def test_doc_preview_full_text_for_approver(client):
    """审批人可预览涉密制度全文"""
    res = client(APPROVER).get("/api/v1/kb/doc/MO-SCM-001")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["title"] == "客户定制配方与保密管理规定"
    assert "第一章" in data["body"]
    assert data["char_count"] > 500


def test_doc_preview_forbidden_for_submitter(client):
    """员工看涉密制度：403，且提示里说明密级与当前身份"""
    res = client(SUBMITTER).get("/api/v1/kb/doc/MO-SCM-001")
    assert res.status_code == 403
    body = res.json()
    msg = str(body.get("message") or body.get("detail") or "")
    assert "涉密" in msg
    assert "员工" in msg


def test_doc_preview_internal_ok_for_submitter(client):
    """员工可以正常预览内部制度"""
    res = client(SUBMITTER).get("/api/v1/kb/doc/MO-SOP-001")
    assert res.status_code == 200
    assert "单据提交流程规定" in res.json()["data"]["title"]


def test_doc_preview_unknown_id(client):
    res = client(APPROVER).get("/api/v1/kb/doc/MO-NOT-EXIST")
    assert res.status_code == 404

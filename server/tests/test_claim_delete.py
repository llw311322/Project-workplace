"""
删除单据的回归测试。

背景：`approval_logs.document_id` 外键没有级联删除，历史上删除一张有审批
流水的单据会返回 500。修复后删除前先清理留痕，这里把行为钉住。

测试直接打进程内接口（覆盖 get_current_user），不经过登录接口。
测试产生的数据在 finally 里清掉，不污染演示库。
"""
from __future__ import annotations

import sqlite3
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

DB = SERVER_DIR / "data" / "dev.db"
SUBMITTER = SimpleNamespace(id=1, role="submitter", username="0001", display_name="张三")
APPROVER = SimpleNamespace(id=2, role="approver", username="1001", display_name="李四")


@pytest.fixture()
def client():
    def _make(user):
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def _create(client, title: str = "删除回归测试单据") -> int:
    res = client(SUBMITTER).post(
        "/api/v1/claims",
        json={
            "title": title,
            "workshop": "萃取车间",
            "workshopCode": "EX-01",
            "applicant": "张三",
            "applicantTitle": "车间主管",
            "phone": "13800000000",
            "demandDate": "2026-11-20",
            "urgency": "normal",
            "remark": "回归测试，请勿在演示中引用",
            "items": [
                {"id": "it-1", "name": "埃塞俄比亚水洗生豆 G1", "spec": "60kg/袋", "quantity": 2, "unit": "袋", "purpose": "测试"}
            ],
        },
    )
    assert res.status_code == 201, res.text
    return int(res.json()["data"]["id"])


def _add_log(doc_id: int) -> None:
    """模拟一条审批流水，制造「有流水的单据」这个原始故障场景"""
    con = sqlite3.connect(DB)
    con.execute(
        "INSERT INTO approval_logs (document_id, approver_id, action, comment, created_at) "
        "VALUES (?, 2, 'reject', '测试留痕', datetime('now'))",
        (doc_id,),
    )
    con.commit()
    con.close()


def _count_logs(doc_id: int) -> int:
    con = sqlite3.connect(DB)
    n = con.execute("SELECT COUNT(*) FROM approval_logs WHERE document_id=?", (doc_id,)).fetchone()[0]
    con.close()
    return n


def _force_cleanup(doc_id: int) -> None:
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM approval_logs WHERE document_id=?", (doc_id,))
    con.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    con.commit()
    con.close()


def test_delete_draft_with_logs_does_not_500(client):
    """核心回归：带审批流水的草稿删除要成功，且留痕一并清理"""
    doc_id = _create(client)
    try:
        _add_log(doc_id)
        assert _count_logs(doc_id) == 1

        res = client(SUBMITTER).delete(f"/api/v1/claims/{doc_id}")
        assert res.status_code == 200, res.text
        assert res.json()["data"]["deleted"] == doc_id

        # 单据与留痕都应消失，不能再残留孤儿记录
        assert client(SUBMITTER).get(f"/api/v1/claims/{doc_id}").status_code == 404
        assert _count_logs(doc_id) == 0
    finally:
        _force_cleanup(doc_id)


def test_delete_submitted_claim_rejected(client):
    """已提交的单据不允许删（要先撤销），避免删掉审批中的单据"""
    doc_id = _create(client)
    try:
        assert client(SUBMITTER).post(f"/api/v1/claims/{doc_id}/submit").status_code == 200
        res = client(SUBMITTER).delete(f"/api/v1/claims/{doc_id}")
        assert res.status_code == 400
        assert "撤销" in res.json()["message"]
    finally:
        _force_cleanup(doc_id)


def test_only_owner_can_delete(client):
    """审批人不能删别人的草稿"""
    doc_id = _create(client)
    try:
        res = client(APPROVER).delete(f"/api/v1/claims/{doc_id}")
        assert res.status_code == 403
    finally:
        _force_cleanup(doc_id)

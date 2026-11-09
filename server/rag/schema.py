"""
知识库元数据规范（RAG 侧的"身份证"）。

每份制度文件头部必须带 YAML front-matter，字段由此处的模型约束。
设计原则：
    1. **版本优先** —— 制度是有生命周期的，检索时必须能识别"现行有效"，
       否则 Agent 会拿废止条文去给审批人做判断，这比不回答更危险。
    2. **权限优先** —— 配方、报价、薪酬类文档不能进通用检索池，用
       confidentiality + acl_roles 做双重门控。
    3. **可溯源** —— chunk 保留 doc_id / version / clause，回答能引用到条款。
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DocStatus(str, Enum):
    """文档生命周期状态"""

    ACTIVE = "active"            # 现行有效
    SUPERSEDED = "superseded"    # 已被新版替代（保留但检索时排除）
    DRAFT = "draft"              # 草案，未生效，不进检索池
    ARCHIVED = "archived"        # 已废止


class Confidentiality(str, Enum):
    """密级 —— 决定是否需要 ACL 门控"""

    PUBLIC = "public"            # 全员可见
    INTERNAL = "internal"        # 内部公开（默认）
    RESTRICTED = "restricted"    # 限部门 / 岗位
    SECRET = "secret"            # 涉密：客户配方、报价、薪酬


class DocType(str, Enum):
    """文档类型 —— 影响切分策略"""

    REGULATION = "regulation"    # 制度 / 规定 / 管理办法（按条款切）
    SOP = "sop"                  # 作业指导书（按步骤切）
    MANUAL = "manual"            # 手册（培训手册、员工手册）
    RECORD = "record"            # 记录 / 表单模板
    CERTIFICATE = "certificate"  # 认证证书、检测报告
    CHANGE_NOTE = "change_note"  # 制度修订书 / 变更通知


class DocMeta(BaseModel):
    """front-matter 的强类型模型"""

    # ---------- 身份 ----------
    doc_id: str = Field(..., description="全局唯一编号，如 MO-SOP-001")
    title: str
    version: str = Field(..., description="语义化版本，如 v1.0 / v2.3")
    doc_type: DocType = DocType.REGULATION
    category: str = Field(..., description="所属目录，如 01_制度流程")

    # ---------- 生效 / 失效 ----------
    effective_date: date = Field(..., description="生效日期，检索时 <= today")
    expire_date: Optional[date] = Field(None, description="失效日期，为空表示长期有效")
    status: DocStatus = DocStatus.ACTIVE
    supersedes: Optional[str] = Field(None, description="替代的旧版 doc_id:version")
    superseded_by: Optional[str] = Field(None, description="被哪个新版替代")

    # ---------- 归属与权限 ----------
    department: str = Field(..., description="归口部门，如 生产部 / 品控部 / 人力行政部")
    owner: Optional[str] = Field(None, description="制度责任人（岗位，不写人名）")
    confidentiality: Confidentiality = Confidentiality.INTERNAL
    acl_roles: list[str] = Field(
        default_factory=list,
        description="可见角色；空列表表示按 confidentiality 默认策略",
    )

    # ---------- 检索增强 ----------
    keywords: list[str] = Field(default_factory=list, description="同义词/别名，补召回")
    related_claims: list[str] = Field(
        default_factory=list,
        description="该文档约束哪些单据类型，如 ['领料单','退料单']",
    )
    related_workshops: list[str] = Field(
        default_factory=list,
        description="适用车间代码，如 ['EX-01','FZ-02']；空=全厂",
    )
    source_file: Optional[str] = Field(None, description="原始附件文件名（PDF/DOCX）")
    note: Optional[str] = None

    @field_validator("doc_id")
    @classmethod
    def _doc_id_format(cls, v: str) -> str:
        if not v or " " in v:
            raise ValueError("doc_id 不能为空且不能含空格")
        return v.upper()

    @field_validator("version")
    @classmethod
    def _version_format(cls, v: str) -> str:
        if not v.startswith("v"):
            raise ValueError("version 必须以 v 开头，如 v1.0")
        return v

    def is_retrievable(self, today: date) -> bool:
        """是否应进入检索池（不考虑 ACL）"""
        if self.status != DocStatus.ACTIVE:
            return False
        if self.effective_date > today:
            return False
        if self.expire_date and self.expire_date < today:
            return False
        return True

    def citation(self, clause: str = "") -> str:
        """生成可溯源的引用串：供 Agent 回答中拼接"""
        base = f"《{self.title}》{self.version}"
        return f"{base} {clause}".strip()

"""
统一彝文数据管理 — Pydantic 数据模型
"""

from pydantic import BaseModel


class CharacterUpdate(BaseModel):
    """更新字符的注音和释义。"""

    pronunciation: str = ""
    meaning: str = ""


class AlignmentGroupCreate(BaseModel):
    """创建/扩展对齐组的请求。"""

    entries: list[str]  # ["D0-00101", "U0-00101", ...]
    note: str = ""


class SuggestBatchInput(BaseModel):
    """批量建议的请求。"""

    entries: list[str]

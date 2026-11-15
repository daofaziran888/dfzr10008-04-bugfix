"""文档自动生成业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import json
from typing import Any

from app.services.apigen import contract_by_code
from app.store import store

MODULE = "docgen"
REQUIRED_FIELDS = ["模板编号", "文档标题", "目标接口"]
ALL_FIELDS = ["模板编号", "文档标题", "目标接口", "生成格式", "示例数据", "错误码表", "更新触发", "模板状态"]
STATUS_ORDER = ["草稿", "已生成", "已发布", "已过期"]
# 动作目标状态与状态序列对齐：生成文档进入已生成、发布文档进入已发布、归档文档进入已过期。
ACTION_RULES = {"生成文档": "已生成", "发布文档": "已发布", "归档文档": "已过期"}
NEGATIVE_ACTIONS: list[str] = []
# 与示例数据口径一致：只有前两个状态算待处理。
PENDING_STATUSES = STATUS_ORDER[:2]


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


class DocgenService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("模板编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def error_codes(self, api_code: str) -> dict[str, Any] | None:
        """文档自动生成读取接口契约里的错误码结构；接口未登记或契约缺失时返回 None。"""
        contract = contract_by_code(api_code)
        if contract is None:
            return None
        return {
            "接口编号": contract.get("接口编号"),
            "版本": contract.get("版本"),
            "响应结构": contract.get("响应结构") or {},
            "错误码结构": contract.get("错误码结构") or {},
        }

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        contract = contract_by_code(str(values.get("目标接口") or ""))
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ALL_FIELDS:
            if values.get(field) is not None:
                entry[field] = values.get(field)
        if contract is not None:
            # 示例数据与错误码表沿契约回填，文档不再读到空响应。
            template = contract.get("响应结构")
            if not str(entry.get("示例数据") or "").strip() and isinstance(template, dict) and template.get("data") is not None:
                entry["示例数据"] = _to_text(template["data"])
            if not str(entry.get("错误码表") or "").strip() and contract.get("错误码结构"):
                entry["错误码表"] = _to_text(contract["错误码结构"])
        entry.setdefault("模板状态", STATUS_ORDER[0])
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"文档模板 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于文档自动生成可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["模板状态"] = target
        entry["pending"] = target in PENDING_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"文档模板已{action}"

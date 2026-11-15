"""产品沙箱测试业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.services.apigen import contract_by_code
from app.store import store

MODULE = "sandbox"
REQUIRED_FIELDS = ["实例编号", "测试产品"]
ALL_FIELDS = ["实例编号", "测试产品", "测试参数", "预期输出", "实际输出", "差异对比", "测试耗时", "实例状态"]
STATUS_ORDER = ["草稿", "测试中", "测试完成", "已关闭"]
# 动作目标状态与状态序列对齐：开始测试进入测试中、关闭实例进入测试完成、归档结果进入已关闭。
ACTION_RULES = {"开始测试": "测试中", "关闭实例": "测试完成", "归档结果": "已关闭"}
NEGATIVE_ACTIONS: list[str] = []
# 与示例数据口径一致：只有前两个状态算待处理。
PENDING_STATUSES = STATUS_ORDER[:2]


def _format_params(params: list[dict[str, Any]]) -> str:
    return "、".join(f"{item['参数名']} {'必填' if item.get('是否必填') else '可选'}" for item in params)


class SandboxService:
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
            rows = [row for row in rows if keyword in str(row.get("实例编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def request_params(self, api_code: str) -> dict[str, Any] | None:
        """沙箱测试读取接口契约里的请求参数；接口未登记或契约缺失时返回 None。"""
        contract = contract_by_code(api_code)
        if contract is None:
            return None
        return {
            "接口编号": contract.get("接口编号"),
            "版本": contract.get("版本"),
            "请求参数": contract.get("请求参数") or [],
            "参数数量": len(contract.get("请求参数") or []),
            "超时秒数": contract.get("超时秒数"),
        }

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        params = values.get("测试参数")
        if not str(params or "").strip():
            # 测试参数未填时，沿接口编号去契约里取请求参数，不再直接报错。
            contract = contract_by_code(str(values.get("测试产品") or ""))
            if contract and contract.get("请求参数"):
                params = contract.get("参数定义") or _format_params(contract["请求参数"])
            else:
                return None, ["测试参数"]
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ALL_FIELDS:
            if values.get(field) is not None:
                entry[field] = values.get(field)
        entry["测试参数"] = params
        entry.setdefault("实例状态", STATUS_ORDER[0])
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"沙箱实例 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于产品沙箱测试可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["实例状态"] = target
        entry["pending"] = target in PENDING_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"沙箱实例已{action}"

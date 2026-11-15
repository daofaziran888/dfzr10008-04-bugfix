"""API接口生成业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import json
import re
from typing import Any

from app.store import store

MODULE = "apigen"
REQUIRED_FIELDS = ["接口编号", "接口名称", "请求方法"]
# 登记时必须完整保留的字段：契约字段（请求方法、请求路径、参数定义、响应模板、超时秒数）
# 与状态字段一样都不能在保存时丢弃，否则下游（沙箱、文档）读到的就是空契约。
ALL_FIELDS = ["接口编号", "接口名称", "请求方法", "请求路径", "参数定义", "响应模板", "超时秒数", "接口状态"]
CONTRACT_FIELDS = ["请求方法", "请求路径", "参数定义", "响应模板", "超时秒数"]
STATUS_ORDER = ["草稿", "测试中", "已发布", "已废弃"]
# 动作目标状态与状态序列对齐：发布进入已发布、废弃进入已废弃、删除直接移除记录。
ACTION_RULES = {"发布接口": "已发布", "废弃接口": "已废弃"}
DELETE_ACTION = "删除接口"
NEGATIVE_ACTIONS: list[str] = []
# 与示例数据口径一致：只有前两个状态算待处理。
PENDING_STATUSES = STATUS_ORDER[:2]
DEFAULT_VERSION = "v1"


def _next_version(version: Any) -> str:
    """版本号顺延：v1 -> v2；无法解析时回到 v2，保证变化后版本一定前进。"""
    match = re.fullmatch(r"v(\d+)", str(version or "").strip())
    if match:
        return f"v{int(match.group(1)) + 1}"
    return "v2"


def parse_params(raw: Any) -> list[dict[str, Any]]:
    """把参数定义解析成请求参数清单，例如「store_id 必填、biz_date 可选」-> 两个参数。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        params: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                name = item.get("参数名", item.get("name"))
                required = item.get("是否必填", item.get("required", False))
                if name is None or str(name).strip() == "":
                    continue
                params.append({"参数名": str(name).strip(), "是否必填": bool(required)})
            elif str(item).strip():
                params.append({"参数名": str(item).strip(), "是否必填": False})
        return params
    params = []
    for segment in re.split(r"[、,，;；\n]+", str(raw)):
        text = segment.strip()
        if not text:
            continue
        required = "必填" in text and "可选" not in text
        name = re.sub(r"[（(][^)）]*[)）]", "", text)
        name = name.replace("必填", "").replace("可选", "").strip(" :：")
        if not name:
            continue
        params.append({"参数名": name, "是否必填": required})
    return params


def _paths_to_tree(paths: list[str]) -> dict[str, Any]:
    """把 data.items、error.code 这类点路径还原成嵌套结构。"""
    tree: dict[str, Any] = {}
    for path in paths:
        node = tree
        parts = [part for part in path.split(".") if part]
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        if parts:
            node.setdefault(parts[-1], {})
    return tree


def parse_response_template(raw: Any) -> tuple[Any, dict[str, Any]]:
    """解析响应模板，返回 (响应结构, 错误码结构)。

    支持三种登记形态：JSON 对象、JSON 字符串、含 data.items / error.code 点路径的文本。
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {}, {}
    data = raw
    if isinstance(raw, str):
        text = raw.strip()
        try:
            data = json.loads(text)
        except ValueError:
            data = _paths_to_tree(re.findall(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+", text))
    if isinstance(data, dict):
        error = data.get("error") or data.get("错误") or {}
        if not isinstance(error, dict):
            error = {"值": error}
        return data, error
    return data, {}


def build_contract(entry: dict[str, Any]) -> dict[str, Any]:
    """从接口配置组装请求响应契约：下游沙箱与文档都按这个结构读取。"""
    template, error = parse_response_template(entry.get("响应模板"))
    return {
        "接口编号": entry.get("接口编号"),
        "接口名称": entry.get("接口名称"),
        "版本": entry.get("版本") or DEFAULT_VERSION,
        "请求方法": entry.get("请求方法"),
        "请求路径": entry.get("请求路径"),
        "参数定义": entry.get("参数定义"),
        "请求参数": parse_params(entry.get("参数定义")),
        "响应模板": entry.get("响应模板"),
        "响应结构": template,
        "错误码结构": error,
        "超时秒数": entry.get("超时秒数"),
        "接口状态": entry.get("接口状态") or entry.get("status"),
    }


def find_by_code(api_code: str) -> dict[str, Any] | None:
    code = str(api_code or "").strip()
    if not code:
        return None
    for row in store.rows(MODULE):
        if str(row.get("接口编号") or "").strip() == code:
            return row
    return None


def contract_by_code(api_code: str) -> dict[str, Any] | None:
    """下游契约读取入口：按接口编号给出当前请求响应契约，读不到时返回 None。"""
    entry = find_by_code(api_code)
    if entry is None:
        return None
    return build_contract(entry)


class ApigenService:
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
            rows = [row for row in rows if keyword in str(row.get("接口编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], bool]:
        """登记接口配置。

        返回 (记录, 缺失字段, 是否更新已有草稿)。同一接口编号重复提交时只更新当前草稿，
        不再追加新行，从源头避免契约清单出现同版本副本。
        """
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, False
        existing = find_by_code(str(values.get("接口编号")))
        if existing is not None:
            contract_changed = any(
                field in values and values.get(field) is not None
                and str(values.get(field)) != str(existing.get(field))
                for field in CONTRACT_FIELDS
            )
            for field in ALL_FIELDS:
                if field in values and values.get(field) is not None:
                    existing[field] = values.get(field)
            if values.get("接口状态") is None:
                # 未显式提交接口状态时与当前工作流状态对齐，避免残留旧占位值。
                existing["接口状态"] = existing.get("status")
            if contract_changed and existing.get("status") == "已发布":
                # 已发布接口的契约字段被改动：版本前进并退回草稿，等待重新发布。
                existing["版本"] = _next_version(existing.get("版本"))
                existing["status"] = STATUS_ORDER[0]
                existing["接口状态"] = STATUS_ORDER[0]
            existing["pending"] = existing.get("status") in PENDING_STATUSES
            return existing, [], True
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ALL_FIELDS:
            if values.get(field) is not None:
                entry[field] = values.get(field)
        entry.setdefault("接口状态", STATUS_ORDER[0])
        entry["版本"] = str(values.get("版本") or DEFAULT_VERSION)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, [], False

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"接口配置 {entry_id} 不存在或已归档"
        if action == DELETE_ACTION:
            store.rows(MODULE).remove(entry)
            store.remove_contracts(str(entry.get("接口编号") or ""))
            return entry, f"接口配置已{action}"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于API接口生成可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["接口状态"] = target
        entry["pending"] = target in PENDING_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if action == "发布接口":
            # 发布即把当前请求响应契约按 (接口编号, 版本) 落入契约清单；
            # 同一版本重复发布只更新同一份契约，发布结果与清单始终对应同一版本。
            store.upsert_contract(build_contract(entry))
        return entry, f"接口配置已{action}"

    def get_contract(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return build_contract(entry)

    def list_contracts(self, api_code: str | None = None) -> list[dict[str, Any]]:
        return store.list_contracts(api_code)

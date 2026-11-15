"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        # 请求响应契约清单：以 (接口编号, 版本) 为键，保证同一版本只保留一份契约。
        # 单独存放而不是塞进 _tables，避免被当成业务模块计入运营概览。
        self._contracts: dict[tuple[str, str], dict[str, Any]] = {}

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def upsert_contract(self, contract: dict[str, Any]) -> dict[str, Any]:
        """写入或更新一条请求响应契约；同接口同版本只保留一份，重复发布不会叠出副本。"""
        key = (str(contract.get("接口编号") or ""), str(contract.get("版本") or ""))
        self._contracts[key] = contract
        return contract

    def list_contracts(self, api_code: str | None = None) -> list[dict[str, Any]]:
        items = list(self._contracts.values())
        if api_code:
            items = [item for item in items if str(item.get("接口编号") or "") == api_code]
        return sorted(items, key=lambda item: (str(item.get("接口编号") or ""), str(item.get("版本") or "")))

    def remove_contracts(self, api_code: str) -> None:
        for key in [key for key in self._contracts if key[0] == api_code]:
            del self._contracts[key]

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()

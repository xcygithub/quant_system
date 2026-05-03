"""
自选股管理模块
支持自选股的添加、删除、查询、分组管理
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
import pandas as pd

# 默认指数（展示在自选股默认组，但业务计算中默认排除）
DEFAULT_BENCHMARK_INDICES: Dict[str, str] = {
    "399001.SZ": "深圳成指",
    "399006.SZ": "创业板指",
    "000001.SH": "上证指数",
    "000688.SH": "科创50",
}


def _normalize_symbol_text(symbol: str) -> str:
    """标准化股票/指数代码格式。"""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return symbol

    # 兼容 "SZ:399001" / "SH:000001" 写法
    if ":" in symbol:
        prefix, code = symbol.split(":", 1)
        code = code.strip()
        if prefix == "SH":
            return f"{code}.SH"
        if prefix == "SZ":
            return f"{code}.SZ"
        if prefix == "BJ":
            return f"{code}.BJ"

    # 如果已包含后缀，直接返回
    if symbol.endswith((".SH", ".SZ", ".HK", ".BJ")):
        return symbol

    # 根据代码前缀添加后缀
    if symbol.startswith(("6", "5", "9")):
        return f"{symbol}.SH"
    if symbol.startswith(("0", "1", "2", "3")):
        return f"{symbol}.SZ"
    if symbol.startswith(("4", "8")):
        return f"{symbol}.BJ"
    return f"{symbol}.SZ"


def is_benchmark_symbol(symbol: str) -> bool:
    """判断是否为系统默认指数。"""
    return _normalize_symbol_text(symbol) in DEFAULT_BENCHMARK_INDICES


def filter_out_benchmark_symbols(symbols: List[str]) -> List[str]:
    """过滤默认指数代码。"""
    return [s for s in symbols if not is_benchmark_symbol(s)]


def filter_out_benchmark_stocks(stocks: List["StockInfo"]) -> List["StockInfo"]:
    """过滤默认指数股票对象。"""
    return [s for s in stocks if not is_benchmark_symbol(s.symbol)]


@dataclass
class StockInfo:
    """股票信息"""
    symbol: str          # 股票代码 (如 000001.SZ)
    name: str            # 股票名称
    group: str = "默认"   # 分组名称
    added_date: str = ""  # 添加日期
    notes: str = ""       # 备注
    tags: List[str] = field(default_factory=list)  # 标签

    def __post_init__(self):
        if not self.added_date:
            self.added_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @property
    def exchange(self) -> str:
        """获取交易所后缀"""
        if self.symbol.endswith('.SH') or self.symbol.endswith('.SZ'):
            return self.symbol[-3:]
        # 根据代码判断交易所
        if self.symbol.startswith(('6', '5', '9')):
            return '.SH'
        elif self.symbol.startswith(('0', '1', '3', '2')):
            return '.SZ'
        return '.SZ'

    def to_dict(self) -> dict:
        return asdict(self)


class WatchlistManager:
    """
    自选股管理器

    功能：
    - 自选股CRUD操作
    - 自选股分组管理
    - 批量导入/导出
    - 与数据库联动
    """

    def __init__(self, storage_path: str = None):
        """
        初始化自选股管理器

        Args:
            storage_path: 存储路径，默认使用项目目录下的 watchlist.json
        """
        if storage_path is None:
            storage_path = Path(__file__).parent.parent / "data" / "watchlist.json"
        else:
            storage_path = Path(storage_path)

        storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path = storage_path
        self._watchlist: Dict[str, StockInfo] = {}
        self._groups: Set[str] = {"默认"}
        self._load()
        self._ensure_default_benchmark_indices()

    def _ensure_default_benchmark_indices(self):
        """确保默认指数存在于“默认”分组。"""
        changed = False
        if "默认" not in self._groups:
            self._groups.add("默认")
            changed = True

        for symbol, name in DEFAULT_BENCHMARK_INDICES.items():
            norm_symbol = self._normalize_symbol(symbol)
            stock = self._watchlist.get(norm_symbol)
            if stock is None:
                self._watchlist[norm_symbol] = StockInfo(
                    symbol=norm_symbol,
                    name=name,
                    group="默认",
                    notes="系统默认指数（默认不参与回测/财务更新/因子计算）",
                )
                changed = True
            else:
                if not stock.name:
                    stock.name = name
                    changed = True
                if stock.group != "默认":
                    stock.group = "默认"
                    changed = True
        if changed:
            self._save()

    def _load(self):
        """从文件加载自选股"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 加载自选股
                stocks = data.get('stocks', [])
                for stock_data in stocks:
                    stock = StockInfo(**stock_data)
                    self._watchlist[stock.symbol] = stock

                # 加载分组
                self._groups = set(data.get('groups', ["默认"]))

            except Exception as e:
                print(f"加载自选股失败: {e}")
                self._watchlist = {}
                self._groups = {"默认"}
        else:
            self._watchlist = {}
            self._groups = {"默认"}

    def _save(self):
        """保存自选股到文件"""
        data = {
            'stocks': [stock.to_dict() for stock in self._watchlist.values()],
            'groups': list(self._groups),
            'updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ==================== 基本操作 ====================

    def add_stock(self, symbol: str, name: str = "", group: str = "默认",
                  notes: str = "", tags: List[str] = None) -> bool:
        """
        添加自选股

        Args:
            symbol: 股票代码
            name: 股票名称
            group: 分组名称
            notes: 备注
            tags: 标签列表

        Returns:
            是否添加成功
        """
        # 标准化代码格式
        symbol = self._normalize_symbol(symbol)

        if symbol in self._watchlist:
            # 已存在，更新信息
            stock = self._watchlist[symbol]
            if name:
                stock.name = name
            if group:
                stock.group = group
            stock.notes = notes
            stock.tags = tags or []
        else:
            # 新增
            stock = StockInfo(
                symbol=symbol,
                name=name or symbol,
                group=group,
                notes=notes,
                tags=tags or []
            )
            self._watchlist[symbol] = stock

        # 确保分组存在
        if group and group not in self._groups:
            self._groups.add(group)

        self._save()
        return True

    def remove_stock(self, symbol: str) -> bool:
        """
        删除自选股

        Args:
            symbol: 股票代码

        Returns:
            是否删除成功
        """
        symbol = self._normalize_symbol(symbol)

        if symbol in self._watchlist:
            del self._watchlist[symbol]
            self._save()
            return True
        return False

    def update_stock(self, symbol: str, **kwargs) -> bool:
        """
        更新自选股信息

        Args:
            symbol: 股票代码
            **kwargs: 可更新字段 (name, group, notes, tags)

        Returns:
            是否更新成功
        """
        symbol = self._normalize_symbol(symbol)

        if symbol not in self._watchlist:
            return False

        stock = self._watchlist[symbol]
        for key, value in kwargs.items():
            if hasattr(stock, key) and value is not None:
                setattr(stock, key, value)

        # 确保分组存在
        if 'group' in kwargs and kwargs['group'] not in self._groups:
            self._groups.add(kwargs['group'])

        self._save()
        return True

    def get_stock(self, symbol: str) -> Optional[StockInfo]:
        """获取单只股票信息"""
        symbol = self._normalize_symbol(symbol)
        return self._watchlist.get(symbol)

    # ==================== 查询操作 ====================

    def get_all_stocks(self) -> List[StockInfo]:
        """获取所有自选股"""
        return list(self._watchlist.values())

    def get_stocks_by_group(self, group: str) -> List[StockInfo]:
        """获取指定分组的自选股"""
        return [s for s in self._watchlist.values() if s.group == group]

    def get_stocks_by_tags(self, tags: List[str]) -> List[StockInfo]:
        """获取包含指定标签的自选股"""
        result = []
        for stock in self._watchlist.values():
            if any(tag in stock.tags for tag in tags):
                result.append(stock)
        return result

    def search_stocks(self, keyword: str) -> List[StockInfo]:
        """
        搜索自选股

        Args:
            keyword: 搜索关键词（匹配代码、名称、标签）

        Returns:
            匹配的自选股列表
        """
        keyword = keyword.lower()
        result = []

        for stock in self._watchlist.values():
            if (keyword in stock.symbol.lower() or
                keyword in stock.name.lower() or
                keyword in stock.notes.lower() or
                any(keyword in tag.lower() for tag in stock.tags)):
                result.append(stock)

        return result

    def get_all_symbols(self) -> List[str]:
        """获取所有自选股代码"""
        return list(self._watchlist.keys())

    def get_groups(self) -> List[str]:
        """获取所有分组"""
        return sorted(list(self._groups))

    # ==================== 分组管理 ====================

    def add_group(self, group: str) -> bool:
        """添加分组"""
        if group and group not in self._groups:
            self._groups.add(group)
            self._save()
            return True
        return False

    def remove_group(self, group: str) -> bool:
        """
        删除分组（会将被删除分组的股票移至'默认'分组）

        Args:
            group: 分组名称

        Returns:
            是否删除成功
        """
        if group == "默认":
            return False  # 不能删除默认分组

        if group in self._groups:
            # 将该分组的股票移至默认分组
            for stock in self._watchlist.values():
                if stock.group == group:
                    stock.group = "默认"

            self._groups.remove(group)
            self._save()
            return True
        return False

    def rename_group(self, old_name: str, new_name: str) -> bool:
        """重命名分组"""
        if old_name not in self._groups or new_name in self._groups:
            return False

        for stock in self._watchlist.values():
            if stock.group == old_name:
                stock.group = new_name

        self._groups.remove(old_name)
        self._groups.add(new_name)
        self._save()
        return True

    def move_stock_to_group(self, symbol: str, new_group: str) -> bool:
        """将股票移动到指定分组"""
        return self.update_stock(symbol, group=new_group)

    # ==================== 批量操作 ====================

    def import_stocks(self, stocks: List[Dict], mode: str = "merge") -> Dict[str, int]:
        """
        批量导入自选股

        Args:
            stocks: 股票列表，每个元素包含 symbol, name, group 等字段
            mode: 导入模式 - "merge"(合并) 或 "replace"(替换)

        Returns:
            导入结果统计 {"success": x, "failed": y}
        """
        if mode == "replace":
            self._watchlist.clear()

        stats = {"success": 0, "failed": 0}

        for stock_data in stocks:
            try:
                symbol = stock_data.get('symbol', '')
                name = stock_data.get('name', '')
                group = stock_data.get('group', '默认')

                if symbol:
                    self.add_stock(symbol, name=name, group=group)
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
            except Exception:
                stats["failed"] += 1

        return stats

    def export_stocks(self, group: str = None) -> List[Dict]:
        """
        导出自选股

        Args:
            group: 如果指定，只导出该分组的股票

        Returns:
            股票列表
        """
        if group:
            stocks = self.get_stocks_by_group(group)
        else:
            stocks = self.get_all_stocks()

        return [stock.to_dict() for stock in stocks]

    # ==================== 工具方法 ====================

    def _normalize_symbol(self, symbol: str) -> str:
        """标准化股票代码格式"""
        return _normalize_symbol_text(symbol)

    def get_stock_count(self) -> int:
        """获取自选股数量"""
        return len(self._watchlist)

    def clear_all(self):
        """清空所有自选股"""
        self._watchlist.clear()
        self._save()

    def to_dataframe(self) -> pd.DataFrame:
        """转换为DataFrame格式"""
        stocks = self.get_all_stocks()
        if not stocks:
            return pd.DataFrame()

        data = [{
            '代码': s.symbol,
            '名称': s.name,
            '分组': s.group,
            '添加日期': s.added_date,
            '备注': s.notes,
            '标签': ','.join(s.tags) if s.tags else ''
        } for s in stocks]

        return pd.DataFrame(data)


# ==================== 便捷函数 ====================

_default_manager: Optional[WatchlistManager] = None


def get_watchlist_manager() -> WatchlistManager:
    """获取全局自选股管理器实例"""
    global _default_manager
    if _default_manager is None:
        _default_manager = WatchlistManager()
    return _default_manager


def add_to_watchlist(symbol: str, name: str = "", group: str = "默认") -> bool:
    """便捷函数：添加自选股"""
    return get_watchlist_manager().add_stock(symbol, name, group)


def remove_from_watchlist(symbol: str) -> bool:
    """便捷函数：删除自选股"""
    return get_watchlist_manager().remove_stock(symbol)


def get_watchlist() -> List[str]:
    """便捷函数：获取所有自选股代码"""
    return get_watchlist_manager().get_all_symbols()


if __name__ == "__main__":
    # 测试代码
    manager = WatchlistManager()

    # 添加测试股票
    manager.add_stock("000001", "平安银行", group="银行")
    manager.add_stock("600000", "浦发银行", group="银行")
    manager.add_stock("600519", "贵州茅台", group="消费")
    manager.add_stock("000858", "五粮液", group="消费")

    print("=== 所有自选股 ===")
    print(manager.to_dataframe())

    print("\n=== 银行组 ===")
    print(manager.get_stocks_by_group("银行"))

    print("\n=== 所有分组 ===")
    print(manager.get_groups())

    print("\n=== 搜索'茅台' ===")
    print(manager.search_stocks("茅台"))

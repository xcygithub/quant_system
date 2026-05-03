"""多因子回测的因子准备服务（最小实现）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd


@dataclass
class FactorQualityReport:
    """因子质量报告。"""

    total_cells: int
    non_null_cells: int
    coverage_ratio: float
    zero_ratio: float
    factor_coverage: Dict[str, float]
    symbol_coverage: Dict[str, float]
    missing_factors: List[str]
    warning_messages: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cells": self.total_cells,
            "non_null_cells": self.non_null_cells,
            "coverage_ratio": self.coverage_ratio,
            "zero_ratio": self.zero_ratio,
            "factor_coverage": self.factor_coverage,
            "symbol_coverage": self.symbol_coverage,
            "missing_factors": self.missing_factors,
            "warning_messages": self.warning_messages,
        }


def prepare_factor_data_for_backtest(
    db_path: str,
    stock_data: Dict[str, pd.DataFrame],
    factor_names: List[str],
    start_date: str,
    end_date: str,
    min_coverage: float = 0.95,
    max_zero_ratio: float = 0.98,
    progress_callback: Optional[Callable[[int, str], bool]] = None,
) -> Tuple[Dict[str, pd.DataFrame], FactorQualityReport, List[str], Optional[str], Optional[str]]:
    """
    预留的因子准备入口。

    当前先返回空面板和质量报告，由上层决定是否继续。
    """
    _ = (db_path, stock_data, factor_names, start_date, end_date, min_coverage, max_zero_ratio, progress_callback)
    report = FactorQualityReport(
        total_cells=0,
        non_null_cells=0,
        coverage_ratio=0.0,
        zero_ratio=0.0,
        factor_coverage={},
        symbol_coverage={},
        missing_factors=[],
        warning_messages=["未提供预计算因子面板。"],
    )
    return {}, report, [], "未提供预计算因子面板。", None

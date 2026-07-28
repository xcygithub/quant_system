"""回测参数服务：统一整理与校验 Tab2 运行参数。"""

from datetime import datetime
from typing import Any, Dict, List, Set


def build_run_config(
    selected_stocks: Set[str],
    strategy_name: str,
    start_date: Any,
    end_date: Any,
    initial_capital: float,
    commission_rate: float,
    max_positions: int,
    rebalance_days: int,
    position_method: str,
    max_single_position: float,
    max_total_position: float,
    stop_loss: float,
    strategy_params: Dict[str, Any],
    session_state: Dict[str, Any],
) -> Dict[str, Any]:
    """构建回测运行配置，供执行层直接使用。"""
    symbols: List[str] = sorted(list(selected_stocks))
    is_single_stock = len(symbols) == 1
    is_multi_factor = strategy_name == "多因子 (Multi-Factor)"

    return {
        "symbols": symbols,
        "is_single_stock": is_single_stock,
        "is_multi_factor": is_multi_factor,
        "start_date_str": start_date.strftime("%Y-%m-%d"),
        "end_date_str": end_date.strftime("%Y-%m-%d"),
        "strategy_name": strategy_name,
        "strategy_params": strategy_params,
        "initial_capital": initial_capital,
        "commission_rate": commission_rate,
        "max_positions": 1 if is_single_stock else max_positions,
        "rebalance_days": rebalance_days,
        "position_method": position_method,
        "max_single_position": max_single_position,
        "max_total_position": max_total_position,
        "stop_loss": stop_loss,
        "mf_factor_weights": session_state.get("mf_factor_weights", {}),
        "mf_use_ic": session_state.get("mf_use_ic", True),
        "mf_ic_update_freq": session_state.get("mf_ic_update_freq", 60),
        "mf_ic_lookback": session_state.get("mf_ic_lookback", 120),
    }


def validate_run_config(run_config: Dict[str, Any]) -> List[str]:
    """校验回测运行参数，返回错误列表。"""
    errors: List[str] = []

    if not run_config.get("symbols"):
        errors.append("请至少选择一只股票进行回测。")

    start_date_str = run_config.get("start_date_str")
    end_date_str = run_config.get("end_date_str")
    try:
        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
            if start_date > end_date:
                errors.append("开始日期不能晚于结束日期。")
    except ValueError:
        errors.append("日期格式无效，请检查开始日期和结束日期。")

    max_single_position = run_config.get("max_single_position", 0.0)
    max_total_position = run_config.get("max_total_position", 0.0)
    if not (0 <= max_single_position <= 1):
        errors.append("单只最大仓位必须在 0 到 1 之间。")
    if not (0 <= max_total_position <= 1):
        errors.append("最大总仓位必须在 0 到 1 之间。")
    if max_single_position > max_total_position:
        errors.append("单只最大仓位不能大于最大总仓位。")

    if run_config.get("max_positions", 0) < 1:
        errors.append("最大持仓数必须大于等于 1。")
    if run_config.get("rebalance_days", 0) < 1:
        errors.append("调仓周期必须大于等于 1。")

    commission_rate = run_config.get("commission_rate", 0.0)
    if commission_rate < 0:
        errors.append("手续费率不能为负数。")

    stop_loss = run_config.get("stop_loss", 0.0)
    if not (0 <= stop_loss <= 1):
        errors.append("止损比例必须在 0 到 1 之间。")

    if run_config.get("is_multi_factor") and not run_config.get("mf_factor_weights"):
        errors.append("多因子策略需要先配置至少一个因子权重。")

    return errors

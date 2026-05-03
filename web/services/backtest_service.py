"""策略回测服务：封装数据加载、信号生成与回测执行。"""

from typing import Any, Callable, Dict, List, Optional, Tuple
import traceback

import pandas as pd

from data.data_provider import CacheOnlyProvider
from data.factor_data import FactorData
from strategy.moving_average import MovingAverageCrossStrategy, MACDStrategy, BollingerBandsStrategy
from strategy.multi_factor import RSIStrategy
from portfolio.multi_stock_backtest import MultiStockBacktest
from portfolio.multi_factor_backtest import run_multi_factor_backtest
from .factor_preparation_service import prepare_factor_data_for_backtest


STRATEGY_CLASS_MAP = {
    "均线交叉 (MA Cross)": MovingAverageCrossStrategy,
    "MACD": MACDStrategy,
    "布林带 (Bollinger Bands)": BollingerBandsStrategy,
    "RSI": RSIStrategy,
}


def _validate_factor_data_contract(
    factor_data: Dict[str, pd.DataFrame],
    factor_weights: Dict[str, float],
    min_factor_coverage: float,
    max_factor_zero_ratio: float,
) -> Dict[str, Any]:
    """校验多因子回测输入契约。"""
    if not factor_data:
        return {"ok": False, "error": "因子数据为空，无法执行多因子回测", "quality_report": {}}

    factor_names = [name for name, weight in factor_weights.items() if weight > 0]
    if not factor_names:
        return {"ok": False, "error": "因子权重配置为空，无法执行多因子回测", "quality_report": {}}

    total_cells = 0
    non_null_cells = 0
    non_null_values: List[float] = []
    factor_total: Dict[str, int] = {name: 0 for name in factor_names}
    factor_non_null: Dict[str, int] = {name: 0 for name in factor_names}
    factor_all_zero: Dict[str, bool] = {name: True for name in factor_names}
    factor_has_column: Dict[str, bool] = {name: False for name in factor_names}

    for _, df in factor_data.items():
        if df is None or df.empty:
            continue
        for factor_name in factor_names:
            if factor_name not in df.columns:
                continue
            factor_has_column[factor_name] = True
            series = pd.to_numeric(df[factor_name], errors="coerce")
            valid = series.dropna()
            count_total = len(series)
            count_non_null = len(valid)
            total_cells += count_total
            non_null_cells += count_non_null
            factor_total[factor_name] += count_total
            factor_non_null[factor_name] += count_non_null
            if count_non_null > 0:
                vals = valid.tolist()
                non_null_values.extend(vals)
                if any(v != 0 for v in vals):
                    factor_all_zero[factor_name] = False

    factor_coverage = {
        name: (factor_non_null[name] / factor_total[name]) if factor_total[name] else 0.0
        for name in factor_names
    }
    coverage_ratio = (non_null_cells / total_cells) if total_cells else 0.0
    zero_ratio = 0.0
    if non_null_values:
        zero_ratio = float(sum(1 for v in non_null_values if v == 0) / len(non_null_values))

    missing_factor_columns = [name for name, exists in factor_has_column.items() if not exists]
    all_zero_factors = [
        name for name in factor_names
        if factor_has_column[name] and factor_non_null[name] > 0 and factor_all_zero[name]
    ]
    sparse_factors = [name for name, cnt in factor_non_null.items() if cnt < 2]

    quality_report = {
        "coverage_ratio": coverage_ratio,
        "zero_ratio": zero_ratio,
        "factor_coverage": factor_coverage,
        "missing_factor_columns": missing_factor_columns,
        "all_zero_factors": all_zero_factors,
        "sparse_factors": sparse_factors,
        "total_cells": total_cells,
        "non_null_cells": non_null_cells,
    }

    if missing_factor_columns:
        return {
            "ok": False,
            "error": f"缺少关键因子列: {', '.join(missing_factor_columns)}",
            "quality_report": quality_report,
        }
    if coverage_ratio < min_factor_coverage:
        return {
            "ok": False,
            "error": f"因子覆盖率不足: {coverage_ratio:.2%} < {min_factor_coverage:.2%}",
            "quality_report": quality_report,
        }
    if zero_ratio > max_factor_zero_ratio:
        return {
            "ok": False,
            "error": f"因子零值占比过高: {zero_ratio:.2%} > {max_factor_zero_ratio:.2%}",
            "quality_report": quality_report,
        }
    if all_zero_factors:
        return {
            "ok": False,
            "error": f"关键因子全为0: {', '.join(all_zero_factors)}",
            "quality_report": quality_report,
        }
    if sparse_factors:
        return {
            "ok": False,
            "error": f"关键因子有效样本不足(<2): {', '.join(sparse_factors)}",
            "quality_report": quality_report,
        }
    return {"ok": True, "quality_report": quality_report}


def _validate_real_stock_data(stock_data: Dict[str, pd.DataFrame]) -> List[str]:
    """校验输入是否为真实行情数据，返回错误列表。"""
    errors: List[str] = []
    required_cols = {"date", "open", "high", "low", "close", "volume"}
    for symbol, df in stock_data.items():
        if df is None or df.empty:
            errors.append(f"{symbol} 无可用行情数据")
            continue

        if "data_source" in df.columns:
            source_series = df["data_source"].astype(str).str.lower()
            if source_series.eq("simulated").any():
                errors.append(f"{symbol} 使用了模拟行情数据，请先更新真实数据后重试")

        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            errors.append(f"{symbol} 缺少必要行情字段: {sorted(missing_cols)}")
    return errors


def load_backtest_stock_data(
    db_path: str,
    symbols: List[str],
    start_date: str,
    end_date: str,
) -> Dict[str, pd.DataFrame]:
    """从本地缓存批量加载回测数据。"""
    provider = CacheOnlyProvider(db_path)
    stock_data: Dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        df = provider.get_stock_data(symbol, start_date, end_date)
        if not df.empty:
            stock_data[symbol] = df
    return stock_data


def _generate_signals(
    stock_data: Dict[str, pd.DataFrame],
    strategy_name: str,
    strategy_params: Dict[str, Any],
) -> Tuple[Dict[str, pd.Series], List[str]]:
    """生成普通策略信号。"""
    strategy_cls = STRATEGY_CLASS_MAP.get(strategy_name)
    if strategy_cls is None:
        raise ValueError(f"不支持的策略: {strategy_name}")

    signals: Dict[str, pd.Series] = {}
    warnings: List[str] = []
    for symbol, df in stock_data.items():
        try:
            factor_data = FactorData(df)
            df_with_factors = factor_data.calculate_all_factors()
            strategy = strategy_cls(strategy_params)
            signal_series = strategy.get_signal_series(df_with_factors)
            if "date" in df.columns:
                signal_series.index = pd.to_datetime(df["date"])
            signals[symbol] = signal_series
        except Exception as exc:
            warnings.append(f"{symbol} 信号计算失败: {exc}")
    return signals, warnings


def run_standard_strategy_backtest(
    stock_data: Dict[str, pd.DataFrame],
    strategy_name: str,
    strategy_params: Dict[str, Any],
    start_date: str,
    end_date: str,
    initial_capital: float,
    commission_rate: float,
    max_positions: int,
    rebalance_days: int,
    position_method: str,
    max_single_position: float,
    max_total_position: float,
    stop_loss: float,
) -> Dict[str, Any]:
    """执行普通策略回测。"""
    signals, warnings = _generate_signals(stock_data, strategy_name, strategy_params)
    if not signals:
        return {"error": "所有股票信号计算失败!", "warnings": warnings}

    engine = MultiStockBacktest(
        initial_capital=initial_capital,
        commission_rate=commission_rate,
        max_positions=max_positions,
        rebalance_days=rebalance_days,
        position_method=position_method,
        max_single_position=max_single_position,
        max_total_position=max_total_position,
        stop_loss=-abs(stop_loss),
    )
    engine.set_data(stock_data, signals)
    results = engine.run(start_date, end_date)

    return {
        "results": results,
        "signals": signals,
        "engine": engine,
        "warnings": warnings,
    }


def run_multi_factor_strategy_backtest(
    symbols: List[str],
    db_path: str,
    stock_data: Dict[str, pd.DataFrame],
    start_date: str,
    end_date: str,
    initial_capital: float,
    max_positions: int,
    rebalance_days: int,
    factor_weights: Dict[str, float],
    use_ic_weighting: bool,
    ic_update_freq: int,
    commission_rate: float,
    max_single_position: float,
    max_total_position: float,
    stop_loss: float,
    factor_data: Optional[Dict[str, pd.DataFrame]] = None,
    progress_callback: Optional[Callable[[int, str], bool]] = None,
    stock_names: Optional[Dict[str, str]] = None,
    min_factor_coverage: float = 0.95,
    max_factor_zero_ratio: float = 0.98,
) -> Dict[str, Any]:
    """执行多因子回测。"""
    if not factor_weights:
        return {"error": "请先在左侧配置多因子权重"}

    validation_errors = _validate_real_stock_data(stock_data)
    if validation_errors:
        return {"error": "输入行情数据校验失败：\n- " + "\n- ".join(validation_errors)}

    if progress_callback and not progress_callback(15, "开始准备因子数据"):
        return {"error": "任务已被中断"}

    warnings: List[str] = []
    quality_report = None
    job_key = None
    if factor_data is None:
        factor_data, quality_report, prep_warnings, prep_error, job_key = prepare_factor_data_for_backtest(
            db_path=db_path,
            stock_data=stock_data,
            factor_names=list(factor_weights.keys()),
            start_date=start_date,
            end_date=end_date,
            min_coverage=min_factor_coverage,
            max_zero_ratio=max_factor_zero_ratio,
            progress_callback=progress_callback,
        )
        warnings.extend(prep_warnings)
        if prep_error:
            return {
                "error": f"因子数据准备失败：{prep_error}",
                "warnings": warnings,
                "quality_report": quality_report.to_dict() if quality_report else {},
                "factor_prepare_job": job_key,
            }

    contract_check = _validate_factor_data_contract(
        factor_data=factor_data,
        factor_weights=factor_weights,
        min_factor_coverage=min_factor_coverage,
        max_factor_zero_ratio=max_factor_zero_ratio,
    )
    if not contract_check["ok"]:
        return {
            "error": contract_check["error"],
            "warnings": warnings,
            "quality_report": contract_check.get("quality_report", {}),
            "factor_prepare_job": job_key,
        }

    if progress_callback and not progress_callback(50, "运行多因子回测"):
        return {"error": "任务已被中断", "warnings": warnings}

    try:
        results = run_multi_factor_backtest(
            symbols=symbols,
            stock_data=stock_data,
            factor_data=factor_data,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            max_positions=max_positions,
            rebalance_days=rebalance_days,
            factor_weights=factor_weights,
            use_ic_weighting=use_ic_weighting,
            ic_update_freq=ic_update_freq,
            commission_rate=commission_rate,
            max_single_position=max_single_position,
            max_total_position=max_total_position,
            stop_loss=stop_loss,
            stock_names=stock_names,
        )
        if quality_report:
            results["factor_quality_report"] = quality_report.to_dict()
            results["factor_prepare_job"] = job_key
        else:
            results["factor_quality_report"] = contract_check.get("quality_report", {})
        if progress_callback:
            progress_callback(100, "回测完成")
        return {"results": results, "warnings": warnings}
    except Exception as exc:
        return {"error": f"多因子回测出错: {exc}", "traceback": traceback.format_exc(), "warnings": warnings}

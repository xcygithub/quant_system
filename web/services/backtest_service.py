"""策略回测服务：封装数据加载、信号生成与回测执行。"""

from typing import Any, Dict, List, Tuple
import traceback

import pandas as pd

from data.data_provider import CacheOnlyProvider
from data.factor_data import FactorData
from strategy.moving_average import MovingAverageCrossStrategy, MACDStrategy, BollingerBandsStrategy
from strategy.multi_factor import RSIStrategy
from portfolio.multi_stock_backtest import MultiStockBacktest
from portfolio.multi_factor_backtest import run_multi_factor_backtest


STRATEGY_CLASS_MAP = {
    "均线交叉 (MA Cross)": MovingAverageCrossStrategy,
    "MACD": MACDStrategy,
    "布林带 (Bollinger Bands)": BollingerBandsStrategy,
    "RSI": RSIStrategy,
}


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
) -> Dict[str, Any]:
    """执行多因子回测。"""
    if not factor_weights:
        return {"error": "请先在左侧配置多因子权重"}

    try:
        results = run_multi_factor_backtest(
            symbols=symbols,
            stock_data=stock_data,
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
        )
        return {"results": results}
    except Exception as exc:
        return {"error": f"多因子回测出错: {exc}", "traceback": traceback.format_exc()}

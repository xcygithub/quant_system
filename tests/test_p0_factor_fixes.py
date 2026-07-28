"""
P0 回归测试：
1. 负向因子方向在百分位打分中生效。
2. 多因子回测在 DataFrame 使用 date 列时仍可计算技术因子。
3. 因子写库使用 UPSERT 后可正确覆盖旧值。
"""
import os
import sqlite3
import tempfile
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.factor_manager import FactorManager
from portfolio.factor_signal_generator import FactorSignalGenerator
from portfolio.multi_factor_backtest import MultiFactorBacktest


def test_negative_factor_direction_applied() -> None:
    """负向因子（如 pe）应当值越小得分越高。"""
    factor_data = pd.DataFrame(
        {
            "pe": [10.0, 20.0, 30.0],
        },
        index=["A", "B", "C"],
    )

    generator = FactorSignalGenerator(
        factor_weights={"pe": 1.0},
        use_ic_weighted=False,
    )

    scores = generator.get_combined_scores(factor_data)
    assert scores["A"] > scores["B"] > scores["C"]


def test_technical_factors_with_date_column() -> None:
    """当行情数据是 date 列而不是索引时，动量/波动率也应可计算。"""
    dates = pd.date_range("2024-01-01", periods=25, freq="D")
    close = np.arange(1, 26, dtype=float)
    stock_df = pd.DataFrame(
        {
            "date": dates,
            "close": close,
        }
    )

    backtest = MultiFactorBacktest(
        factor_weights={"momentum_20": 0.6, "volatility_20": 0.4},
        factor_names=["momentum_20", "volatility_20"],
        use_ic_weighting=False,
    )

    panel = backtest._build_factor_panel(
        date=dates[-1].strftime("%Y-%m-%d"),
        stock_data={"TEST": stock_df},
    )

    assert "TEST" in panel.index
    assert "momentum_20" in panel.columns
    assert "volatility_20" in panel.columns

    expected_momentum = (25.0 - 5.0) / 5.0
    assert abs(panel.loc["TEST", "momentum_20"] - expected_momentum) < 1e-9
    assert not np.isnan(panel.loc["TEST", "volatility_20"])


def test_factor_manager_upsert_replace() -> None:
    """同一主键重复写入时应覆盖旧值，不应残留重复行。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE factor_values (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                factor_name TEXT NOT NULL,
                factor_value REAL,
                update_time TEXT,
                PRIMARY KEY (symbol, trade_date, factor_name)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE factor_cache (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                factor_name TEXT NOT NULL,
                factor_value REAL,
                update_time TEXT,
                PRIMARY KEY (symbol, trade_date, factor_name)
            )
            """
        )
        conn.commit()
        conn.close()

        manager = FactorManager(db_path=db_path)

        values_df = pd.DataFrame(
            [
                {"symbol": "000001.SZ", "trade_date": "2024-01-01", "factor_name": "pe", "factor_value": 10.0},
            ]
        )
        assert manager.save_factor_values(values_df) == 1

        values_df_new = pd.DataFrame(
            [
                {"symbol": "000001.SZ", "trade_date": "2024-01-01", "factor_name": "pe", "factor_value": 12.5},
            ]
        )
        assert manager.save_factor_values(values_df_new) == 1

        result = manager.get_factor_values(symbol="000001.SZ", factor_name="pe")
        assert len(result) == 1
        assert abs(result.iloc[0]["factor_value"] - 12.5) < 1e-9

        cache_df = pd.DataFrame(
            [
                {"symbol": "000001.SZ", "trade_date": "2024-01-01", "factor_name": "roe", "factor_value": 0.15},
            ]
        )
        assert manager.save_factor_cache(cache_df) == 1

        cache_df_new = pd.DataFrame(
            [
                {"symbol": "000001.SZ", "trade_date": "2024-01-01", "factor_name": "roe", "factor_value": 0.2},
            ]
        )
        assert manager.save_factor_cache(cache_df_new) == 1

        conn = sqlite3.connect(db_path)
        cache_rows = pd.read_sql_query("SELECT * FROM factor_cache", conn)
        conn.close()
        assert len(cache_rows) == 1
        assert abs(cache_rows.iloc[0]["factor_value"] - 0.2) < 1e-9
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def main() -> None:
    test_negative_factor_direction_applied()
    test_technical_factors_with_date_column()
    test_factor_manager_upsert_replace()
    print("P0 回归测试通过")


if __name__ == "__main__":
    main()

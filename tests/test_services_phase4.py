"""阶段4测试：服务层回测逻辑与参数校验。"""

from datetime import datetime
from unittest.mock import patch

import pandas as pd

from web.services import backtest_params_service as params_service
from web.services import backtest_service


def test_build_run_config_single_stock_uses_one_position():
    config = params_service.build_run_config(
        selected_stocks={"000001.SZ"},
        strategy_name="RSI",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        initial_capital=1000000,
        commission_rate=0.0003,
        max_positions=5,
        rebalance_days=5,
        position_method="equal",
        max_single_position=0.2,
        max_total_position=0.8,
        stop_loss=0.1,
        strategy_params={"period": 14},
        session_state={},
    )
    assert config["is_single_stock"] is True
    assert config["max_positions"] == 1
    assert config["start_date_str"] == "2024-01-01"
    assert config["end_date_str"] == "2024-01-31"


def test_validate_run_config_reports_multiple_errors():
    invalid = {
        "symbols": [],
        "start_date_str": "2024-03-01",
        "end_date_str": "2024-01-01",
        "max_single_position": 0.9,
        "max_total_position": 0.5,
        "max_positions": 0,
        "rebalance_days": 0,
        "commission_rate": -0.1,
        "stop_loss": 1.5,
        "is_multi_factor": True,
        "mf_factor_weights": {},
    }
    errors = params_service.validate_run_config(invalid)
    assert any("请至少选择一只股票" in e for e in errors)
    assert any("开始日期不能晚于结束日期" in e for e in errors)
    assert any("单只最大仓位不能大于最大总仓位" in e for e in errors)
    assert any("多因子策略需要先配置至少一个因子权重" in e for e in errors)


def test_load_backtest_stock_data_filters_empty_frames():
    non_empty_df = pd.DataFrame({"close": [1.0], "date": ["2024-01-01"]})

    class DummyProvider:
        def __init__(self, _db_path):
            pass

        def get_stock_data(self, symbol, _start, _end):
            return non_empty_df if symbol == "A" else pd.DataFrame()

    with patch.object(backtest_service, "CacheOnlyProvider", DummyProvider):
        data = backtest_service.load_backtest_stock_data(
            db_path="dummy.db",
            symbols=["A", "B"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
    assert list(data.keys()) == ["A"]


def test_run_standard_strategy_backtest_handles_no_signals():
    with patch.object(backtest_service, "_generate_signals", return_value=({}, ["x failed"])):
        result = backtest_service.run_standard_strategy_backtest(
            stock_data={"A": pd.DataFrame()},
            strategy_name="RSI",
            strategy_params={},
            start_date="2024-01-01",
            end_date="2024-01-31",
            initial_capital=1000000,
            commission_rate=0.0003,
            max_positions=3,
            rebalance_days=5,
            position_method="equal",
            max_single_position=0.2,
            max_total_position=0.8,
            stop_loss=0.1,
        )
    assert result["error"] == "所有股票信号计算失败!"
    assert result["warnings"] == ["x failed"]


def test_run_standard_strategy_backtest_passes_negative_stop_loss():
    dummy_signals = {"A": pd.Series([1], index=[pd.Timestamp("2024-01-01")])}

    class DummyEngine:
        last_init_kwargs = {}
        run_called = False

        def __init__(self, **kwargs):
            DummyEngine.last_init_kwargs = kwargs

        def set_data(self, _stock_data, _signals):
            return None

        def run(self, _start, _end):
            DummyEngine.run_called = True
            return {"ok": True}

    with patch.object(backtest_service, "_generate_signals", return_value=(dummy_signals, [])), patch.object(
        backtest_service, "MultiStockBacktest", DummyEngine
    ):
        result = backtest_service.run_standard_strategy_backtest(
            stock_data={"A": pd.DataFrame({"date": ["2024-01-01"], "close": [1.0]})},
            strategy_name="RSI",
            strategy_params={},
            start_date="2024-01-01",
            end_date="2024-01-31",
            initial_capital=1000000,
            commission_rate=0.0003,
            max_positions=3,
            rebalance_days=5,
            position_method="equal",
            max_single_position=0.2,
            max_total_position=0.8,
            stop_loss=0.25,
        )

    assert DummyEngine.run_called is True
    assert DummyEngine.last_init_kwargs["stop_loss"] == -0.25
    assert result["results"] == {"ok": True}

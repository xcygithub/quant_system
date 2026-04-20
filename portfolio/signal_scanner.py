"""
信号扫描模块
对自选股批量应用策略，生成交易信号
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import sys
import os

# Check if we're running as part of a package or standalone
_package_name = 'quant_system'
_in_package = _package_name in sys.modules or any(_package_name in p for p in sys.path)

if _in_package:
    # Running from parent directory - use absolute imports
    from quant_system.strategy.base import Strategy, Signal, SignalType
    from quant_system.strategy.moving_average import MovingAverageCrossStrategy, MACDStrategy, BollingerBandsStrategy
    from quant_system.strategy.multi_factor import RSIStrategy, MultiFactorStrategy
    from quant_system.portfolio.watchlist import WatchlistManager, get_watchlist_manager
else:
    # Running standalone or relative - use relative imports
    from .strategy.base import Strategy, Signal, SignalType
    from .strategy.moving_average import MovingAverageCrossStrategy, MACDStrategy, BollingerBandsStrategy
    from .strategy.multi_factor import RSIStrategy, MultiFactorStrategy
    from .watchlist import WatchlistManager, get_watchlist_manager


class SignalTypeFilter(Enum):
    """信号类型过滤器"""
    ALL = "all"
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class ScanSignal:
    """
    扫描信号结果

    包含单只股票的最新信号信息
    """
    symbol: str           # 股票代码
    name: str             # 股票名称
    date: str             # 信号日期
    signal_type: str      # buy/sell/hold
    strength: float       # 信号强度 0-5星
    price: float          # 当前价格
    change_pct: float     # 涨跌幅
    strategy_name: str     # 策略名称
    indicators: Dict[str, Any] = field(default_factory=dict)  # 策略关键指标
    reason: str = ""      # 信号原因描述

    @property
    def strength_stars(self) -> str:
        """信号强度星级表示"""
        full_stars = int(self.strength)
        half_star = 1 if self.strength - full_stars >= 0.5 else 0
        empty_stars = 5 - full_stars - half_star
        return "★" * full_stars + "☆" * half_star + "○" * empty_stars


@dataclass
class ScanResult:
    """
    扫描结果汇总

    包含所有股票的信号扫描结果
    """
    scan_date: str                    # 扫描日期
    strategy_name: str                # 使用的策略名称
    total_stocks: int                # 扫描股票总数
    buy_signals: int                 # 买入信号数量
    sell_signals: int                # 卖出信号数量
    hold_signals: int                # 持仓信号数量
    signals: List[ScanSignal] = field(default_factory=list)  # 所有信号列表

    def get_filtered_signals(self, signal_type: str) -> List[ScanSignal]:
        """获取指定类型的信号"""
        if signal_type == "all":
            return self.signals
        return [s for s in self.signals if s.signal_type == signal_type]

    def to_dataframe(self) -> pd.DataFrame:
        """转换为DataFrame便于展示"""
        if not self.signals:
            return pd.DataFrame()

        data = []
        for sig in self.signals:
            data.append({
                '股票代码': sig.symbol,
                '股票名称': sig.name,
                '最新价': sig.price,
                '涨跌幅': sig.change_pct,
                '信号类型': sig.signal_type,
                '信号强度': sig.strength,
                '信号星级': sig.strength_stars,
                '信号日期': sig.date,
                '策略': sig.strategy_name,
                '指标详情': str(sig.indicators),
                '信号原因': sig.reason
            })

        df = pd.DataFrame(data)
        # 按信号类型和强度排序
        signal_order = {'buy': 0, 'sell': 1, 'hold': 2}
        df['_sort_key'] = df['信号类型'].map(signal_order).fillna(3)
        df = df.sort_values(['_sort_key', '信号强度'], ascending=[True, False])
        df = df.drop('_sort_key', axis=1)
        return df


class SignalScanner:
    """
    策略信号扫描器

    对自选股列表批量应用指定策略，生成交易信号

    使用方法:
        scanner = SignalScanner()
        result = scanner.scan(
            symbols=['000001.SZ', '600000.SH'],
            strategy_name='MACD',
            start_date='2024-01-01',
            end_date='2024-12-31'
        )
    """

    # 支持的策略映射
    STRATEGY_MAP = {
        '均线交叉 (MA Cross)': MovingAverageCrossStrategy,
        'MACD': MACDStrategy,
        '布林带 (Bollinger Bands)': BollingerBandsStrategy,
        'RSI': RSIStrategy,
        '多因子 (Multi-Factor)': MultiFactorStrategy,
    }

    # 策略默认参数
    DEFAULT_PARAMS = {
        '均线交叉 (MA Cross)': {'fast_period': 20, 'slow_period': 60},
        'MACD': {'fast': 12, 'slow': 26, 'signal': 9},
        '布林带 (Bollinger Bands)': {'period': 20, 'std_dev': 2.0},
        'RSI': {'period': 14, 'oversold': 30, 'overbought': 70},
        '多因子 (Multi-Factor)': {},
    }

    def __init__(self, data_manager=None):
        """
        初始化信号扫描器

        Args:
            data_manager: 数据管理器实例，如果为None则创建默认实例
        """
        self.data_manager = data_manager
        self.watchlist_manager = get_watchlist_manager()

    def scan(
        self,
        symbols: List[str] = None,
        strategy_name: str = 'MACD',
        strategy_params: Dict[str, Any] = None,
        start_date: str = None,
        end_date: str = None,
        data_manager=None
    ) -> ScanResult:
        """
        扫描自选股信号

        Args:
            symbols: 股票代码列表，如果为None则扫描所有自选股
            strategy_name: 策略名称
            strategy_params: 策略参数，如果为None使用默认参数
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'
            data_manager: 数据管理器（可覆盖初始化时的实例）

        Returns:
            ScanResult: 扫描结果
        """
        # 获取数据管理器
        dm = data_manager or self.data_manager
        if dm is None:
            try:
                from .data.data_manager import DataManager
            except ImportError:
                from quant_system.data.data_manager import DataManager
            dm = DataManager()

        # 确定扫描的股票列表
        if symbols is None:
            symbols = self.watchlist_manager.get_all_symbols()

        # 默认日期范围：最近3个月
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if start_date is None:
            start_date = (datetime.now() - pd.Timedelta(days=90)).strftime('%Y-%m-%d')

        # 获取策略参数
        params = strategy_params or self.DEFAULT_PARAMS.get(strategy_name, {})

        # 获取策略类
        strategy_class = self.STRATEGY_MAP.get(strategy_name)
        if strategy_class is None:
            raise ValueError(f"不支持的策略: {strategy_name}")

        # 扫描结果
        signals = []
        buy_count = 0
        sell_count = 0
        hold_count = 0

        for symbol in symbols:
            try:
                # 获取股票名称
                stock_info = self.watchlist_manager.get_stock(symbol)
                name = stock_info.name if stock_info else symbol

                # 获取K线数据
                df = dm.get_daily_kline(symbol, start_date, end_date)

                if df.empty or len(df) < 10:
                    continue

                # 计算策略信号
                signal = self._calculate_signal(
                    df, symbol, name, strategy_class, params
                )

                if signal:
                    signals.append(signal)

                    # 统计信号类型
                    if signal.signal_type == 'buy':
                        buy_count += 1
                    elif signal.signal_type == 'sell':
                        sell_count += 1
                    else:
                        hold_count += 1

            except Exception as e:
                print(f"扫描 {symbol} 时出错: {e}")
                continue

        # 构建扫描结果
        result = ScanResult(
            scan_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            strategy_name=strategy_name,
            total_stocks=len(symbols),
            buy_signals=buy_count,
            sell_signals=sell_count,
            hold_signals=hold_count,
            signals=signals
        )

        return result

    def _calculate_signal(
        self,
        df: pd.DataFrame,
        symbol: str,
        name: str,
        strategy_class: type,
        params: Dict[str, Any]
    ) -> Optional[ScanSignal]:
        """
        计算单只股票的最新信号

        Args:
            df: K线数据
            symbol: 股票代码
            name: 股票名称
            strategy_class: 策略类
            params: 策略参数

        Returns:
            ScanSignal 或 None
        """
        try:
            # 创建策略实例
            strategy = strategy_class(params)

            # 计算信号序列
            signal_series = strategy.get_signal_series(df)

            # 获取最新数据
            latest_close = df['close'].iloc[-1]
            prev_close = df['close'].iloc[-2] if len(df) > 1 else latest_close
            change_pct = ((latest_close - prev_close) / prev_close * 100) if prev_close != 0 else 0

            # 获取最新信号
            latest_signal = signal_series.iloc[-1] if len(signal_series) > 0 else 0

            # 信号类型映射
            if latest_signal == 1:
                signal_type = 'buy'
            elif latest_signal == -1:
                signal_type = 'sell'
            else:
                signal_type = 'hold'

            # 计算信号强度（基于近期信号一致性）
            signal_strength = self._calculate_strength(signal_series)

            # 获取信号日期
            latest_date = df['date'].iloc[-1] if 'date' in df.columns else str(datetime.now().date())

            # 计算策略指标
            indicators = self._get_indicators(df, strategy_class, params)

            # 生成信号原因描述
            reason = self._generate_reason(signal_type, indicators, strategy_class.__name__)

            return ScanSignal(
                symbol=symbol,
                name=name,
                date=str(latest_date)[:10],
                signal_type=signal_type,
                strength=signal_strength,
                price=latest_close,
                change_pct=change_pct,
                strategy_name=strategy_class.__name__,
                indicators=indicators,
                reason=reason
            )

        except Exception as e:
            print(f"计算 {symbol} 信号失败: {e}")
            return None

    def _calculate_strength(self, signal_series: pd.Series) -> float:
        """
        计算信号强度 (0-5)

        基于近期信号的一致性和持续性
        """
        if len(signal_series) < 5:
            return 2.5

        # 最近5天的信号
        recent = signal_series.iloc[-5:]
        latest = recent.iloc[-1]

        if latest == 0:
            return 2.5

        # 计算一致性：最近几天信号相同的比例
        consistency = (recent == latest).sum() / len(recent)

        # 计算信号稳定性：最近几天信号变化次数
        changes = (recent.diff().fillna(0) != 0).sum()

        # 强度 = 一致性 * 稳定性因子
        stability_factor = max(0, 1 - (changes - 1) / len(recent))

        # 信号强度 0-5
        strength = consistency * stability_factor * 5

        return round(strength, 1)

    def _get_indicators(
        self,
        df: pd.DataFrame,
        strategy_class: type,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        获取策略关键指标
        """
        indicators = {}
        close = df['close']

        strategy_name = strategy_class.__name__

        if strategy_name == 'MovingAverageCrossStrategy':
            fast = params.get('fast_period', 20)
            slow = params.get('slow_period', 60)
            if len(df) >= slow:
                indicators['MA_fast'] = close.iloc[-fast:].mean() if len(df) >= fast else None
                indicators['MA_slow'] = close.iloc[-slow:].mean()
                indicators['MA_diff'] = indicators.get('MA_fast', 0) - indicators['MA_slow']

        elif strategy_name == 'MACDStrategy':
            fast = params.get('fast', 12)
            slow = params.get('slow', 26)
            signal_period = params.get('signal', 9)

            if len(df) >= slow:
                ema_fast = close.ewm(span=fast, adjust=False).mean()
                ema_slow = close.ewm(span=slow, adjust=False).mean()
                macd_line = ema_fast - ema_slow
                signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
                histogram = macd_line - signal_line

                indicators['MACD'] = macd_line.iloc[-1]
                indicators['Signal'] = signal_line.iloc[-1]
                indicators['Histogram'] = histogram.iloc[-1]

        elif strategy_name == 'BollingerBandsStrategy':
            period = params.get('period', 20)
            std_dev = params.get('std_dev', 2.0)

            if len(df) >= period:
                middle = close.iloc[-period:].mean()
                std = close.iloc[-period:].std()
                indicators['BB_middle'] = middle
                indicators['BB_upper'] = middle + std_dev * std
                indicators['BB_lower'] = middle - std_dev * std
                indicators['BB_position'] = (close.iloc[-1] - indicators['BB_lower']) / (indicators['BB_upper'] - indicators['BB_lower']) if indicators['BB_upper'] != indicators['BB_lower'] else 0.5

        elif strategy_name == 'RSIStrategy':
            period = params.get('period', 14)
            if len(df) >= period:
                delta = close.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                indicators['RSI'] = rsi.iloc[-1]
                indicators['oversold'] = params.get('oversold', 30)
                indicators['overbought'] = params.get('overbought', 70)

        return indicators

    def _generate_reason(
        self,
        signal_type: str,
        indicators: Dict[str, Any],
        strategy_name: str
    ) -> str:
        """
        生成信号原因描述
        """
        if signal_type == 'buy':
            if strategy_name == 'MovingAverageCrossStrategy':
                ma_fast = indicators.get('MA_fast')
                ma_slow = indicators.get('MA_slow')
                if ma_fast and ma_slow:
                    return f"MA快速线上穿MA慢速线，金叉形成"

            elif strategy_name == 'MACDStrategy':
                histogram = indicators.get('Histogram')
                if histogram is not None:
                    return f"MACD柱状图由负转正，当前值: {histogram:.4f}"

            elif strategy_name == 'BollingerBandsStrategy':
                position = indicators.get('BB_position')
                if position is not None:
                    return f"价格触及布林带下轨，布林带位置: {position:.2%}"

            elif strategy_name == 'RSIStrategy':
                rsi = indicators.get('RSI')
                oversold = indicators.get('oversold', 30)
                if rsi is not None:
                    return f"RSI进入超卖区({rsi:.1f}<{oversold})"

            return "策略发出买入信号"

        elif signal_type == 'sell':
            if strategy_name == 'MovingAverageCrossStrategy':
                ma_fast = indicators.get('MA_fast')
                ma_slow = indicators.get('MA_slow')
                if ma_fast and ma_slow:
                    return f"MA快速线下穿MA慢速线，死叉形成"

            elif strategy_name == 'MACDStrategy':
                histogram = indicators.get('Histogram')
                if histogram is not None:
                    return f"MACD柱状图由正转负，当前值: {histogram:.4f}"

            elif strategy_name == 'BollingerBandsStrategy':
                position = indicators.get('BB_position')
                if position is not None:
                    return f"价格触及布林带上轨，布林带位置: {position:.2%}"

            elif strategy_name == 'RSIStrategy':
                rsi = indicators.get('RSI')
                overbought = indicators.get('overbought', 70)
                if rsi is not None:
                    return f"RSI进入超买区({rsi:.1f}>{overbought})"

            return "策略发出卖出信号"

        else:
            return "策略显示持仓信号"


# 便捷函数
def scan_watchlist(
    strategy_name: str = 'MACD',
    strategy_params: Dict[str, Any] = None,
    start_date: str = None,
    end_date: str = None
) -> ScanResult:
    """
    扫描自选股信号的便捷函数

    Args:
        strategy_name: 策略名称
        strategy_params: 策略参数
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        ScanResult: 扫描结果
    """
    scanner = SignalScanner()
    return scanner.scan(
        strategy_name=strategy_name,
        strategy_params=strategy_params,
        start_date=start_date,
        end_date=end_date
    )


if __name__ == "__main__":
    # 测试代码
    scanner = SignalScanner()

    # 测试扫描
    result = scanner.scan(
        symbols=['000001.SZ', '600000.SH'],
        strategy_name='MACD',
        start_date='2024-01-01',
        end_date='2024-12-31'
    )

    print(f"=== 扫描结果 ===")
    print(f"扫描时间: {result.scan_date}")
    print(f"策略: {result.strategy_name}")
    print(f"买入信号: {result.buy_signals}")
    print(f"卖出信号: {result.sell_signals}")
    print(f"持仓信号: {result.hold_signals}")

    print(f"\n=== 信号详情 ===")
    df = result.to_dataframe()
    print(df)

"""
多股票回测引擎
支持多只股票同时持仓的组合投资回测
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

from .selector import StockSelector, StockScore, create_selector
from .position_sizer import PositionSizer, PositionResult, create_position_sizer


@dataclass
class PortfolioPosition:
    """组合持仓"""
    symbol: str
    quantity: int
    avg_price: float
    current_price: float = 0

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.avg_price) * self.quantity

    @property
    def return_rate(self) -> float:
        if self.avg_price == 0:
            return 0
        return (self.current_price - self.avg_price) / self.avg_price


@dataclass
class TradeRecord:
    """交易记录"""
    date: Any
    symbol: str
    side: str  # BUY / SELL
    price: float
    quantity: int
    amount: float
    commission: float
    reason: str = ""  # 信号原因


@dataclass
class DailySnapshot:
    """每日快照"""
    date: Any
    total_value: float
    cash: float
    position_value: float
    positions: Dict[str, PortfolioPosition]
    daily_return: float


class MultiStockBacktest:
    """
    多股票回测引擎

    特点：
    - 支持多只股票同时持仓
    - 集成选股和仓位分配
    - 支持调仓周期控制
    - 详细交易记录和持仓跟踪
    """

    def __init__(
        self,
        initial_capital: float = 1000000,
        commission_rate: float = 0.0003,
        stamp_tax: float = 0.001,  # 印花税（卖出时收取）
        max_positions: int = 5,
        rebalance_days: int = 5,  # 调仓周期（交易日）
        position_method: str = "equal",
        selector_method: str = "composite",
        max_single_position: float = 0.3,
        max_total_position: float = 0.8
    ):
        """
        初始化多股票回测引擎

        Args:
            initial_capital: 初始资金
            commission_rate: 佣金费率
            stamp_tax: 印花税率（仅卖出时）
            max_positions: 最大持仓股票数
            rebalance_days: 调仓周期（交易日）
            position_method: 仓位分配方法
            selector_method: 选股方法
            max_single_position: 单只股票最大仓位
            max_total_position: 最大总仓位
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.stamp_tax = stamp_tax
        self.max_positions = max_positions
        self.rebalance_days = rebalance_days
        self.position_method = position_method
        self.selector_method = selector_method
        self.max_single_position = max_single_position
        self.max_total_position = max_total_position

        # 状态
        self.cash = initial_capital
        self.positions: Dict[str, PortfolioPosition] = {}
        self.trades: List[TradeRecord] = []
        self.snapshots: List[DailySnapshot] = []

        # 回测数据
        self.stock_data: Dict[str, pd.DataFrame] = {}
        self.signals: Dict[str, pd.Series] = {}

        # 选股器和仓位分配器
        self.selector = create_selector(method=selector_method, top_n=max_positions)
        self.position_sizer = create_position_sizer(
            method=position_method,
            max_total=max_total_position,
            max_single=max_single_position
        )

        # 计数器
        self.trading_days = 0
        self.last_rebalance_day = -1

    def set_data(
        self,
        stock_data: Dict[str, pd.DataFrame],
        signals: Dict[str, pd.Series] = None
    ):
        """
        设置回测数据

        Args:
            stock_data: 股票数据字典 {symbol: dataframe}
                        DataFrame需要包含 date, open, high, low, close, volume 列
            signals: 信号字典 {symbol: signal_series}
                    signal: 1(买入), 0(持有), -1(卖出)
        """
        self.stock_data = stock_data
        self.signals = signals or {}

    def run(self, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """
        运行回测

        Args:
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）

        Returns:
            回测结果
        """
        print(f"\n{'='*60}")
        print(f"开始多股票回测 | 初始资金: {self.initial_capital:,.0f}")
        print(f"{'='*60}")

        # 同步所有股票的日期
        all_dates = self._get_common_dates(start_date, end_date)
        print(f"回测期间: {all_dates[0]} ~ {all_dates[-1]}, 共 {len(all_dates)} 个交易日")

        if len(all_dates) == 0:
            print("错误: 没有可用的回测日期")
            return {}

        # 重置状态
        self.cash = self.initial_capital
        self.positions = {}
        self.trades = []
        self.snapshots = []
        self.trading_days = 0
        self.last_rebalance_day = -1

        # 遍历每个交易日
        for i, date in enumerate(all_dates):
            self.trading_days = i

            # 获取当日数据
            current_prices = self._get_prices_on_date(date)

            # 更新持仓信息
            self._update_positions(current_prices)

            # 检查是否需要调仓
            should_rebalance = (i - self.last_rebalance_day) >= self.rebalance_days

            # 检查卖出信号
            self._check_sell_signals(date, current_prices)

            # 如果需要调仓且有现金，选择新股票买入
            if should_rebalance and self.cash > 0:
                self._rebalance(date, current_prices)

            # 记录每日快照
            self._record_snapshot(date)

        # 回测结束，清空所有持仓（按最后一天收盘价）
        if self.positions:
            last_prices = self._get_prices_on_date(all_dates[-1])
            self._close_all_positions(all_dates[-1], last_prices, "回测结束")

        # 计算结果
        results = self._calculate_results(all_dates)

        self._print_summary(results)

        return results

    def _get_common_dates(
        self,
        start_date: str,
        end_date: str
    ) -> List[Any]:
        """获取所有股票的共同交易日"""
        date_sets = []

        for symbol, df in self.stock_data.items():
            if 'date' in df.columns:
                dates = pd.to_datetime(df['date'])
            else:
                dates = df.index

            if start_date:
                dates = dates[dates >= pd.to_datetime(start_date)]
            if end_date:
                dates = dates[dates <= pd.to_datetime(end_date)]

            date_sets.append(set(dates))

        if not date_sets:
            return []

        # 取交集
        common_dates = set.intersection(*date_sets)
        return sorted(list(common_dates))

    def _get_prices_on_date(self, date) -> Dict[str, float]:
        """获取指定日期各股票的价格"""
        prices = {}

        for symbol, df in self.stock_data.items():
            if 'date' in df.columns:
                row = df[df['date'] == date]
            else:
                row = df[df.index == date]

            if not row.empty:
                prices[symbol] = row['close'].iloc[0]

        return prices

    def _update_positions(self, prices: Dict[str, float]):
        """更新持仓的当前价格"""
        for symbol, pos in self.positions.items():
            if symbol in prices:
                pos.current_price = prices[symbol]

    def _check_sell_signals(self, date, prices: Dict[str, float]):
        """检查卖出信号"""
        positions_to_close = []

        for symbol, pos in self.positions.items():
            if symbol in self.signals:
                signal_series = self.signals[symbol]

                # 找到当日对应的信号
                if 'date' in signal_series.index.names:
                    signal_val = signal_series.loc[date] if date in signal_series.index else 0
                else:
                    idx = signal_series.index.get_loc(date) if date in signal_series.index else -1
                    signal_val = signal_series.iloc[idx] if idx >= 0 else 0

                if signal_val < 0:  # 卖出信号
                    positions_to_close.append(symbol)
            elif symbol not in prices:
                # 没有价格数据，强制平仓
                positions_to_close.append(symbol)

        # 执行平仓
        for symbol in positions_to_close:
            self._close_position(symbol, date, prices.get(symbol, 0), "卖出信号")

    def _rebalance(self, date, prices: Dict[str, float]):
        """调仓：卖出不需要持仓的，买入新候选"""
        # 1. 选出新的候选股票
        new_candidates = self._select_candidates()

        if not new_candidates:
            return

        # 2. 计算目标持仓
        target_symbols = {score.symbol for score in new_candidates}
        current_symbols = set(self.positions.keys())

        # 3. 卖出不在目标中的持仓
        to_sell = current_symbols - target_symbols
        for symbol in to_sell:
            self._close_position(symbol, date, prices.get(symbol, 0), "调仓换股")

        # 4. 分配仓位并买入
        if self.cash > 0:
            # 准备候选股票数据（包含得分和波动率）
            candidate_data = []
            for score in new_candidates:
                volatility = self._estimate_volatility(score.symbol)
                candidate_data.append((score.symbol, score.composite_score, volatility))

            # 分配仓位
            allocations = self.position_sizer.allocate(
                candidate_data,
                self.cash + sum(p.market_value for p in self.positions.values()),
                prices
            )

            # 执行买入
            for alloc in allocations:
                if alloc.shares > 0 and alloc.symbol in prices:
                    self._buy(alloc.symbol, date, prices[alloc.symbol], alloc.shares, "调仓买入")

            self.last_rebalance_day = self.trading_days

    def _select_candidates(self) -> List[StockScore]:
        """选择候选股票"""
        # 准备评分数据
        data_for_scoring = {}
        signals_for_scoring = {}

        for symbol, df in self.stock_data.items():
            if len(df) >= 20:  # 需要足够的数据
                data_for_scoring[symbol] = df
                if symbol in self.signals:
                    signals_for_scoring[symbol] = self.signals[symbol]

        if not data_for_scoring:
            return []

        # 评分
        scores = self.selector.score_stocks(data_for_scoring, signals_for_scoring)

        # 筛选买入候选
        candidates = self.selector.select_buy_candidates(
            scores,
            top_n=self.max_positions,
            min_score=30  # 最低得分门槛
        )

        return candidates

    def _estimate_volatility(self, symbol: str, window: int = 20) -> float:
        """估算股票波动率"""
        if symbol not in self.stock_data:
            return 0.2

        df = self.stock_data[symbol]
        if len(df) < window:
            return 0.2

        returns = df['close'].pct_change().dropna()
        if len(returns) < window:
            return 0.2

        return returns.tail(window).std() * np.sqrt(252)

    def _buy(
        self,
        symbol: str,
        date,
        price: float,
        quantity: int,
        reason: str = ""
    ):
        """买入"""
        if quantity <= 0 or price <= 0:
            return

        amount = price * quantity
        commission = amount * self.commission_rate
        total_cost = amount + commission

        if total_cost > self.cash:
            # 资金不足，调整数量
            quantity = int(self.cash / (price * (1 + self.commission_rate)) / 100) * 100
            if quantity < 100:
                return
            amount = price * quantity
            commission = amount * self.commission_rate
            total_cost = amount + commission

        self.cash -= total_cost

        if symbol in self.positions:
            # 加仓
            pos = self.positions[symbol]
            total_quantity = pos.quantity + quantity
            pos.avg_price = (pos.avg_price * pos.quantity + price * quantity) / total_quantity
            pos.quantity = total_quantity
            pos.current_price = price
        else:
            # 新开仓
            self.positions[symbol] = PortfolioPosition(
                symbol=symbol,
                quantity=quantity,
                avg_price=price,
                current_price=price
            )

        # 记录交易
        self.trades.append(TradeRecord(
            date=date,
            symbol=symbol,
            side="BUY",
            price=price,
            quantity=quantity,
            amount=amount,
            commission=commission,
            reason=reason
        ))

    def _sell(
        self,
        symbol: str,
        date,
        price: float,
        quantity: int,
        reason: str = ""
    ):
        """卖出"""
        if symbol not in self.positions or quantity <= 0:
            return

        pos = self.positions[symbol]
        sell_quantity = min(quantity, pos.quantity)

        amount = price * sell_quantity
        commission = amount * self.commission_rate
        stamp = amount * self.stamp_tax  # 印花税
        net_proceeds = amount - commission - stamp

        self.cash += net_proceeds

        # 更新持仓
        if sell_quantity >= pos.quantity:
            del self.positions[symbol]
        else:
            pos.quantity -= sell_quantity

        # 记录交易
        self.trades.append(TradeRecord(
            date=date,
            symbol=symbol,
            side="SELL",
            price=price,
            quantity=sell_quantity,
            amount=amount,
            commission=commission + stamp,
            reason=reason
        ))

    def _close_position(
        self,
        symbol: str,
        date,
        price: float,
        reason: str = ""
    ):
        """平仓"""
        if symbol in self.positions:
            pos = self.positions[symbol]
            self._sell(symbol, date, price, pos.quantity, reason)

    def _close_all_positions(self, date, prices: Dict[str, float], reason: str):
        """清空所有持仓"""
        for symbol in list(self.positions.keys()):
            price = prices.get(symbol, 0)
            if price > 0:
                self._close_position(symbol, date, prices[symbol], reason)

    def _record_snapshot(self, date):
        """记录每日快照"""
        position_value = sum(p.market_value for p in self.positions.values())
        total_value = self.cash + position_value

        # 计算日收益率
        daily_return = 0
        if self.snapshots:
            prev_total = self.snapshots[-1].total_value
            if prev_total > 0:
                daily_return = (total_value - prev_total) / prev_total

        self.snapshots.append(DailySnapshot(
            date=date,
            total_value=total_value,
            cash=self.cash,
            position_value=position_value,
            positions={s: p for s, p in self.positions.items()},
            daily_return=daily_return
        ))

    def _calculate_results(self, dates: List) -> Dict[str, Any]:
        """计算回测结果"""
        if not self.snapshots:
            return {}

        equity_df = pd.DataFrame([{
            'date': s.date,
            'total_value': s.total_value,
            'cash': s.cash,
            'position_value': s.position_value
        } for s in self.snapshots])

        # 计算收益率序列
        equity_df['return'] = equity_df['total_value'].pct_change()

        # 总收益率
        total_return = (equity_df['total_value'].iloc[-1] - self.initial_capital) / self.initial_capital

        # 年化收益率
        n_days = len(equity_df)
        annual_return = (1 + total_return) ** (252 / n_days) - 1 if n_days > 0 else 0

        # 波动率
        volatility = equity_df['return'].std() * np.sqrt(252)

        # 夏普比率
        risk_free_rate = 0.03
        sharpe_ratio = (annual_return - risk_free_rate) / volatility if volatility > 0 else 0

        # 最大回撤
        equity_df['cummax'] = equity_df['total_value'].cummax()
        equity_df['drawdown'] = (equity_df['total_value'] - equity_df['cummax']) / equity_df['cummax']
        max_drawdown = equity_df['drawdown'].min()

        # 交易统计
        buy_trades = [t for t in self.trades if t.side == "BUY"]
        sell_trades = [t for t in self.trades if t.side == "SELL"]

        # 持仓统计
        final_positions = {s: {
            'quantity': p.quantity,
            'avg_price': p.avg_price,
            'current_price': p.current_price,
            'return': p.return_rate
        } for s, p in self.positions.items()}

        return {
            'initial_capital': self.initial_capital,
            'final_value': equity_df['total_value'].iloc[-1],
            'total_return': total_return,
            'annual_return': annual_return,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'total_trades': len(self.trades),
            'buy_trades': len(buy_trades),
            'sell_trades': len(sell_trades),
            'equity_curve': equity_df,
            'trades': self.trades,
            'final_positions': final_positions,
            'dates': {'start': dates[0], 'end': dates[-1], 'trading_days': n_days}
        }

    def _print_summary(self, results: Dict):
        """打印回测摘要"""
        print(f"\n{'='*60}")
        print("回测结果摘要")
        print(f"{'='*60}")

        print(f"\n收益指标:")
        print(f"  总收益率: {results['total_return']:.2%}")
        print(f"  年化收益率: {results['annual_return']:.2%}")

        print(f"\n风险指标:")
        print(f"  最大回撤: {results['max_drawdown']:.2%}")
        print(f"  年化波动率: {results['volatility']:.2%}")

        print(f"\n风险调整收益:")
        print(f"  夏普比率: {results['sharpe_ratio']:.2f}")

        print(f"\n交易统计:")
        print(f"  总交易次数: {results['total_trades']}")
        print(f"  买入次数: {results['buy_trades']}")
        print(f"  卖出次数: {results['sell_trades']}")

        if results['final_positions']:
            print(f"\n最终持仓:")
            for symbol, info in results['final_positions'].items():
                print(f"  {symbol}: {info['quantity']}股, 成本{info['avg_price']:.2f}, "
                      f"现价{info['current_price']:.2f}, 收益率{info['return']:.2%}")

        print(f"\n{'='*60}")

    def get_equity_curve(self) -> pd.DataFrame:
        """获取权益曲线"""
        if not self.snapshots:
            return pd.DataFrame()

        return pd.DataFrame([{
            'date': s.date,
            'equity': s.total_value,
            'cash': s.cash,
            'position_value': s.position_value,
            'return': s.daily_return
        } for s in self.snapshots])

    def get_trades_df(self) -> pd.DataFrame:
        """获取交易记录DataFrame"""
        if not self.trades:
            return pd.DataFrame()

        return pd.DataFrame([{
            '日期': t.date,
            '股票': t.symbol,
            '方向': t.side,
            '价格': t.price,
            '数量': t.quantity,
            '金额': t.amount,
            '手续费': t.commission,
            '原因': t.reason
        } for t in self.trades])


def run_multi_stock_backtest(
    symbols: List[str],
    stock_data: Dict[str, pd.DataFrame],
    signals: Dict[str, pd.Series] = None,
    initial_capital: float = 1000000,
    start_date: str = None,
    end_date: str = None,
    **kwargs
) -> Dict[str, Any]:
    """
    运行多股票回测的便捷函数

    Args:
        symbols: 股票代码列表
        stock_data: 股票数据字典
        signals: 信号字典
        initial_capital: 初始资金
        start_date: 开始日期
        end_date: 结束日期
        **kwargs: 其他参数传递给MultiStockBacktest

    Returns:
        回测结果
    """
    engine = MultiStockBacktest(
        initial_capital=initial_capital,
        **kwargs
    )

    # 过滤出有数据的股票
    filtered_data = {s: stock_data[s] for s in symbols if s in stock_data}
    filtered_signals = {s: signals[s] for s in symbols if signals and s in signals}

    engine.set_data(filtered_data, filtered_signals)

    return engine.run(start_date, end_date)


if __name__ == "__main__":
    # 简单测试
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta

    # 生成模拟数据
    dates = pd.date_range(end=datetime.now(), periods=120, freq='D')

    stock_data = {
        "000001.SZ": pd.DataFrame({
            'date': dates,
            'open': 10 + np.random.randn(120).cumsum(),
            'high': 10.5 + np.random.randn(120).cumsum(),
            'low': 9.5 + np.random.randn(120).cumsum(),
            'close': 10 + np.random.randn(120).cumsum(),
            'volume': np.random.randint(1000000, 10000000, 120)
        }),
        "600000.SH": pd.DataFrame({
            'date': dates,
            'open': 8 + np.random.randn(120).cumsum(),
            'high': 8.5 + np.random.randn(120).cumsum(),
            'low': 7.5 + np.random.randn(120).cumsum(),
            'close': 8 + np.random.randn(120).cumsum(),
            'volume': np.random.randint(2000000, 15000000, 120)
        }),
        "600519.SH": pd.DataFrame({
            'date': dates,
            'open': 1800 + np.random.randn(120).cumsum() * 10,
            'high': 1820 + np.random.randn(120).cumsum() * 10,
            'low': 1780 + np.random.randn(120).cumsum() * 10,
            'close': 1800 + np.random.randn(120).cumsum() * 10,
            'volume': np.random.randint(500000, 3000000, 120)
        })
    }

    # 生成信号
    signals = {}
    for symbol in stock_data:
        close = stock_data[symbol]['close']
        ma5 = close.rolling(5).mean()
        ma20 = close.rolling(20).mean()
        signals[symbol] = (ma5 > ma20).astype(int) - (ma5 < ma20).astype(int)

    # 运行回测
    results = run_multi_stock_backtest(
        symbols=["000001.SZ", "600000.SH", "600519.SH"],
        stock_data=stock_data,
        signals=signals,
        initial_capital=1000000,
        max_positions=2,
        rebalance_days=10
    )

    print("\n最终资金:", results['final_value'])

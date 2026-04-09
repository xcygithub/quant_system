"""
回测引擎 - 事件驱动和向量化回测实现
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
import json

class OrderType(Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"

class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"

class PositionSide(Enum):
    """持仓方向"""
    LONG = "long"
    SHORT = "short"

@dataclass
class Order:
    """订单类"""
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    stop_price: Optional[float] = None
    order_id: str = field(default_factory=lambda: f"order_{datetime.now().timestamp()}")
    timestamp: datetime = field(default_factory=datetime.now)
    status: str = "pending"  # pending, filled, cancelled, rejected
    filled_price: Optional[float] = None
    filled_quantity: float = 0
    commission: float = 0

@dataclass
class Position:
    """持仓类"""
    symbol: str
    side: PositionSide
    quantity: float
    avg_price: float
    market_price: float = 0
    unrealized_pnl: float = 0
    realized_pnl: float = 0
    
    @property
    def market_value(self) -> float:
        """持仓市值"""
        return self.quantity * self.market_price
    
    @property
    def total_pnl(self) -> float:
        """总盈亏"""
        return self.unrealized_pnl + self.realized_pnl

@dataclass
class Trade:
    """成交记录"""
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    timestamp: datetime
    commission: float
    pnl: float = 0


class BacktestEngine:
    """
    事件驱动回测引擎
    
    特点：
    - 逐日/逐分钟模拟
    - 支持限价单、止损单
    - 真实滑点和手续费模拟
    - 详细的成交记录
    """
    
    def __init__(
        self,
        initial_capital: float = 1000000.0,
        commission_rate: float = 0.0003,
        slippage: float = 0.001,
        max_position_pct: float = 0.95
    ):
        """
        初始化回测引擎
        
        Args:
            initial_capital: 初始资金
            commission_rate: 手续费率
            slippage: 滑点比例
            max_position_pct: 最大持仓比例
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage
        self.max_position_pct = max_position_pct
        
        # 账户状态
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.orders: List[Order] = []
        self.trades: List[Trade] = []
        
        # 历史记录
        self.equity_curve: List[Dict] = []
        self.daily_returns: List[float] = []
        
        # 当前日期
        self.current_date: Optional[datetime] = None
        
        # 策略
        self.strategy = None
        
    def set_strategy(self, strategy):
        """设置策略"""
        self.strategy = strategy
        self.strategy.set_engine(self)
    
    def run(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        运行回测
        
        Args:
            data: 包含OHLCV数据的DataFrame，需要有date列
            
        Returns:
            回测结果字典
        """
        print("开始回测...")
        
        # 确保数据按日期排序
        data = data.sort_values('date').reset_index(drop=True)
        
        # 遍历每个交易日
        for idx, row in data.iterrows():
            self.current_date = row['date'] if isinstance(row['date'], datetime) else pd.to_datetime(row['date'])
            
            # 更新持仓市值
            self._update_positions(row)
            
            # 处理待成交订单
            self._process_orders(row)
            
            # 调用策略生成信号
            if self.strategy:
                self.strategy.on_bar(row)
            
            # 记录权益
            self._record_equity()
        
        # 计算回测结果
        results = self._calculate_results()
        
        print("回测完成!")
        return results
    
    def buy(self, symbol: str, quantity: float, price: Optional[float] = None,
            order_type: OrderType = OrderType.MARKET, stop_price: Optional[float] = None) -> str:
        """
        买入
        
        Args:
            symbol: 股票代码
            quantity: 数量
            price: 价格（限价单需要）
            order_type: 订单类型
            stop_price: 止损价
            
        Returns:
            订单ID
        """
        order = Order(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=order_type,
            price=price,
            stop_price=stop_price
        )
        self.orders.append(order)
        return order.order_id
    
    def sell(self, symbol: str, quantity: float, price: Optional[float] = None,
             order_type: OrderType = OrderType.MARKET, stop_price: Optional[float] = None) -> str:
        """卖出"""
        order = Order(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            order_type=order_type,
            price=price,
            stop_price=stop_price
        )
        self.orders.append(order)
        return order.order_id
    
    def close_position(self, symbol: str):
        """平仓"""
        if symbol in self.positions:
            position = self.positions[symbol]
            if position.side == PositionSide.LONG:
                self.sell(symbol, position.quantity)
            else:
                self.buy(symbol, position.quantity)
    
    def close_all_positions(self):
        """平掉所有持仓"""
        for symbol in list(self.positions.keys()):
            self.close_position(symbol)
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓信息"""
        return self.positions.get(symbol)
    
    def get_total_equity(self) -> float:
        """获取总权益"""
        position_value = sum(p.market_value for p in self.positions.values())
        return self.cash + position_value
    
    def _update_positions(self, bar: pd.Series):
        """更新持仓市值"""
        symbol = bar.get('symbol', 'unknown')
        close_price = bar['close']
        
        if symbol in self.positions:
            position = self.positions[symbol]
            position.market_price = close_price
            
            # 计算未实现盈亏
            if position.side == PositionSide.LONG:
                position.unrealized_pnl = (close_price - position.avg_price) * position.quantity
            else:
                position.unrealized_pnl = (position.avg_price - close_price) * position.quantity
    
    def _process_orders(self, bar: pd.Series):
        """处理订单"""
        symbol = bar.get('symbol', 'unknown')
        high, low, close = bar['high'], bar['low'], bar['close']
        
        for order in self.orders:
            if order.status != "pending" or order.symbol != symbol:
                continue
            
            filled = False
            filled_price = close
            
            if order.order_type == OrderType.MARKET:
                # 市价单以收盘价成交，加上滑点
                filled = True
                if order.side == OrderSide.BUY:
                    filled_price = close * (1 + self.slippage)
                else:
                    filled_price = close * (1 - self.slippage)
                    
            elif order.order_type == OrderType.LIMIT:
                # 限价单
                if order.side == OrderSide.BUY and low <= order.price:
                    filled = True
                    filled_price = min(order.price, close)
                elif order.side == OrderSide.SELL and high >= order.price:
                    filled = True
                    filled_price = max(order.price, close)
                    
            elif order.order_type == OrderType.STOP:
                # 止损单
                if order.side == OrderSide.BUY and high >= order.stop_price:
                    filled = True
                    filled_price = max(order.stop_price, close)
                elif order.side == OrderSide.SELL and low <= order.stop_price:
                    filled = True
                    filled_price = min(order.stop_price, close)
            
            if filled:
                self._fill_order(order, filled_price)
    
    def _fill_order(self, order: Order, price: float):
        """成交订单"""
        order.status = "filled"
        order.filled_price = price
        order.filled_quantity = order.quantity
        
        # 计算手续费
        order.commission = price * order.quantity * self.commission_rate
        
        # 计算成交金额
        trade_value = price * order.quantity
        total_cost = trade_value + order.commission
        
        # 更新资金
        if order.side == OrderSide.BUY:
            self.cash -= total_cost
        else:
            self.cash += trade_value - order.commission
        
        # 更新持仓
        symbol = order.symbol
        if symbol not in self.positions:
            # 新开仓
            self.positions[symbol] = Position(
                symbol=symbol,
                side=PositionSide.LONG if order.side == OrderSide.BUY else PositionSide.SHORT,
                quantity=order.quantity,
                avg_price=price,
                market_price=price
            )
        else:
            position = self.positions[symbol]
            if order.side == OrderSide.BUY:
                # 加仓
                total_quantity = position.quantity + order.quantity
                position.avg_price = (position.avg_price * position.quantity + price * order.quantity) / total_quantity
                position.quantity = total_quantity
            else:
                # 减仓或平仓
                if order.quantity >= position.quantity:
                    # 完全平仓
                    realized_pnl = (price - position.avg_price) * position.quantity - order.commission
                    position.realized_pnl += realized_pnl
                    del self.positions[symbol]
                else:
                    # 部分平仓
                    realized_pnl = (price - position.avg_price) * order.quantity - order.commission
                    position.realized_pnl += realized_pnl
                    position.quantity -= order.quantity
        
        # 记录成交
        trade = Trade(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=price,
            timestamp=self.current_date,
            commission=order.commission
        )
        self.trades.append(trade)
    
    def _record_equity(self):
        """记录权益曲线"""
        equity = self.get_total_equity()
        self.equity_curve.append({
            'date': self.current_date,
            'equity': equity,
            'cash': self.cash,
            'position_value': equity - self.cash
        })
    
    def _calculate_results(self) -> Dict[str, Any]:
        """计算回测结果"""
        equity_df = pd.DataFrame(self.equity_curve)
        
        if len(equity_df) < 2:
            return {'error': '数据不足'}
        
        # 计算收益率
        equity_df['return'] = equity_df['equity'].pct_change()
        
        # 总收益率
        total_return = (equity_df['equity'].iloc[-1] - self.initial_capital) / self.initial_capital
        
        # 年化收益率
        n_days = len(equity_df)
        annual_return = (1 + total_return) ** (252 / n_days) - 1
        
        # 波动率
        volatility = equity_df['return'].std() * np.sqrt(252)
        
        # 夏普比率 (假设无风险利率3%)
        risk_free_rate = 0.03
        sharpe_ratio = (annual_return - risk_free_rate) / volatility if volatility > 0 else 0
        
        # 最大回撤
        equity_df['cummax'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax']
        max_drawdown = equity_df['drawdown'].min()
        
        # 胜率
        winning_trades = [t for t in self.trades if t.pnl > 0]
        win_rate = len(winning_trades) / len(self.trades) if self.trades else 0
        
        # 盈亏比
        avg_profit = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        losing_trades = [t for t in self.trades if t.pnl <= 0]
        avg_loss = abs(np.mean([t.pnl for t in losing_trades])) if losing_trades else 1
        profit_factor = avg_profit / avg_loss if avg_loss > 0 else 0
        
        return {
            'initial_capital': self.initial_capital,
            'final_equity': equity_df['equity'].iloc[-1],
            'total_return': total_return,
            'annual_return': annual_return,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'total_trades': len(self.trades),
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'equity_curve': equity_df,
            'trades': self.trades,
            'positions': self.positions
        }


class VectorizedBacktest:
    """
    向量化回测引擎

    特点：
    - 使用矩阵运算，速度极快
    - 适合策略研究和参数优化
    - 不支持复杂的订单类型
    """

    def __init__(
        self,
        initial_capital: float = 1000000.0,
        commission_rate: float = 0.0003,
        min_holding_days: int = 0  # 最短持股天数
    ):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.min_holding_days = min_holding_days
    
    def run(
        self,
        price_data: pd.DataFrame,
        signal_series: pd.Series,
        position_size: float = 1.0
    ) -> Dict[str, Any]:
        """
        运行向量化回测
        
        Args:
            price_data: 价格数据DataFrame，需要包含close列
            signal_series: 信号序列 (-1: 卖出, 0: 持仓, 1: 买入)
            position_size: 仓位比例
            
        Returns:
            回测结果
        """
        df = price_data.copy()
        df['signal'] = signal_series
        df['position'] = df['signal'].shift(1).fillna(0)  # 次日执行
        
        # 计算收益率
        df['market_return'] = df['close'].pct_change().fillna(0)  # 第一天收益为0
        # 修正：实际仓位比例为10%（每次交易使用初始资金的10%）
        actual_position_ratio = 0.1
        df['strategy_return'] = df['position'] * df['market_return'] * actual_position_ratio
        
        # 计算换手率和手续费
        df['turnover'] = abs(df['position'].diff().fillna(0)) * actual_position_ratio
        df['commission'] = df['turnover'] * self.commission_rate
        df['strategy_return'] = (df['position'] * df['market_return'] * actual_position_ratio) - df['commission']
        df['strategy_return'] = df['strategy_return'].fillna(0)  # 填充可能的NaN
        
        # 计算累计收益
        df['cumulative_market'] = (1 + df['market_return']).cumprod()
        df['cumulative_strategy'] = (1 + df['strategy_return']).cumprod()
        
        # 计算权益
        df['market_equity'] = self.initial_capital * df['cumulative_market']
        df['strategy_equity'] = self.initial_capital * df['cumulative_strategy']
        
        # 生成交易记录
        trades = self._generate_trades(df)
        
        # 计算基于实际交易的总收益率
        if len(trades) > 0:
            total_profit = sum([t['profit'] for t in trades])
            total_return = total_profit / self.initial_capital
        else:
            total_return = df['cumulative_strategy'].iloc[-1] - 1
        
        n_days = len(df)
        annual_return = (1 + total_return) ** (252 / n_days) - 1
        volatility = df['strategy_return'].std() * np.sqrt(252)
        sharpe_ratio = annual_return / volatility if volatility > 0 else 0
        
        # 最大回撤
        df['cummax'] = df['strategy_equity'].cummax()
        df['drawdown'] = (df['strategy_equity'] - df['cummax']) / df['cummax']
        max_drawdown = df['drawdown'].min()
        
        # 胜率
        if len(trades) > 0:
            winning_trades = [t for t in trades if t['net_return_rate'] > 0]
            win_rate = len(winning_trades) / len(trades)
        else:
            win_rate = 0
        
        return {
            'total_return': total_return,
            'annual_return': annual_return,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'equity_curve': df[['market_equity', 'strategy_equity']],
            'returns': df['strategy_return'],
            'positions': df['position'],
            'turnover': df['turnover'].sum(),
            'trades': trades
        }
    
    def _generate_trades(self, df: pd.DataFrame) -> List[Dict]:
        """
        生成交易记录
        
        Args:
            df: 包含信号和价格数据的DataFrame
            
        Returns:
            交易记录列表
        """
        trades = []
        position = 0  # 当前持仓
        entry_price = 0  # 入场价格
        entry_date = None  # 入场日期
        entry_quantity = 0  # 买入数量
        trade_id = 0
        
        for idx, row in df.iterrows():
            signal = row['position']
            date = row.get('date', idx)
            price = row['close']
            volume = row.get('volume', 0)  # 获取成交量
            
            # 检测信号变化
            if idx > 0:
                prev_signal = df.iloc[idx - 1]['position']
                
                # 买入信号: 从0或-1变为1
                if prev_signal <= 0 and signal == 1:
                    trade_id += 1
                    position = 1
                    entry_price = price
                    entry_date = date
                    # 假设每次买入固定金额（初始资金的10%）
                    # A股交易规则：买入数量必须是100的整数倍（1手=100股）
                    raw_quantity = (self.initial_capital * 0.1) / price
                    entry_quantity = int(raw_quantity / 100) * 100  # 向下取整到100的倍数
                    # 确保至少买入100股
                    if entry_quantity < 100:
                        entry_quantity = 100
                    
                # 卖出信号: 从1变为0或-1
                elif prev_signal == 1 and signal <= 0:
                    # 计算持有天数
                    entry_dt = pd.to_datetime(entry_date)
                    exit_dt = pd.to_datetime(date)
                    holding_days = (exit_dt - entry_dt).days

                    # 检查最短持股天数限制
                    if self.min_holding_days > 0 and holding_days < self.min_holding_days:
                        # 持有天数不足，忽略卖出信号，继续持仓
                        continue

                    # 计算收益率
                    return_rate = (price - entry_price) / entry_price

                    # 计算手续费 (双边)
                    commission = entry_price * entry_quantity * self.commission_rate + price * entry_quantity * self.commission_rate

                    # 计算净收益率 (扣除手续费)
                    net_return = return_rate - (commission / (entry_price * entry_quantity))

                    # 计算买入金额和卖出金额
                    entry_value = entry_price * entry_quantity
                    exit_value = price * entry_quantity

                    # 计算收益金额
                    profit = exit_value - entry_value - commission

                    trade = {
                        'trade_id': trade_id,
                        'entry_date': entry_date,
                        'entry_price': entry_price,
                        'entry_quantity': entry_quantity,
                        'entry_value': entry_value,
                        'exit_date': date,
                        'exit_price': price,
                        'exit_quantity': entry_quantity,
                        'exit_value': exit_value,
                        'return_rate': return_rate,
                        'net_return_rate': net_return,
                        'profit': profit,
                        'holding_days': holding_days,
                        'commission': commission,
                        'status': 'closed'  # 已平仓
                    }
                    trades.append(trade)
                    position = 0
                    entry_price = 0
                    entry_date = None
                    entry_quantity = 0
        
        # 检查回测结束时是否仍有持仓,添加未平仓记录
        if position == 1 and entry_price > 0 and entry_quantity > 0:
            last_row = df.iloc[-1]
            last_date = last_row.get('date', df.index[-1])
            last_price = last_row['close']
            
            # 计算浮动收益率
            return_rate = (last_price - entry_price) / entry_price
            
            # 计算持有天数
            entry_dt = pd.to_datetime(entry_date)
            exit_dt = pd.to_datetime(last_date)
            holding_days = (exit_dt - entry_dt).days
            
            # 计算买入金额和当前市值
            entry_value = entry_price * entry_quantity
            current_value = last_price * entry_quantity
            
            # 浮动盈亏 (不含卖出手续费,因为还没卖)
            unrealized_profit = current_value - entry_value
            
            trade = {
                'trade_id': trade_id,
                'entry_date': entry_date,
                'entry_price': entry_price,
                'entry_quantity': entry_quantity,
                'entry_value': entry_value,
                'exit_date': '持有中',
                'exit_price': last_price,
                'exit_quantity': entry_quantity,
                'exit_value': current_value,
                'return_rate': return_rate,
                'net_return_rate': return_rate,  # 未平仓,没有卖出手续费
                'profit': unrealized_profit,  # 浮动盈亏
                'holding_days': holding_days,
                'commission': entry_price * entry_quantity * self.commission_rate,  # 只有买入手续费
                'status': 'open'  # 未平仓
            }
            trades.append(trade)
        
        return trades


if __name__ == "__main__":
    # 测试回测引擎
    from quant_system.data.data_manager import DataManager
    
    dm = DataManager()
    df = dm.get_daily_kline("000001", "2024-01-01", "2024-12-31")
    
    if not df.empty:
        # 简单测试策略：均线交叉
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_60'] = df['close'].rolling(60).mean()
        df['signal'] = np.where(df['sma_20'] > df['sma_60'], 1, -1)
        
        # 向量化回测
        engine = VectorizedBacktest()
        results = engine.run(df, df['signal'])
        
        print("\n回测结果:")
        print(f"总收益率: {results['total_return']:.2%}")
        print(f"年化收益率: {results['annual_return']:.2%}")
        print(f"夏普比率: {results['sharpe_ratio']:.2f}")
        print(f"最大回撤: {results['max_drawdown']:.2%}")

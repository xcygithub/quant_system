"""
多因子回测引擎
集成因子信号、IC动态权重、暴露度分析的完整回测引擎
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import json
from dataclasses import dataclass, field
import logging

from .multi_stock_backtest import (
    MultiStockBacktest, PortfolioPosition, TradeRecord, TradeDetail,
    run_multi_stock_backtest
)
from .factor_signal_generator import FactorSignalGenerator, create_signal_generator
from .factor_exposure_tracker import FactorExposureTracker
from .factor_ic_configurator import FactorICConfigurator
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

def _assert_real_market_data(stock_data: Dict[str, pd.DataFrame]) -> None:
    """
    校验回测输入必须为真实行情数据，不允许模拟数据。

    Rules:
    - 禁止 data_source=simulated 的数据进入回测；
    - 至少包含基础行情字段（date/open/high/low/close/volume）。
    """
    required_cols = {"date", "open", "high", "low", "close", "volume"}
    for symbol, df in stock_data.items():
        if df is None or df.empty:
            continue

        # 显式拦截模拟数据
        if "data_source" in df.columns:
            source_series = df["data_source"].astype(str).str.lower()
            if source_series.eq("simulated").any():
                raise ValueError(f"{symbol} 包含模拟数据（data_source=simulated），请先更新真实行情数据")

        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            raise ValueError(
                f"{symbol} 缺少必要行情字段: {sorted(missing_cols)}，无法作为真实行情回测输入"
            )


@dataclass
class RebalanceSnapshot:
    """调仓日快照：记录每次调仓时的完整因子面板"""
    date: str
    # 全部候选股票的综合得分 {symbol: score}
    all_scores: Dict[str, float] = field(default_factory=dict)
    # 全部候选股票的因子原始值 {symbol: {factor: value}}
    all_factor_values: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # 全部候选股票的因子百分位 {symbol: {factor: percentile}}
    all_factor_percentiles: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # 最终买入的股票列表
    selected_symbols: List[str] = field(default_factory=list)
    # 最终卖出的股票列表
    sold_symbols: List[str] = field(default_factory=list)


class MultiFactorBacktest(MultiStockBacktest):
    """
    多因子回测引擎

    继承 MultiStockBacktest，扩展以下功能：
    - 在回测期间根据因子 IC 动态调整权重
    - 跟踪组合因子暴露度
    - 生成因子归因分析报告
    - 支持分层回测对比
    """

    def __init__(
        self,
        initial_capital: float = 1000000,
        commission_rate: float = 0.0003,
        stamp_tax: float = 0.001,
        max_positions: int = 5,
        rebalance_days: int = 5,
        position_method: str = "equal",
        selector_method: str = "composite",
        max_single_position: float = 0.2,
        max_total_position: float = 0.8,
        stop_loss: float = 0.0,
        # 因子配置
        factor_weights: Dict[str, float] = None,
        factor_names: List[str] = None,
        use_ic_weighting: bool = True,
        ic_update_freq: int = 60,
        db_path: str = None,
        progress_callback: callable = None
    ):
        """
        初始化多因子回测引擎

        Args:
            继承 MultiStockBacktest 的参数...
            factor_weights: 基础因子权重
            factor_names: 要使用的因子列表
            use_ic_weighting: 是否根据 IC 动态调整权重
            ic_update_freq: IC 更新频率（天）
            db_path: 数据库路径
        """
        super().__init__(
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            stamp_tax=stamp_tax,
            max_positions=max_positions,
            rebalance_days=rebalance_days,
            position_method=position_method,
            selector_method=selector_method,
            max_single_position=max_single_position,
            max_total_position=max_total_position,
            stop_loss=stop_loss,
            progress_callback=progress_callback
        )

        # 因子配置
        self.factor_weights = factor_weights or {}
        self.factor_names = factor_names or list(factor_weights.keys()) if factor_weights else []
        self.use_ic_weighting = use_ic_weighting
        self.ic_update_freq = ic_update_freq
        self.db_path = db_path or str(DATABASE_PATH)

        # IC 配置器
        self.ic_configurator = FactorICConfigurator(db_path=self.db_path)

        # 因子信号生成器
        self.signal_generator = FactorSignalGenerator(
            factor_weights=self.factor_weights,
            use_ic_weighted=False  # 初始不使用 IC 加权
        )

        # 暴露度跟踪器
        self.exposure_tracker = FactorExposureTracker(
            factor_names=self.factor_names,
            db_path=self.db_path
        )

        # 当前 IC 权重
        self.ic_weights = None

        # IC 更新计数器
        self.ic_update_counter = 0

        # 因子数据缓存
        self.factor_data_cache: Dict[str, pd.DataFrame] = {}

        # 因子报告
        self.factor_report: Dict[str, Any] = {}

        # 调仓日快照列表
        self.rebalance_snapshots: List[RebalanceSnapshot] = []

        # 每日因子面板缓存 {date_str: DataFrame}
        self._factor_panel_cache: Dict[str, pd.DataFrame] = {}

        # 每日因子百分位缓存 {date_str: {symbol: {factor: percentile}}}
        self._factor_percentiles_cache: Dict[str, Dict[str, Dict[str, float]]] = {}

        # 每日综合得分缓存 {date_str: {symbol: score}}
        self._composite_scores_cache: Dict[str, Dict[str, float]] = {}

        # 股票名称映射 {symbol: name}
        self.stock_names: Dict[str, str] = {}
        # 首笔买入诊断：用于解释“回测开始后为何长期空仓”
        self.first_buy_date: Optional[str] = None
        self.pre_first_buy_diagnostics: List[Dict[str, Any]] = []

    def set_data(
        self,
        stock_data: Dict[str, pd.DataFrame],
        signals: Dict[str, pd.Series] = None,
        factor_data: Dict[str, pd.DataFrame] = None
    ):
        """
        设置回测数据并生成因子信号

        Args:
            stock_data: 股票数据
            signals: 外部信号（可选，会被忽略）
            factor_data: 因子数据
        """
        # 调用父类方法设置股票数据
        super().set_data(stock_data, signals=None)

        # 保存因子数据：优先使用显式传入的预计算面板，
        # 若缺失则仅做一次从 stock_data 的同名列推断，避免在回测内跨源兜底拼装。
        if factor_data is None:
            self.factor_data_cache = _infer_factor_data_from_stock_data(stock_data, self.factor_names)
        else:
            self.factor_data_cache = factor_data

        # 生成每日因子信号
        logger.info("多因子回测开始生成信号")
        self._emit_progress(30, f"开始生成因子信号，共 {len(stock_data)} 只股票")
        all_signals = {}

        # 获取所有日期
        if stock_data:
            first_df = list(stock_data.values())[0]
            if 'date' in first_df.columns:
                all_dates = pd.to_datetime(first_df['date']).dt.strftime('%Y-%m-%d').tolist()
            else:
                all_dates = first_df.index.strftime('%Y-%m-%d').tolist()
        else:
            all_dates = []

        # 为每个日期生成信号
        total_dates = len(all_dates)
        signal_step = max(1, total_dates // 10) if total_dates > 0 else 1
        for idx, date in enumerate(all_dates):
            daily_signals = self._generate_factor_signals(date, stock_data)
            for symbol, signal_series in daily_signals.items():
                if symbol not in all_signals:
                    all_signals[symbol] = []
                all_signals[symbol].append((date, signal_series.iloc[0] if len(signal_series) > 0 else 0))
            if idx == 0 or idx % signal_step == 0 or idx == total_dates - 1:
                percent = 30 + int(((idx + 1) / max(1, total_dates)) * 20)
                self._emit_progress(percent, f"因子信号生成进度 {idx + 1}/{total_dates}（日期 {date}）")

        # 转换为 Series 格式
        self.signals = {}
        for symbol, signal_list in all_signals.items():
            if signal_list:
                dates_list = [s[0] for s in signal_list]
                values_list = [s[1] for s in signal_list]
                self.signals[symbol] = pd.Series(values_list, index=dates_list)

        logger.info("多因子回测信号生成完成: symbols_with_signals=%s", len(self.signals))
        self._emit_progress(50, f"因子信号生成完成，有效股票 {len(self.signals)} 只")

    def run(
        self,
        symbols: List[str],
        stock_data: Dict[str, pd.DataFrame],
        start_date: str = None,
        end_date: str = None,
        factor_data: Dict[str, pd.DataFrame] = None,
        initial_weights: Dict[str, float] = None
    ) -> Dict[str, Any]:
        """
        运行多因子回测

        Args:
            symbols: 股票池
            stock_data: 股票数据 {symbol: dataframe with date, open, high, low, close, volume}
            start_date: 开始日期
            end_date: 结束日期
            factor_data: 因子数据（可选，运行时计算）
            initial_weights: 初始因子权重（覆盖默认配置）

        Returns:
            回测结果 + 因子分析结果
        """
        logger.info("开始多因子回测: initial_capital=%.2f symbols=%s", self.initial_capital, len(symbols))
        self._emit_progress(52, "多因子引擎准备完成，开始执行组合回测")

        # 重置调仓快照（每次回测重新记录）
        self.rebalance_snapshots = []
        self.first_buy_date = None
        self.pre_first_buy_diagnostics = []
        # 注意：不重置 _factor_panel_cache 等缓存，
        # 因为 set_data() 中已生成，而 run() 中不会重新调用 set_data()

        # 更新初始权重
        if initial_weights:
            self.factor_weights = initial_weights
            self.signal_generator.update_weights(factor_weights=initial_weights)

        # Step 1: 初始化 IC 权重状态（实际更新在调仓点触发）
        self.ic_update_counter = 0
        if self.use_ic_weighting:
            self.ic_weights = self.factor_weights.copy()
            self.signal_generator.update_weights(ic_weights=self.ic_weights)
        else:
            self.ic_weights = self.factor_weights.copy()

        # Step 2: 调用父类回测
        results = super().run(start_date, end_date)
        if results.get("error"):
            return results

        # Step 3: 生成因子分析报告
        self._emit_progress(96, "组合回测完成，正在生成因子分析报告")
        factor_report = self._generate_factor_report(results)
        results['factor_report'] = factor_report

        # ===== 新增：将调仓快照加入结果 =====
        results['rebalance_snapshots'] = self.rebalance_snapshots
        results['factor_names'] = self.factor_names
        results['first_buy_date'] = self.first_buy_date
        results['pre_first_buy_diagnostics'] = self.pre_first_buy_diagnostics

        # 打印因子报告摘要
        self._print_factor_summary(factor_report)
        self._emit_progress(100, "多因子回测全部完成")

        return results

    def _update_ic_weights(self):
        """根据 IC 统计更新因子权重"""
        logger.info("开始加载 IC 统计: factors=%s", self.factor_names)

        ic_stats = self.ic_configurator.load_ic_stats(self.factor_names)

        if ic_stats and any(s['ic_mean'] != 0 for s in ic_stats.values()):
            self.ic_weights = self.ic_configurator.calculate_weights(
                self.factor_weights,
                ic_stats
            )
            self.signal_generator.update_weights(ic_weights=self.ic_weights)

            logger.info("IC 调整后权重已更新")
            for factor, weight in sorted(self.ic_weights.items(), key=lambda x: x[1], reverse=True):
                stats = ic_stats.get(factor, {})
                ic_mean = stats.get('ic_mean', 0)
                ir = stats.get('ir', 0)
                validity = self.ic_configurator.judge_factor_validity(stats)
                logger.info(
                    "IC权重明细: factor=%s weight=%.6f ic_mean=%.6f ir=%.6f validity=%s",
                    factor, weight, ic_mean, ir, validity
                )
        else:
            logger.info("无可用 IC 统计，回退基础权重")
            self.ic_weights = self.factor_weights.copy()

    def _maybe_update_ic_weights_for_rebalance(self):
        """
        按调仓计数触发 IC 权重更新。
        - 首次调仓强制更新一次；
        - 后续每 ic_update_freq 次调仓更新一次。
        """
        if not self.use_ic_weighting:
            return
        self.ic_update_counter += 1
        if self.ic_update_counter == 1:
            self._update_ic_weights()
            return
        if self.ic_update_freq > 0 and self.ic_update_counter % self.ic_update_freq == 0:
            self._update_ic_weights()

    def _generate_factor_signals(
        self,
        date: str,
        stock_data: Dict[str, pd.DataFrame]
    ) -> Dict[str, pd.Series]:
        """
        根据因子生成交易信号

        Args:
            date: 当前日期
            stock_data: 股票数据

        Returns:
            {symbol: signal_series}
        """
        signals = {}

        # 构建因子面板
        factor_panel = self._build_factor_panel(date, stock_data)

        if factor_panel.empty:
            return signals

        # ===== 缓存因子面板 =====
        self._factor_panel_cache[date] = factor_panel.copy()

        # 计算百分位得分并缓存
        percentile_scores = self.signal_generator._calculate_percentile_scores(factor_panel)
        self._factor_percentiles_cache[date] = percentile_scores

        # 计算综合得分并缓存
        combined_scores = self.signal_generator._calculate_combined_scores(percentile_scores)
        self._composite_scores_cache[date] = combined_scores

        # 生成排名信号
        top_n = self.max_positions
        raw_signals = self.signal_generator.generate_ranking_signals(factor_panel, top_n=top_n)

        # 转换为信号序列
        for symbol, signal in raw_signals.items():
            # 创建单日信号序列
            signals[symbol] = pd.Series([signal], index=[date])

        return signals

    def _build_factor_panel(
        self,
        date: str,
        stock_data: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """
        构建因子面板

        Args:
            date: 当前日期
            stock_data: 股票数据

        Returns:
            DataFrame(index=symbol, columns=factor_values)
        """
        panel_data = []

        for symbol in stock_data.keys():
            df = stock_data[symbol]

            # 找到当日的数据
            if 'date' in df.columns:
                df_dates = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
                row = df[df_dates == date]
            else:
                if isinstance(df.index, pd.DatetimeIndex):
                    row = df[df.index.strftime('%Y-%m-%d') == date]
                else:
                    row = df[df.index.astype(str) == date]

            if row.empty:
                continue

            row_index_key = row.index[0]
            if 'date' in df.columns:
                close_idx = int(row_index_key)
            else:
                loc = df.index.get_loc(row_index_key)
                if isinstance(loc, slice):
                    close_idx = loc.start
                elif isinstance(loc, np.ndarray):
                    close_idx = int(loc[0]) if len(loc) > 0 else -1
                else:
                    close_idx = int(loc)

            row = row.iloc[0]

            # 构建因子字典
            factor_values = {}

            # 技术因子（如果有）
            if 'momentum_20' in self.factor_names and 'close' in df.columns:
                # 计算动量
                if close_idx >= 20:
                    mom = (df['close'].iloc[close_idx] - df['close'].iloc[close_idx - 20]) / df['close'].iloc[close_idx - 20]
                    factor_values['momentum_20'] = mom

            if 'volatility_20' in self.factor_names and 'close' in df.columns:
                if close_idx >= 20:
                    returns = df['close'].pct_change().iloc[max(0, close_idx-20):close_idx]
                    factor_values['volatility_20'] = returns.std()

            # 基本面因子 - 优先从 factor_data_cache 获取
            if symbol in self.factor_data_cache:
                factor_df = self.factor_data_cache[symbol]
                if 'date' in factor_df.columns:
                    factor_dates = pd.to_datetime(factor_df['date']).dt.strftime('%Y-%m-%d')
                    factor_row = factor_df[factor_dates == date]
                else:
                    factor_row = factor_df[factor_df.index == date]

                if not factor_row.empty:
                    factor_row = factor_row.iloc[0]
                    for factor in self.factor_names:
                        if factor not in factor_values and factor in factor_row.index:
                            factor_values[factor] = factor_row[factor]

            factor_values['symbol'] = symbol
            panel_data.append(factor_values)

        if not panel_data:
            return pd.DataFrame()

        panel = pd.DataFrame(panel_data).set_index('symbol')

        return panel

    def _rebalance(self, date, prices: Dict[str, float]):
        """调仓：重写父类方法，增加因子信息记录和调仓快照"""
        self._maybe_update_ic_weights_for_rebalance()
        date_str = str(date)[:10]

        # 0. 排除当天止损卖出的股票
        stop_loss_sold = self._stop_loss_sold_today.copy()

        # 1. 选出新的候选股票
        new_candidates = self._select_candidates()

        if not new_candidates:
            self._record_pre_first_buy_debug({
                "date": date_str,
                "reason": "no_candidates",
                "candidate_count": 0,
                "cash": round(float(self.cash), 2),
                "positions_count": len(self.positions),
            })
            return

        # 过滤掉当天止损卖出的股票
        new_candidates = [c for c in new_candidates if c.symbol not in stop_loss_sold]

        if not new_candidates:
            self._record_pre_first_buy_debug({
                "date": date_str,
                "reason": "all_candidates_filtered_by_stop_loss_today",
                "candidate_count": 0,
                "cash": round(float(self.cash), 2),
                "positions_count": len(self.positions),
            })
            return

        # 2. 计算目标持仓
        target_symbols = {score.symbol for score in new_candidates}
        current_symbols = set(self.positions.keys())

        # 3. 卖出不在目标中的持仓
        to_sell = current_symbols - target_symbols
        for symbol in to_sell:
            self._close_position(symbol, date, prices.get(symbol, 0), "调仓换股")

        # ===== 新增：创建调仓快照 =====
        snapshot = RebalanceSnapshot(date=str(date)[:10])

        # 记录全部候选股票的因子信息
        if date_str in self._composite_scores_cache:
            snapshot.all_scores = self._composite_scores_cache[date_str]
        if date_str in self._factor_panel_cache:
            panel = self._factor_panel_cache[date_str]
            for symbol in panel.index:
                snapshot.all_factor_values[symbol] = {
                    f: panel.loc[symbol, f]
                    for f in self.factor_names if f in panel.columns
                }
        if date_str in self._factor_percentiles_cache:
            snapshot.all_factor_percentiles = self._factor_percentiles_cache[date_str]

        # 记录卖出股票
        snapshot.sold_symbols = list(to_sell)

        # 4. 分配仓位并买入
        debug_stats = {
            "date": date_str,
            "reason": "rebalance_no_buy",
            "candidate_count": len(new_candidates),
            "allocation_count": 0,
            "price_available_count": 0,
            "executed_buy_count": 0,
            "skip_non_positive_weight": 0,
            "skip_missing_price": 0,
            "skip_target_already_reached": 0,
            "skip_lot_too_small": 0,
            "cash": round(float(self.cash), 2),
            "positions_count": len(self.positions),
        }

        if self.cash > 0:
            # 准备候选股票数据（包含得分和波动率）
            candidate_data = []
            for score in new_candidates:
                volatility = self._estimate_volatility(score.symbol)
                candidate_data.append((score.symbol, score.composite_score, volatility))

            # 分配仓位（基于总资产计算目标权重）
            total_assets = self.cash + sum(p.market_value for p in self.positions.values())
            allocations = self.position_sizer.allocate(
                candidate_data,
                total_assets,
                prices
            )
            debug_stats["allocation_count"] = len(allocations)

            # 执行买入（扣除已有持仓，只买差额部分）
            for alloc in allocations:
                if alloc.weight <= 0:
                    debug_stats["skip_non_positive_weight"] += 1
                    continue
                if alloc.symbol not in prices:
                    debug_stats["skip_missing_price"] += 1
                    continue

                debug_stats["price_available_count"] += 1

                # 计算目标持仓金额
                target_amount = total_assets * alloc.weight
                # 扣除已有持仓市值
                current_holding = self.positions[alloc.symbol].market_value if alloc.symbol in self.positions else 0
                buy_amount_needed = target_amount - current_holding

                if buy_amount_needed <= 0:
                    # 已达目标仓位，不需要加仓
                    debug_stats["skip_target_already_reached"] += 1
                    continue

                # 根据需要买入的金额计算股数
                price = prices[alloc.symbol]
                buy_shares = int(buy_amount_needed / price / 100) * 100
                if buy_shares < 100:
                    debug_stats["skip_lot_too_small"] += 1
                    continue

                # 获取该股票的因子信息
                factor_values = {}
                factor_percentiles = {}
                composite_score = 0.0
                rank = 0

                if date_str in self._factor_panel_cache:
                    panel = self._factor_panel_cache[date_str]
                    if alloc.symbol in panel.index:
                        factor_values = {
                            f: panel.loc[alloc.symbol, f]
                            for f in self.factor_names if f in panel.columns
                        }

                if date_str in self._factor_percentiles_cache:
                    percs = self._factor_percentiles_cache[date_str]
                    factor_percentiles = percs.get(alloc.symbol, {})

                if date_str in self._composite_scores_cache:
                    scores = self._composite_scores_cache[date_str]
                    composite_score = scores.get(alloc.symbol, 0)
                    # 计算排名
                    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                    for i, (sym, _) in enumerate(sorted_scores):
                        if sym == alloc.symbol:
                            rank = i + 1
                            break

                # 获取股票名称
                stock_name = self.stock_names.get(alloc.symbol, "")

                # 执行买入（传入因子信息）
                self._buy_multi_factor(
                    alloc.symbol, date, price, buy_shares, total_assets, "调仓买入",
                    stock_name=stock_name,
                    factor_values=factor_values,
                    factor_percentiles=factor_percentiles,
                    composite_score=composite_score,
                    rank=rank,
                    total_candidates=len(snapshot.all_scores)
                )

                snapshot.selected_symbols.append(alloc.symbol)
                debug_stats["executed_buy_count"] += 1

        if self.first_buy_date is None and debug_stats["executed_buy_count"] > 0:
            self.first_buy_date = date_str
        self._record_pre_first_buy_debug(debug_stats)

        # 保存调仓快照
        self.rebalance_snapshots.append(snapshot)
        self.last_rebalance_day = self.trading_days

    def _record_pre_first_buy_debug(self, debug_row: Dict[str, Any]) -> None:
        """记录首笔买入前的调仓诊断信息。"""
        if self.first_buy_date is not None:
            return
        if len(self.pre_first_buy_diagnostics) >= 200:
            return
        self.pre_first_buy_diagnostics.append(debug_row)

    def _buy_multi_factor(
        self,
        symbol: str,
        date,
        price: float,
        quantity: int,
        total_assets: float,
        reason: str = "",
        stock_name: str = "",
        factor_values: Dict[str, float] = None,
        factor_percentiles: Dict[str, float] = None,
        composite_score: float = 0.0,
        rank: int = 0,
        total_candidates: int = 0
    ):
        """
        多因子专用买入方法
        调用父类 _buy() 执行实际买入，然后补充因子信息到 TradeDetail
        """
        # 调用父类买入（执行实际交易逻辑）
        super()._buy(symbol, date, price, quantity, total_assets, reason, stock_name=stock_name)

        # 补充因子信息到 active_trades
        if symbol in self.active_trades:
            td = self.active_trades[symbol]
            td.factor_values = factor_values or {}
            td.factor_percentiles = factor_percentiles or {}
            td.composite_score = composite_score
            td.rank = rank
            td.total_candidates = total_candidates

    def _record_factor_exposure(
        self,
        date: str,
        positions: Dict[str, PortfolioPosition],
        stock_data: Dict[str, pd.DataFrame]
    ):
        """
        记录因子暴露度

        Args:
            date: 当前日期
            positions: 当前持仓
            stock_data: 股票数据
        """
        if not positions:
            return

        # 构建持仓市值字典
        position_values = {
            symbol: pos.market_value
            for symbol, pos in positions.items()
        }

        # 构建因子值字典
        factor_values = {}
        for symbol, pos in positions.items():
            if symbol in stock_data:
                df = stock_data[symbol]
                if 'date' in df.columns:
                    df_dates = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
                    row = df[df_dates == date]
                else:
                    row = df[df.index == date]

                if not row.empty:
                    row = row.iloc[0]
                    factor_values[symbol] = {
                        f: row[f] for f in self.factor_names if f in row.index
                    }

        # 记录暴露度
        self.exposure_tracker.record_exposure(
            date=date,
            positions=position_values,
            factor_values=factor_values
        )

    def _generate_factor_report(self, backtest_results: Dict) -> Dict[str, Any]:
        """
        生成因子分析报告

        Args:
            backtest_results: 回测结果

        Returns:
            因子分析报告
        """
        report = {
            'factor_weights': self.factor_weights,
            'ic_weights': self.ic_weights,
            'exposure_summary': None,
            'attribution': {},
            'ic_validity_report': None
        }

        # 暴露度摘要
        exposure_summary = self.exposure_tracker.calculate_exposure_summary()
        if not exposure_summary.empty:
            report['exposure_summary'] = exposure_summary

        # IC 有效性回顾
        ic_stats = self.ic_configurator.load_ic_stats(self.factor_names)
        if ic_stats:
            ic_validity = {}
            for factor, stats in ic_stats.items():
                ic_validity[factor] = {
                    'ic_mean': stats.get('ic_mean', 0),
                    'ir': stats.get('ir', 0),
                    'validity': self.ic_configurator.judge_factor_validity(stats)
                }
            report['ic_validity_report'] = ic_validity

        # 收益归因
        if 'equity_curve' in backtest_results:
            equity_df = backtest_results['equity_curve']
            if 'return' in equity_df.columns and not equity_df['return'].isna().all():
                portfolio_returns = equity_df.set_index('date')['return']
                if report['exposure_summary'] is not None:
                    # 简化的归因计算
                    exposure_df = self.exposure_tracker.get_exposure_timeseries()
                    if exposure_df is not None and not exposure_df.empty:
                        # 使用因子暴露度与收益的相关性作为归因近似
                        for factor in self.factor_names:
                            if factor in exposure_df.columns:
                                corr = exposure_df[factor].corr(equity_df.set_index('date')['return'])
                                report['attribution'][factor] = corr

        return report

    def _print_factor_summary(self, factor_report: Dict):
        """打印因子报告摘要"""
        logger.info("输出因子分析摘要")
        for factor, weight in sorted(self.factor_weights.items(), key=lambda x: x[1], reverse=True):
            ic_weight = self.ic_weights.get(factor, weight) if self.ic_weights else weight
            diff = ic_weight - weight
            logger.info(
                "因子权重: factor=%s base_weight=%.6f ic_weight=%.6f delta=%.6f",
                factor, weight, ic_weight, diff
            )

        # IC 有效性
        if factor_report.get('ic_validity_report'):
            validity_counts = {}
            for factor, data in factor_report['ic_validity_report'].items():
                validity = data['validity']
                validity_counts[validity] = validity_counts.get(validity, 0) + 1

            for validity, count in sorted(validity_counts.items()):
                logger.info("IC有效性统计: validity=%s count=%s", validity, count)

        # 暴露度摘要
        if factor_report.get('exposure_summary') is not None:
            summary = factor_report['exposure_summary']
            for factor in summary.index[:5]:
                avg_exp = summary.loc[factor, '平均暴露度']
                logger.info("因子暴露度: factor=%s avg_exposure=%.6f", factor, avg_exp)


def run_multi_factor_backtest(
    symbols: List[str],
    stock_data: Dict[str, pd.DataFrame],
    factor_data: Dict[str, pd.DataFrame] = None,
    start_date: str = None,
    end_date: str = None,
    initial_capital: float = 1000000,
    max_positions: int = 5,
    rebalance_days: int = 5,
    factor_weights: Dict[str, float] = None,
    use_ic_weighting: bool = True,
    ic_update_freq: int = 60,
    stock_names: Dict[str, str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    运行多因子回测的便捷函数

    Args:
        symbols: 股票池
        stock_data: 股票数据
        factor_data: 因子数据
        start_date: 开始日期
        end_date: 结束日期
        initial_capital: 初始资金
        max_positions: 最大持仓数
        rebalance_days: 调仓周期
        factor_weights: 因子权重
        use_ic_weighting: 是否使用 IC 加权
        ic_update_freq: IC 更新频率
        stock_names: 股票名称映射 {symbol: name}
        **kwargs: 其他参数

    Returns:
        回测结果
    """
    _assert_real_market_data(stock_data)

    # 默认因子权重
    default_weights = {
        'roe': 0.25,
        'pe': 0.10,
        'pb': 0.10,
        'momentum_20': 0.20,
        'revenue_growth': 0.15,
        'debt_ratio': 0.10,
        'liquidity': 0.10
    }

    if factor_weights:
        default_weights.update(factor_weights)

    if factor_data is None:
        factor_data = _infer_factor_data_from_stock_data(
            stock_data=stock_data,
            factor_names=list(default_weights.keys()),
        )

    # 创建回测引擎
    # 从 kwargs 中提取 progress_callback，避免重复传递
    progress_callback = kwargs.pop('progress_callback', None)
    backtest = MultiFactorBacktest(
        initial_capital=initial_capital,
        max_positions=max_positions,
        rebalance_days=rebalance_days,
        factor_weights=default_weights,
        factor_names=list(default_weights.keys()),
        use_ic_weighting=use_ic_weighting,
        ic_update_freq=ic_update_freq,
        progress_callback=progress_callback,
        **kwargs
    )

    # 设置股票名称映射
    if stock_names:
        backtest.stock_names = stock_names

    # 设置数据并运行
    backtest.set_data(stock_data, factor_data=factor_data)

    return backtest.run(
        symbols=symbols,
        stock_data=stock_data,
        start_date=start_date,
        end_date=end_date,
        factor_data=factor_data
    )


def _infer_factor_data_from_stock_data(
    stock_data: Dict[str, pd.DataFrame],
    factor_names: List[str],
) -> Dict[str, pd.DataFrame]:
    """
    兼容入口：当未显式传入 factor_data 时，尝试从 stock_data 中提取同名因子列。
    """
    inferred: Dict[str, pd.DataFrame] = {}
    base_cols = {"date", "open", "high", "low", "close", "volume", "amount"}

    for symbol, df in stock_data.items():
        if df is None or df.empty:
            continue
        if "date" in df.columns:
            factor_df = pd.DataFrame({"date": df["date"], "symbol": symbol})
        else:
            factor_df = pd.DataFrame({"date": df.index, "symbol": symbol})

        for factor_name in factor_names:
            if factor_name in base_cols:
                continue
            if factor_name in df.columns:
                factor_df[factor_name] = pd.to_numeric(df[factor_name], errors="coerce")

        if len(factor_df.columns) > 2:
            inferred[symbol] = factor_df

    return inferred


if __name__ == "__main__":
    # 使用数据库中的真实数据演示（不再使用随机模拟数据）
    from data.data_provider import CacheOnlyProvider
    from strategy.fundamental_factors import FundamentalFactors

    symbols = ["000001.SZ", "600000.SH", "600519.SH", "600016.SH", "601318.SH"]
    start_date = "2023-01-01"
    end_date = "2023-06-30"

    provider = CacheOnlyProvider(str(DATABASE_PATH))
    stock_data: Dict[str, pd.DataFrame] = {}
    factor_data: Dict[str, pd.DataFrame] = {}
    factor_names = ["roe", "pe", "pb", "revenue_growth", "debt_ratio"]

    ff = FundamentalFactors(str(DATABASE_PATH))
    try:
        for symbol in symbols:
            df = provider.get_stock_data(symbol, start_date, end_date)
            if df.empty:
                continue

            stock_data[symbol] = df
            factor_df = pd.DataFrame({"date": df["date"]})
            for factor in factor_names:
                factor_df[factor] = np.nan

            for idx, trade_date in enumerate(pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")):
                factors = ff.calculate_all_factors(symbol, trade_date)
                for factor in factor_names:
                    if factor in factors:
                        factor_df.at[factor_df.index[idx], factor] = factors[factor]

            factor_data[symbol] = factor_df.ffill()
    finally:
        ff.close()

    if not stock_data:
        raise SystemExit("未找到可用真实行情数据，请先更新数据库后再运行。")

    results = run_multi_factor_backtest(
        symbols=list(stock_data.keys()),
        stock_data=stock_data,
        factor_data=factor_data,
        start_date=start_date,
        end_date=end_date,
        initial_capital=1000000,
        max_positions=3,
        rebalance_days=20,
        use_ic_weighting=False
    )

    print("\n回测完成（真实数据）!")
    print(f"总收益率: {results['total_return']:.2%}")
    print(f"年化收益率: {results['annual_return']:.2%}")
    print(f"夏普比率: {results['sharpe_ratio']:.2f}")

"""
多因子回测页 (FactorBacktestPage) — 阶段3迁移（原 Tab4 / web/factor_backtest_page.py）

替代 web/factor_backtest_page.py 的「多因子回测」页面。原实现用 st.sidebar 配置 +
st.tabs + st.rerun + st.progress 联动；桌面版改用：

- 左侧滚动配置区（因子分类勾选 / IC智能加权 or 手动权重 / 回测参数 / 风控 / 执行）
- 右侧 QTabWidget 结果区（收益概览 / 因子分析 / 交易明细 / 调仓记录 / 配置管理）
- 回测在子线程执行（_prepare_factor_data + run_multi_factor_strategy_backtest），
  通过 run_with_progress 显示进度；中断按钮调用 worker.cancel()
- 结果写入 AppState.mfbt_results / multi_backtest_results，绩效页可联动展示

所有因子计算与回测引擎复用 web 层服务，不在桌面层重写。
"""
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGroupBox,
    QPushButton, QComboBox, QLineEdit, QCheckBox, QSpinBox, QScrollArea,
    QDateEdit, QTabWidget, QRadioButton, QButtonGroup, QListWidget,
    QMessageBox, QFormLayout, QPlainTextEdit, QSplitter, QSizePolicy,
    QProgressBar, QDoubleSpinBox, QAbstractItemView, QFileDialog,
)
from PySide6.QtCore import Qt, QDate

from desktop.pages.base_page import BasePage
from desktop.widgets.section_title import SectionTitle
from desktop.widgets.metric_card import MetricCard
from desktop.widgets.message_bar import MessageBar
from desktop.widgets.pandas_table import PandasTableView, make_change_color_rule
from desktop.widgets.chart_container import ChartContainer
from desktop.widgets.async_worker import run_with_progress
from desktop.models.managers import Managers
from desktop.models.app_state import AppState

from data.data_provider import CacheOnlyProvider
from data.data_manager import DataManager
from portfolio.watchlist import (
    WatchlistManager, filter_out_benchmark_stocks, filter_out_benchmark_symbols,
)
from strategy.fundamental_factors import FundamentalFactors
from web.services.backtest_service import run_multi_factor_strategy_backtest


# 因子分类（展示名，与 web/factor_backtest_page.FACTOR_CATEGORIES 保持一致）
FACTOR_CATEGORIES = {
    "基本面因子": {
        "roe": "ROE（净资产收益率）", "roe_avg": "净资产收益率(平均)", "roa": "ROA（资产收益率）",
        "gross_margin": "毛利率", "net_margin": "净利率", "np_margin": "销售净利率(npMargin)",
        "gp_margin": "销售毛利率(gpMargin)", "eps": "EPS（每股收益）", "eps_ttm": "epsTTM",
        "net_profit": "netProfit（净利润）", "mb_revenue": "MBRevenue（主营业务收入）",
        "total_share": "totalShare（总股本）", "liqa_share": "liqaShare（流通股本）",
        "revenue_growth": "营收增长率", "profit_growth": "利润增长率", "asset_turnover": "资产周转率",
    },
    "估值因子": {"pe": "PE（市盈率）", "pb": "PB（市净率）", "ps": "PS（市销率）", "pcf": "PCF（现金流倍率）"},
    "技术因子": {
        "momentum_20": "20日动量", "momentum_60": "60日动量", "volatility_20": "20日波动率",
        "volume_ratio": "量比", "turnover_rate": "换手率",
    },
    "财务结构": {"debt_ratio": "资产负债率", "current_ratio": "流动比率", "quick_ratio": "速动比率"},
    "情绪因子": {"price_volume_trend": "价量趋势", "relative_strength": "相对强弱"},
}
# 默认勾选因子。
# 注：原 web 版此处写的是 "情绪因子": ["turnover_rate"]，但 turnover_rate 属于「技术因子」，
# 该条目在原版实际是死配置（永不生效）。此处移除以保持有效默认值与原版完全一致：
# roe / revenue_growth / pe / pb / momentum_20 / debt_ratio 共 6 个。
DEFAULT_FACTORS = {
    "基本面因子": ["roe", "revenue_growth"],
    "估值因子": ["pe", "pb"],
    "技术因子": ["momentum_20"],
    "财务结构": ["debt_ratio"],
    "情绪因子": [],
}
POSITION_METHODS = [("equal", "等权分配"), ("factor_weighted", "因子加权"), ("risk_parity", "风险平价")]
IC_VALIDITY_ICONS = {"strong": "🟢", "normal": "🟡", "weak": "🟠", "invalid": "🔴"}


# ============ 模块级辅助函数（可在子线程执行）============

def _fetch_stock_data(db_path, symbols, start_date, end_date):
    provider = CacheOnlyProvider(db_path)
    stock_data = {}
    for symbol in symbols:
        try:
            df = provider.get_stock_data(symbol, start_date, end_date)
            if not df.empty:
                stock_data[symbol] = df
        except Exception:
            continue
    return stock_data


def _compute_effective_backtest_window(stock_data, requested_start, requested_end):
    if not stock_data:
        return None, None
    req_start = pd.to_datetime(requested_start)
    req_end = pd.to_datetime(requested_end)
    min_dates, max_dates = [], []
    for df in stock_data.values():
        if df is None or df.empty or "date" not in df.columns:
            continue
        dt = pd.to_datetime(df["date"], errors="coerce").dropna()
        if dt.empty:
            continue
        min_dates.append(dt.min())
        max_dates.append(dt.max())
    if not min_dates or not max_dates:
        return None, None
    eff_start = max(req_start, max(min_dates))
    eff_end = min(req_end, min(max_dates))
    if eff_start > eff_end:
        return None, None
    return eff_start.strftime("%Y-%m-%d"), eff_end.strftime("%Y-%m-%d")


def _backfill_stock_data_to_start_date(db_path, symbols, start_date, end_date):
    provider = CacheOnlyProvider(db_path)
    attempted = updated = unchanged = 0
    for symbol in symbols:
        try:
            before = provider.get_stock_data(symbol, start_date, end_date)
            before_min = None if before.empty else pd.to_datetime(before["date"]).min()
            attempted += 1
            dm = DataManager(db_path)
            try:
                dm.get_daily_kline(symbol, start_date, end_date)
            finally:
                try:
                    dm.close()
                except Exception:
                    pass
            after = provider.get_stock_data(symbol, start_date, end_date)
            after_min = None if after.empty else pd.to_datetime(after["date"]).min()
            if before_min is None and after_min is not None:
                updated += 1
            elif before_min is not None and after_min is not None and after_min < before_min:
                updated += 1
            else:
                unchanged += 1
        except Exception:
            unchanged += 1
    return {"attempted": attempted, "updated": updated, "unchanged": unchanged}


def _prepare_factor_data(db_path, stock_data, factor_names, progress_callback=None):
    """
    准备因子面板（子线程执行，逻辑对齐 web/factor_backtest_page._prepare_factor_data）。

    技术/情绪类因子直接由行情计算；其余因子优先读 factor_values 缓存表，
    未命中的按日兜底计算并回写缓存。

    Returns:
        Dict[symbol, DataFrame]，列为 ['date', 'symbol'] + 命中的因子列
    """
    factor_data = {}
    ff = FundamentalFactors(db_path)
    cached_rows = []

    price_driven_factors = {
        'momentum_20', 'momentum_60', 'volatility_20',
        'price_volume_trend', 'relative_strength', 'volume_ratio',
    }
    db_factor_names = [f for f in factor_names
                       if f not in price_driven_factors and f != 'turnover_rate']

    total = max(len(stock_data), 1)
    try:
        for i, (symbol, df) in enumerate(stock_data.items()):
            if progress_callback:
                pct = 30 + int(20 * i / total)
                if progress_callback(pct, f"准备因子数据 {i + 1}/{total}：{symbol}") is False:
                    break

            factor_df = pd.DataFrame(index=df.index)
            factor_df['date'] = df['date'] if 'date' in df.columns else df.index
            factor_df['symbol'] = symbol

            date_series = pd.to_datetime(factor_df['date']).dt.strftime('%Y-%m-%d')
            f_start = date_series.iloc[0] if len(date_series) > 0 else None
            f_end = date_series.iloc[-1] if len(date_series) > 0 else None

            # --- 技术 / 情绪因子：直接由价格成交量计算 ---
            if 'close' in df.columns:
                close = pd.to_numeric(df['close'], errors='coerce')
                returns = close.pct_change()
                factor_df['momentum_20'] = returns.rolling(20).sum()
                factor_df['momentum_60'] = returns.rolling(60).sum()
                factor_df['volatility_20'] = returns.rolling(20).std()
                factor_df['price_volume_trend'] = (
                    returns.fillna(0)
                    * pd.to_numeric(df.get('volume', 0), errors='coerce').fillna(0)
                ).cumsum()
                factor_df['relative_strength'] = close / close.shift(20) - 1

            if 'volume' in df.columns:
                vol = pd.to_numeric(df['volume'], errors='coerce')
                factor_df['volume_ratio'] = vol / vol.rolling(20).mean()

            # --- 批量读取 factor_values 缓存 ---
            if db_factor_names and f_start and f_end:
                conn = sqlite3.connect(ff.fdm.db_path)
                try:
                    placeholders = ",".join(["?" for _ in db_factor_names])
                    cached_df = pd.read_sql_query(
                        f"""
                        SELECT trade_date, factor_name, factor_value
                        FROM factor_values
                        WHERE symbol = ?
                          AND trade_date BETWEEN ? AND ?
                          AND factor_name IN ({placeholders})
                        ORDER BY trade_date
                        """,
                        conn, params=[symbol, f_start, f_end] + db_factor_names)
                except Exception:
                    cached_df = pd.DataFrame()
                finally:
                    conn.close()

                if not cached_df.empty:
                    cached_df['trade_date'] = pd.to_datetime(
                        cached_df['trade_date']).dt.strftime('%Y-%m-%d')
                    pivot_df = cached_df.pivot_table(
                        index='trade_date', columns='factor_name',
                        values='factor_value', aggfunc='last')
                    trade_date_map = date_series.to_dict()
                    for factor in db_factor_names:
                        source_factor = factor
                        if (factor == 'eps' and source_factor not in pivot_df.columns
                                and 'eps_ttm' in pivot_df.columns):
                            source_factor = 'eps_ttm'
                        if source_factor in pivot_df.columns:
                            series_map = pivot_df[source_factor].to_dict()
                            factor_df[factor] = pd.Series(trade_date_map).map(series_map).values

            # --- 换手率：从估值表取 float_shares 向前匹配 ---
            if 'turnover_rate' in factor_names and 'volume' in df.columns and f_start and f_end:
                conn = sqlite3.connect(ff.fdm.db_path)
                try:
                    valuation_df = pd.read_sql_query(
                        """
                        SELECT trade_date, float_shares
                        FROM valuation_data
                        WHERE symbol = ? AND trade_date BETWEEN ? AND ?
                        ORDER BY trade_date
                        """, conn, params=(symbol, f_start, f_end))
                except Exception:
                    valuation_df = pd.DataFrame()
                finally:
                    conn.close()

                if not valuation_df.empty:
                    trade_dates_df = pd.DataFrame(
                        {'trade_date': pd.to_datetime(date_series)}).sort_values('trade_date')
                    valuation_df['trade_date'] = pd.to_datetime(valuation_df['trade_date'])
                    valuation_df['float_shares'] = pd.to_numeric(
                        valuation_df['float_shares'], errors='coerce')
                    valuation_df = valuation_df.dropna(
                        subset=['float_shares']).sort_values('trade_date')
                    if not valuation_df.empty:
                        merged_df = pd.merge_asof(
                            trade_dates_df, valuation_df[['trade_date', 'float_shares']],
                            on='trade_date', direction='backward')
                        volume_series = pd.to_numeric(df.get('volume', np.nan), errors='coerce')
                        factor_df['turnover_rate'] = np.where(
                            merged_df['float_shares'].fillna(0) > 0,
                            (volume_series.values / merged_df['float_shares'].values) * 100,
                            np.nan)

            # --- 未命中因子按日兜底计算 ---
            fallback_factors = [f for f in factor_names
                                if f not in factor_df.columns or factor_df[f].isna().all()]
            if fallback_factors:
                for idx, trade_date in enumerate(date_series):
                    try:
                        day_factors = ff.calculate_all_factors(symbol, trade_date)
                    except Exception:
                        day_factors = {}
                    for factor in fallback_factors:
                        current_val = (factor_df.at[factor_df.index[idx], factor]
                                       if factor in factor_df.columns else np.nan)
                        if pd.notna(current_val):
                            continue
                        if factor in day_factors:
                            value = day_factors.get(factor, np.nan)
                            factor_df.at[factor_df.index[idx], factor] = value
                            if pd.notna(value):
                                cached_rows.append((symbol, trade_date, factor, float(value)))
                        elif factor == 'eps' and 'eps_ttm' in day_factors:
                            value = day_factors.get('eps_ttm', np.nan)
                            factor_df.at[factor_df.index[idx], factor] = value
                            if pd.notna(value):
                                cached_rows.append((symbol, trade_date, factor, float(value)))

            # --- 前向填充，对齐季度数据到交易日 ---
            for factor in factor_names:
                if factor in factor_df.columns:
                    factor_df[factor] = pd.to_numeric(
                        factor_df[factor], errors='coerce').ffill()

            keep_cols = ['date', 'symbol'] + [f for f in factor_names if f in factor_df.columns]
            factor_data[symbol] = factor_df[keep_cols].copy()

        # --- 兜底现算结果回写缓存 ---
        if cached_rows:
            conn = sqlite3.connect(ff.fdm.db_path)
            try:
                conn.cursor().executemany(
                    """
                    INSERT OR REPLACE INTO factor_values
                    (symbol, trade_date, factor_name, factor_value, update_time)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, cached_rows)
                conn.commit()
            except Exception:
                conn.rollback()
            finally:
                conn.close()
    finally:
        try:
            ff.close()
        except Exception:
            pass

    return factor_data


def _run_backtest(config, db_path, progress_callback=None):
    """执行多因子回测（子线程）。返回 results dict 或含 'error' 的 dict。"""
    symbols = config.get("symbols") or []
    if not symbols:
        return {"error": "请先选择股票"}

    if config.get("auto_backfill_to_start"):
        if progress_callback:
            progress_callback(5, "回测前补齐历史数据并写库")
        stats = _backfill_stock_data_to_start_date(db_path, symbols, config["start_date"], config["end_date"])
        config["_backfill_stats"] = stats

    if progress_callback:
        progress_callback(10, "获取股票数据")
    stock_data = _fetch_stock_data(db_path, symbols, config["start_date"], config["end_date"])
    if not stock_data:
        return {"error": "无法获取股票数据"}

    eff_start, eff_end = _compute_effective_backtest_window(
        stock_data, config["start_date"], config["end_date"])
    if eff_start is None or eff_end is None:
        return {"error": "所选股票在指定区间内无共同可回测交易日，请调整股票池或日期范围"}

    wl = WatchlistManager()
    stock_names = {}
    for s in symbols:
        info = wl.get_stock(s)
        stock_names[s] = info.name if (info and info.name) else s

    if progress_callback:
        progress_callback(30, "准备因子数据")
    factor_data = _prepare_factor_data(
        db_path, stock_data, list(config["factor_weights"].keys()),
        progress_callback=progress_callback)
    if not factor_data:
        return {"error": "因子数据准备失败：未生成有效因子面板"}

    warnings = []
    missing_factors = []
    for factor in config["factor_weights"].keys():
        hit = any(factor in df.columns and df[factor].notna().any()
                  for df in factor_data.values())
        if not hit:
            missing_factors.append(factor)
    if missing_factors:
        warnings.append(
            f"以下因子在当前股票池与区间内无有效数据，回测中将被忽略：{', '.join(missing_factors)}")

    run_result = run_multi_factor_strategy_backtest(
        symbols=symbols, db_path=db_path, stock_data=stock_data,
        start_date=eff_start, end_date=eff_end, initial_capital=config["initial_capital"],
        max_positions=config["max_positions"], rebalance_days=config["rebalance_days"],
        factor_weights=config["factor_weights"], use_ic_weighting=config["use_ic_weighting"],
        ic_update_freq=config["ic_update_freq"] or 60, commission_rate=0.0003,
        max_single_position=config.get("max_single_position", 0.2),
        max_total_position=config.get("max_total_position", 0.8),
        stop_loss=config.get("stop_loss", 0.0), factor_data=factor_data,
        progress_callback=progress_callback, stock_names=stock_names,
    )
    if run_result.get("error"):
        run_result.setdefault("warnings", [])
        return run_result

    results = run_result["results"]
    results["requested_window"] = {"start": config["start_date"], "end": config["end_date"]}
    results["effective_window"] = {"start": eff_start, "end": eff_end}
    results.setdefault("warnings", [])
    results["warnings"].extend(warnings)
    return results


# ============ 图表辅助 ============
# 阶段4：原 plotly 版本 _make_equity_figure / _make_exposure_figure /
# _make_attribution_figure / _make_trade_radar_figure 已迁移到 desktop/charts/
# —— equity_chart / exposure_chart / attribution_chart / radar_chart



class FactorBacktestPage(BasePage):
    """多因子回测页"""

    def __init__(self, parent=None):
        self._db_path = Managers.instance().data_manager.db_path
        self._state = AppState.instance()
        self._worker = None
        self._mfbt_results = None
        super().__init__(title="多因子回测", subtitle="统一配置因子、权重与风控参数，快速评估组合策略稳定性", parent=parent)

    # ============ 构建内容 ============

    def _build_content(self):
        self._msg = MessageBar()
        self.content_layout.addWidget(self._msg)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setSizes([420, 680])

        # 左：配置区
        left = QScrollArea()
        left.setWidgetResizable(True)
        left_widget = QWidget()
        self._config_layout = QVBoxLayout(left_widget)
        self._config_layout.setSpacing(12)
        left.setWidget(left_widget)
        self._build_config()
        splitter.addWidget(left)

        # 右：结果区
        self._results_tabs = QTabWidget()
        self._tab_overview = QWidget()
        self._tab_overview.setLayout(QVBoxLayout())
        self._tab_factor = QWidget()
        self._tab_factor.setLayout(QVBoxLayout())
        self._tab_trade = QWidget()
        self._tab_trade.setLayout(QVBoxLayout())
        self._tab_rebalance = QWidget()
        self._tab_rebalance.setLayout(QVBoxLayout())
        self._tab_config = QWidget()
        self._tab_config.setLayout(QVBoxLayout())
        self._results_tabs.addTab(self._tab_overview, "📈 收益概览")
        self._results_tabs.addTab(self._tab_factor, "📊 因子分析")
        self._results_tabs.addTab(self._tab_trade, "📋 交易明细")
        self._results_tabs.addTab(self._tab_rebalance, "🔄 调仓记录")
        self._results_tabs.addTab(self._tab_config, "💾 配置管理")
        splitter.addWidget(self._results_tabs)

        self.content_layout.addWidget(splitter, 1)

        self._render_results_empty()

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ============ 配置区 ============

    def _build_config(self):
        self._config_layout.addWidget(SectionTitle("📋 因子配置", "选择可解释的因子组合并设置加权方式"))

        # 因子分类勾选
        self._factor_checks = {}
        for category, factors in FACTOR_CATEGORIES.items():
            box = QGroupBox(category)
            box.setCheckable(True)
            box.setChecked(True)
            bl = QVBoxLayout(box)
            defaults = [f for f in DEFAULT_FACTORS.get(category, []) if f in factors]
            for fname, fdisplay in factors.items():
                cb = QCheckBox(fdisplay)
                cb.setChecked(fname in defaults)
                cb.stateChanged.connect(self._on_factor_selection_changed)
                self._factor_checks[fname] = cb
                bl.addWidget(cb)
            self._config_layout.addWidget(box)

        # 权重设置模式
        self._config_layout.addWidget(QLabel("权重设置模式"))
        self._weight_mode_group = QButtonGroup(self)
        self._ic_radio = QRadioButton("🤖 IC智能加权")
        self._manual_radio = QRadioButton("✏️ 手动设置权重")
        self._ic_radio.setChecked(True)
        self._weight_mode_group.addButton(self._ic_radio)
        self._weight_mode_group.addButton(self._manual_radio)
        wm = QHBoxLayout()
        wm.addWidget(self._ic_radio)
        wm.addWidget(self._manual_radio)
        self._config_layout.addLayout(wm)
        self._manual_radio.toggled.connect(self._refresh_weight_controls)

        self._weight_container = QWidget()
        self._weight_container.setLayout(QVBoxLayout())
        self._weight_container.layout().setContentsMargins(0, 0, 0, 0)
        self._config_layout.addWidget(self._weight_container)

        # IC 参数
        self._ic_params_widget = QWidget()
        self._ic_params_layout = QFormLayout(self._ic_params_widget)
        self._ic_freq_spin = QSpinBox()
        self._ic_freq_spin.setRange(20, 120)
        self._ic_freq_spin.setSingleStep(10)
        self._ic_freq_spin.setValue(60)
        self._ic_lookback_spin = QSpinBox()
        self._ic_lookback_spin.setRange(60, 252)
        self._ic_lookback_spin.setSingleStep(20)
        self._ic_lookback_spin.setValue(120)
        self._ic_params_layout.addRow("IC更新频率（天）", self._ic_freq_spin)
        self._ic_params_layout.addRow("IC历史窗口（天）", self._ic_lookback_spin)
        self._config_layout.addWidget(self._ic_params_widget)

        # 回测参数
        self._config_layout.addWidget(SectionTitle("⚙️ 回测参数", "设置股票池、资金规模、调仓与风控约束"))
        self._source_combo = QComboBox()
        self._source_combo.addItems(["📈 自选股", "📋 自定义列表"])
        self._source_combo.currentTextChanged.connect(self._on_source_changed)
        self._config_layout.addWidget(self._labeled(self._source_combo, "股票池来源"))
        self._custom_edit = QPlainTextEdit("000001.SZ, 600000.SH, 600519.SH")
        self._custom_edit.setMaximumHeight(70)
        self._custom_widget = self._labeled(self._custom_edit, "股票代码（逗号分隔）")
        self._custom_widget.setVisible(False)
        self._config_layout.addWidget(self._custom_widget)

        dates = QHBoxLayout()
        self._start_edit = QDateEdit(QDate(2023, 1, 1))
        self._start_edit.setCalendarPopup(True)
        self._end_edit = QDateEdit(QDate.currentDate())
        self._end_edit.setCalendarPopup(True)
        dates.addWidget(self._labeled(self._start_edit, "开始日期"))
        dates.addWidget(self._labeled(self._end_edit, "结束日期"))
        self._config_layout.addLayout(dates)

        self._capital_spin = QSpinBox()
        self._capital_spin.setRange(100000, 100000000)
        self._capital_spin.setSingleStep(100000)
        self._capital_spin.setValue(1000000)
        self._config_layout.addWidget(self._labeled(self._capital_spin, "初始资金（元）"))

        pr = QHBoxLayout()
        self._max_pos_spin = QSpinBox()
        self._max_pos_spin.setRange(1, 20)
        self._max_pos_spin.setValue(5)
        self._rebal_spin = QSpinBox()
        self._rebal_spin.setRange(1, 60)
        self._rebal_spin.setValue(5)
        pr.addWidget(self._labeled(self._max_pos_spin, "最大持仓数"))
        pr.addWidget(self._labeled(self._rebal_spin, "调仓周期（天）"))
        self._config_layout.addLayout(pr)

        self._pos_method_combo = QComboBox()
        for val, disp in POSITION_METHODS:
            self._pos_method_combo.addItem(disp, val)
        self._pos_method_combo.setCurrentIndex(0)
        self._config_layout.addWidget(self._labeled(self._pos_method_combo, "仓位分配方法"))

        # 风控
        self._config_layout.addWidget(QLabel("🛡️ 风控参数"))
        risk = QHBoxLayout()
        self._stop_spin = QSpinBox()
        self._stop_spin.setRange(0, 30)
        self._stop_spin.setValue(10)
        self._maxsingle_spin = QSpinBox()
        self._maxsingle_spin.setRange(10, 50)
        self._maxsingle_spin.setValue(20)
        risk.addWidget(self._labeled(self._stop_spin, "止损比例（%）"))
        risk.addWidget(self._labeled(self._maxsingle_spin, "单一持仓上限（%）"))
        self._config_layout.addLayout(risk)

        # 执行
        self._config_layout.addWidget(SectionTitle("🚀 执行回测", "检查参数后启动策略回放"))
        self._backfill_check = QCheckBox("回测前自动补齐历史行情到开始日期（会写入数据库）")
        self._backfill_check.setChecked(True)
        self._config_layout.addWidget(self._backfill_check)

        run_row = QHBoxLayout()
        self._run_btn = QPushButton("▶️ 开始回测")
        self._run_btn.clicked.connect(self._on_run)
        self._stop_btn = QPushButton("⏹️ 中断")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        run_row.addWidget(self._run_btn)
        run_row.addWidget(self._stop_btn)
        self._config_layout.addLayout(run_row)

        self._progress = QProgressBar()
        self._progress.setValue(0)
        self._config_layout.addWidget(self._progress)
        self._status_label = QLabel("")
        self._config_layout.addWidget(self._status_label)

        self._refresh_weight_controls()

    @staticmethod
    def _labeled(widget, text):
        """把控件包上一行标签，返回 QWidget（可直接 addWidget / setVisible）。"""
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        label = QLabel(text)
        label.setMinimumWidth(96)
        h.addWidget(label)
        h.addWidget(widget, 1)
        return box

    # ============ 配置交互 ============

    def _on_source_changed(self, text):
        self._custom_widget.setVisible(text == "📋 自定义列表")

    def _on_factor_selection_changed(self):
        self._refresh_weight_controls()

    def _selected_factors(self):
        return [f for f, cb in self._factor_checks.items() if cb.isChecked()]

    def _refresh_weight_controls(self):
        layout = self._weight_container.layout()
        self._clear_layout(layout)
        self._weight_spins = {}
        selected = self._selected_factors()
        if not selected:
            layout.addWidget(QLabel("请至少选择一个因子"))
            return
        if self._manual_radio.isChecked():
            equal_w = round(1.0 / len(selected), 4)
            for f in selected:
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 1.0)
                spin.setDecimals(4)
                spin.setSingleStep(0.05)
                spin.setValue(equal_w)
                spin.valueChanged.connect(self._update_weight_sum_label)
                self._weight_spins[f] = spin
                layout.addWidget(self._labeled(spin, f))
            norm_btn = QPushButton("🔄 归一化")
            norm_btn.clicked.connect(self._on_normalize_weights)
            layout.addWidget(norm_btn)
            self._weight_sum_label = QLabel()
            layout.addWidget(self._weight_sum_label)
            # 修正等权舍入残差，让初始总和精确为 1
            spins = list(self._weight_spins.values())
            spins[-1].setValue(round(1.0 - equal_w * (len(spins) - 1), 4))
            self._update_weight_sum_label()
        else:
            # IC 模式：等权基础权重展示
            layout.addWidget(QLabel("IC智能加权：根据因子历史表现动态调整权重（等权基础）"))
            self._ic_params_widget.setVisible(True)

    def _update_weight_sum_label(self):
        label = getattr(self, "_weight_sum_label", None)
        if label is None or not self._weight_spins:
            return
        total = sum(s.value() for s in self._weight_spins.values())
        if abs(total - 1.0) < 1e-6:
            label.setText(f"权重总和：{total:.4f} ✅")
            label.setStyleSheet("color: #16a34a;")
        else:
            label.setText(f"权重总和：{total:.4f}（运行时将自动归一化为 1）")
            label.setStyleSheet("color: #d97706;")

    def _on_normalize_weights(self):
        if not self._weight_spins:
            return
        total = sum(s.value() for s in self._weight_spins.values())
        if total <= 0:
            return
        spins = list(self._weight_spins.values())
        # 先按比例分配，再把小数舍入的残差补到最后一项，确保总和精确为 1
        acc = 0.0
        for s in spins[:-1]:
            v = round(s.value() / total, 4)
            s.setValue(v)
            acc += v
        spins[-1].setValue(round(max(0.0, 1.0 - acc), 4))
        self._update_weight_sum_label()

    def _build_config_dict(self):
        selected = self._selected_factors()
        if self._manual_radio.isChecked():
            factor_weights = {f: self._weight_spins[f].value()
                              for f in selected if f in self._weight_spins}
            # 二次归一化：无论界面上填了什么，传给引擎的权重恒为 1
            total = sum(factor_weights.values())
            if total > 0:
                factor_weights = {f: w / total for f, w in factor_weights.items()}
            use_ic = False
        else:
            factor_weights = {f: 1.0 / len(selected) if selected else 0 for f in selected}
            use_ic = True

        if self._source_combo.currentText() == "📈 自选股":
            wl = WatchlistManager()
            symbols = [s.symbol for s in filter_out_benchmark_stocks(wl.get_all_stocks())]
        else:
            raw = self._custom_edit.toPlainText()
            symbols = [s.strip() for s in raw.split(",") if s.strip()]
            symbols = filter_out_benchmark_symbols(symbols)

        return {
            "factor_weights": factor_weights,
            "use_ic_weighting": use_ic,
            "ic_update_freq": self._ic_freq_spin.value(),
            "ic_lookback": self._ic_lookback_spin.value(),
            "symbols": symbols,
            "start_date": self._start_edit.date().toString("yyyy-MM-dd"),
            "end_date": self._end_edit.date().toString("yyyy-MM-dd"),
            "initial_capital": self._capital_spin.value(),
            "max_positions": self._max_pos_spin.value(),
            "rebalance_days": self._rebal_spin.value(),
            "position_method": self._pos_method_combo.currentData(),
            "stop_loss": self._stop_spin.value() / 100.0,
            "max_single_position": self._maxsingle_spin.value() / 100.0,
            "max_total_position": 0.8,
            "auto_backfill_to_start": self._backfill_check.isChecked(),
        }

    # ============ 执行 ============

    def _on_run(self):
        config = self._build_config_dict()
        if not config["symbols"]:
            self._msg.warning("请先选择股票（自选股为空或自定义列表为空）")
            return
        if not config["factor_weights"]:
            self._msg.warning("请至少选择一个因子")
            return
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._progress.setValue(0)
        self._status_label.setText("正在运行回测，请稍候...")
        self._config = config
        worker = run_with_progress(
            self, _run_backtest, config, self._db_path,
            title="多因子回测", message="准备数据中...", cancelable=True,
        )
        self._worker = worker
        worker.finished.connect(self._on_backtest_finished)
        worker.error.connect(self._on_backtest_error)
        # 进度：ProgressWorker 的进度信号接到进度条
        worker.progress.connect(lambda p, m: (self._progress.setValue(p), self._status_label.setText(m)))

    def _on_stop(self):
        if self._worker is not None:
            self._worker.cancel()
            self._status_label.setText("已请求中断...")

    def _on_backtest_finished(self, results):
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._worker = None
        if isinstance(results, dict) and results.get("error"):
            self._msg.error(f"回测失败: {results['error']}")
            for w in results.get("warnings", []) or []:
                self._msg.warning(w)
            return
        self._mfbt_results = results
        self._state.mfbt_results = results
        self._state.is_multi_factor_backtest = True
        self._state.multi_backtest_results = results
        self._msg.success("✅ 回测完成！")
        for w in results.get("warnings", []) or []:
            self._msg.warning(w)
        self._render_results(results)

    def _on_backtest_error(self, err):
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._worker = None
        self._msg.error(f"回测出错: {err}")

    # ============ 结果渲染 ============

    def _render_results_empty(self):
        for tab in (self._tab_overview, self._tab_factor, self._tab_trade, self._tab_rebalance, self._tab_config):
            self._clear_layout(tab.layout())
            tab.layout().addWidget(QLabel("👈 请在左侧配置参数后点击「开始回测」"))

    def _render_results(self, results):
        self._render_overview(results)
        self._render_factor_analysis(results)
        self._render_trade_details(results)
        self._render_rebalance_history(results)
        self._render_config_management(results)

    def _render_overview(self, results):
        layout = self._tab_overview.layout()
        self._clear_layout(layout)

        row = QHBoxLayout()
        row.setSpacing(12)
        cards = [
            MetricCard("总收益率", f"{results.get('total_return', 0):.2%}"),
            MetricCard("年化收益率", f"{results.get('annual_return', 0):.2%}"),
            MetricCard("夏普比率", f"{results.get('sharpe_ratio', 0):.2f}"),
            MetricCard("最大回撤", f"{results.get('max_drawdown', 0):.2%}"),
            MetricCard("波动率", f"{results.get('volatility', 0):.2%}"),
        ]
        for c in cards:
            row.addWidget(c)
        layout.addLayout(row)

        # 首笔买入诊断
        backtest_dates = results.get("dates", {}) or {}
        backtest_start = str(backtest_dates.get("start", ""))[:10]
        first_buy = results.get("first_buy_date")
        pre_buy = results.get("pre_first_buy_diagnostics", []) or []
        if first_buy and backtest_start and first_buy > backtest_start:
            layout.addWidget(QLabel(f"首笔买入发生在 {first_buy}，晚于回测起始 {backtest_start}。"))
        elif not first_buy and pre_buy:
            layout.addWidget(QLabel("⚠️ 本次回测未发生买入，已记录调仓诊断。"))

        if pre_buy:
            box = QGroupBox("🔍 首笔买入前空仓诊断")
            bl = QVBoxLayout(box)
            df = pd.DataFrame(pre_buy)
            tbl = PandasTableView()
            tbl.set_dataframe(df)
            bl.addWidget(tbl)
            layout.addWidget(box)

        # 权益曲线
        layout.addWidget(QLabel("权益曲线"))
        chart = ChartContainer(title="权益曲线")
        chart.setMinimumHeight(360)
        equity = results.get("equity_curve")
        if equity is not None and not equity.empty:
            from desktop.charts.equity_chart import build_equity_widget
            chart.set_plot_widget(build_equity_widget(equity, height=360))
        else:
            chart.set_message("无权益曲线数据")
        layout.addWidget(chart)

        # 月度收益
        layout.addWidget(QLabel("月度收益统计"))
        monthly = results.get("monthly_returns")
        if monthly is not None and not monthly.empty:
            mt = PandasTableView()
            if "收益率" in monthly.columns:
                mt.set_dataframe(monthly, color_rules={"收益率": make_change_color_rule()})
            else:
                mt.set_dataframe(monthly)
            layout.addWidget(mt)
        else:
            layout.addWidget(QLabel("无月度收益数据"))

    def _render_factor_analysis(self, results):
        layout = self._tab_factor.layout()
        self._clear_layout(layout)
        layout.addWidget(SectionTitle("🧪 因子分析", "追踪权重变化、有效性和收益归因"))
        report = results.get("factor_report", {}) or {}

        fw = report.get("factor_weights", {}) or {}
        icw = report.get("ic_weights", {}) or {}
        weight_data = []
        for f in fw:
            weight_data.append({
                "因子": f,
                "基础权重": f"{fw[f]:.1%}",
                "IC权重": f"{icw.get(f, 0):.1%}",
                "变化": f"{icw.get(f, 0) - fw[f]:+.1%}",
            })
        if weight_data:
            layout.addWidget(QLabel("权重对比"))
            wt = PandasTableView()
            wt.set_dataframe(pd.DataFrame(weight_data))
            layout.addWidget(wt)

        icv = report.get("ic_validity_report", {}) or {}
        validity_data = []
        for f, stats in icv.items():
            validity_data.append({
                "因子": f,
                "IC均值": f"{stats.get('ic_mean', 0):.3f}",
                "IR": f"{stats.get('ir', 0):.2f}",
                "判定": f"{IC_VALIDITY_ICONS.get(stats.get('validity', 'invalid'), '⚪')} {stats.get('validity', 'unknown')}",
            })
        if validity_data:
            layout.addWidget(QLabel("IC 有效性判定"))
            vt = PandasTableView()
            vt.set_dataframe(pd.DataFrame(validity_data))
            layout.addWidget(vt)

        exposure = report.get("exposure_timeseries")
        if exposure is not None and not exposure.empty:
            layout.addWidget(QLabel("因子暴露度时序"))
            ec = ChartContainer(title="因子暴露度")
            ec.setMinimumHeight(360)
            from desktop.charts.exposure_chart import build_exposure_widget
            ec.set_plot_widget(build_exposure_widget(exposure))
            layout.addWidget(ec)

        attribution = report.get("attribution", {}) or {}
        if attribution:
            layout.addWidget(QLabel("因子收益归因"))
            ac = ChartContainer(title="因子收益归因")
            ac.setMinimumHeight(320)
            from desktop.charts.attribution_chart import build_attribution_widget
            ac.set_plot_widget(build_attribution_widget(attribution))
            layout.addWidget(ac)

    def _render_trade_details(self, results):
        layout = self._tab_trade.layout()
        self._clear_layout(layout)
        layout.addWidget(SectionTitle("📋 交易明细", "支持筛选交易记录并查看因子得分"))
        trade_details = results.get("trade_details")
        if trade_details is None or trade_details.empty:
            layout.addWidget(QLabel("无交易明细数据"))
            return

        self._trade_results = results
        factor_names = results.get("factor_names", []) or []

        ctrl = QHBoxLayout()
        self._trade_symbol_list = QListWidget()
        self._trade_symbol_list.setSelectionMode(QListWidget.MultiSelection)
        if "股票" in trade_details.columns:
            for s in trade_details["股票"].unique():
                self._trade_symbol_list.addItem(str(s))
        self._trade_symbol_list.setMaximumHeight(90)
        ctrl.addWidget(self._labeled(self._trade_symbol_list, "股票筛选"))
        self._trade_status_combo = QComboBox()
        self._trade_status_combo.addItems(["全部", "已卖出", "持有中"])
        self._trade_status_combo.currentTextChanged.connect(self._on_trade_filter_changed)
        self._trade_symbol_list.itemSelectionChanged.connect(self._on_trade_filter_changed)
        ctrl.addWidget(self._labeled(self._trade_status_combo, "状态筛选"))
        self._trade_show_factor = QCheckBox("显示因子得分列")
        self._trade_show_factor.stateChanged.connect(self._on_trade_filter_changed)
        ctrl.addWidget(self._trade_show_factor)
        layout.addLayout(ctrl)

        self._trade_table_container = QWidget()
        self._trade_table_container.setLayout(QVBoxLayout())
        self._trade_table_container.layout().setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._trade_table_container)

        self._trade_radar_container = QWidget()
        self._trade_radar_container.setLayout(QVBoxLayout())
        self._trade_radar_container.layout().setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._trade_radar_container)

        self._on_trade_filter_changed()

    def _on_trade_filter_changed(self):
        if not hasattr(self, "_trade_results"):
            return
        results = self._trade_results
        trade_details = results.get("trade_details")
        factor_names = results.get("factor_names", []) or []
        show_factors = self._trade_show_factor.isChecked()

        filtered = trade_details.copy()
        sel_items = [self._trade_symbol_list.item(i).text() for i in range(self._trade_symbol_list.count())
                     if self._trade_symbol_list.item(i).isSelected()]
        if sel_items:
            filtered = filtered[filtered["股票"].isin(sel_items)]
        status = self._trade_status_combo.currentText()
        if status == "已卖出":
            filtered = filtered[filtered.get("状态", "") == "已卖出"]
        elif status == "持有中":
            filtered = filtered[filtered.get("状态", "") == "持有中"]

        # 统计
        stat = QHBoxLayout()
        stat.setSpacing(12)
        for c in [
            MetricCard("总交易次数", str(len(filtered))),
            MetricCard("已卖出次数", str(len(filtered[filtered.get("状态", "") == "已卖出"]))),
            MetricCard("持有中次数", str(len(filtered[filtered.get("状态", "") == "持有中"]))),
        ]:
            stat.addWidget(c)
        if "持有天数" in filtered.columns:
            avg = filtered["持有天数"].mean()
            stat.addWidget(MetricCard("平均持有天数", str(int(round(avg)))))

        base_cols = ["股票", "买入日期", "买入价格（元）", "买入数量", "买入金额（元）",
                     "卖出日期", "卖出价格（元）", "收益率（%）", "净收益率（%）", "收益金额（元）",
                     "持有天数", "状态", "卖出原因"]
        factor_cols = []
        if show_factors and factor_names:
            for f in factor_names:
                if f"{f}_得分" in filtered.columns:
                    factor_cols.append(f"{f}_得分")
            if "综合得分" in filtered.columns:
                factor_cols.append("综合得分")
            if "排名" in filtered.columns:
                factor_cols.append("排名")
        display_cols = [c for c in base_cols + factor_cols if c in filtered.columns]

        self._clear_layout(self._trade_table_container.layout())
        self._trade_table_container.layout().addLayout(stat)
        if display_cols:
            tbl = PandasTableView()
            tbl.set_dataframe(
                filtered[display_cols],
                formatters={"收益率（%）": "{:+.2f}", "收益金额（元）": "{:.2f}", "净收益率（%）": "{:+.2f}"},
                color_rules={"收益率（%）": make_change_color_rule(), "收益金额（元）": make_change_color_rule()},
            )
            self._trade_table_container.layout().addWidget(tbl)

        # 雷达图
        self._clear_layout(self._trade_radar_container.layout())
        if show_factors and factor_names and not filtered.empty and "交易ID" in filtered.columns:
            self._trade_radar_container.layout().addWidget(QLabel("交易因子详情"))
            rid_combo = QComboBox()
            for rid in filtered["交易ID"].tolist():
                rid_combo.addItem(str(rid))
            self._trade_radar_container.layout().addWidget(rid_combo)
            row_data = filtered[filtered["交易ID"] == filtered["交易ID"].iloc[0]].iloc[0]

            def _update_radar(idx_text):
                r = filtered[filtered["交易ID"] == idx_text]
                if not r.empty:
                    self._draw_radar(r.iloc[0], factor_names)

            rid_combo.currentTextChanged.connect(_update_radar)
            self._draw_radar(filtered.iloc[0], factor_names)

    def _draw_radar(self, row, factor_names):
        # 简单重绘：直接在此容器内重建
        self._clear_layout(self._trade_radar_container.layout())
        container = QWidget()
        cl = QVBoxLayout(container)
        # 收集有效因子
        theta, r = [], []
        for f in factor_names:
            col = f"{f}_得分"
            if col in row and pd.notna(row[col]):
                theta.append(f)
                r.append(float(row[col]))
        if len(theta) < 3:
            cl.addWidget(QLabel("因子数据不足，无法绘制雷达图"))
        else:
            from desktop.charts.radar_chart import build_radar_widget
            chart = ChartContainer(title="因子得分雷达图")
            chart.setMinimumHeight(360)
            chart.set_plot_widget(build_radar_widget(theta, r, value_max=100))
            cl.addWidget(chart)
        self._trade_radar_container.layout().addWidget(container)

    def _render_rebalance_history(self, results):
        layout = self._tab_rebalance.layout()
        self._clear_layout(layout)
        layout.addWidget(SectionTitle("🔄 调仓记录", "按调仓日复盘买卖逻辑与候选池变化"))
        snapshots = results.get("rebalance_snapshots", []) or []
        factor_names = results.get("factor_names", []) or []
        if not snapshots:
            layout.addWidget(QLabel("无调仓记录数据"))
            return

        layout.addWidget(QLabel(f"调仓概览（共 {len(snapshots)} 次）"))
        overview = pd.DataFrame([{
            "调仓日期": s.date,
            "买入股票数": len(s.selected_symbols),
            "卖出股票数": len(s.sold_symbols),
            "候选股票数": len(s.all_scores),
        } for s in snapshots])
        ov = PandasTableView()
        ov.set_dataframe(overview)
        layout.addWidget(ov)

        layout.addWidget(QLabel("单次调仓详情"))
        self._rebal_combo = QComboBox()
        for s in snapshots:
            self._rebal_combo.addItem(s.date)
        self._rebal_detail_container = QWidget()
        self._rebal_detail_container.setLayout(QVBoxLayout())
        self._rebal_detail_container.layout().setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._rebal_combo)
        layout.addWidget(self._rebal_detail_container)

        def _on_rebal(date):
            self._render_rebalance_detail(snapshots, factor_names, date)

        self._rebal_combo.currentTextChanged.connect(_on_rebal)
        self._render_rebalance_detail(snapshots, factor_names, snapshots[0].date)

    def _render_rebalance_detail(self, snapshots, factor_names, date):
        snapshot = next((s for s in snapshots if s.date == date), None)
        if snapshot is None:
            return
        self._clear_layout(self._rebal_detail_container.layout())
        bl = self._rebal_detail_container.layout()
        buy_box = QGroupBox("买入股票")
        bbl = QVBoxLayout(buy_box)
        for sym in snapshot.selected_symbols:
            score = snapshot.all_scores.get(sym, 0)
            bbl.addWidget(QLabel(f"{sym} 综合得分: {score:.1f}"))
        bl.addWidget(buy_box)
        sell_box = QGroupBox("卖出股票")
        sbl = QVBoxLayout(sell_box)
        for sym in snapshot.sold_symbols:
            sbl.addWidget(QLabel(sym))
        bl.addWidget(sell_box)

        if snapshot.all_scores:
            panel = []
            for symbol in sorted(snapshot.all_scores.keys(), key=lambda x: snapshot.all_scores.get(x, 0), reverse=True):
                row = {"股票": symbol, "综合得分": round(snapshot.all_scores.get(symbol, 0), 1)}
                vals = snapshot.all_factor_values.get(symbol, {}) or {}
                for f in factor_names:
                    if f in vals:
                        row[f] = round(vals[f], 4) if isinstance(vals[f], float) else vals[f]
                percs = snapshot.all_factor_percentiles.get(symbol, {}) or {}
                for f in factor_names:
                    if f in percs:
                        row[f"{f}_得分"] = round(percs[f], 1)
                row["是否买入"] = "是" if symbol in snapshot.selected_symbols else "否"
                row["是否卖出"] = "是" if symbol in snapshot.sold_symbols else "否"
                panel.append(row)
            pdf = pd.DataFrame(panel)
            pt = PandasTableView()
            pt.set_dataframe(pdf)
            bl.addWidget(QLabel("当日全部候选股票因子面板"))
            bl.addWidget(pt)

            score_cols = [f"{f}_得分" for f in factor_names if f"{f}_得分" in pdf.columns]
            if score_cols:
                from desktop.charts.heatmap_chart import build_heatmap_widget
                from PySide6.QtGui import QColor
                heat = pdf[["股票"] + score_cols].set_index("股票")
                text_arr = heat.values.astype(str)
                # 把每格数值格式化成整数
                import numpy as _np
                text_arr = _np.where(_np.isfinite(heat.values),
                                     _np.round(heat.values).astype(int).astype(str),
                                     "")
                hc = ChartContainer(title="因子得分热力图")
                hc.setMinimumHeight(max(300, len(heat) * 25 + 100))
                hc.set_plot_widget(build_heatmap_widget(
                    heat.values,
                    list(heat.columns),
                    list(heat.index),
                    color_stops=[
                        (0.0, QColor("#dc2626")),    # 低分：红
                        (0.5, QColor("#fbbf24")),    # 中分：黄
                        (1.0, QColor("#16a34a")),    # 高分：绿
                    ],
                    zmin=0, zmax=100,
                    text=text_arr,
                    title="因子得分",
                    height=max(300, len(heat) * 25 + 100),
                    x_label="因子", y_label="股票",
                ))
                bl.addWidget(hc)

    def _render_config_management(self, results):
        layout = self._tab_config.layout()
        self._clear_layout(layout)
        layout.addWidget(SectionTitle("💾 配置管理", "保存策略参数并管理回测输出"))

        cfg = self._config if hasattr(self, "_config") else {}
        info = QFormLayout()
        info.addRow("因子数", QLabel(str(len(cfg.get("factor_weights", {})))))
        info.addRow("股票数", QLabel(str(len(cfg.get("symbols", [])))))
        info.addRow("回测区间", QLabel(f"{cfg.get('start_date','')} ~ {cfg.get('end_date','')}"))
        info.addRow("初始资金", QLabel(str(cfg.get("initial_capital", ""))))
        info.addRow("权重模式", QLabel("IC智能加权" if cfg.get("use_ic_weighting") else "手动权重"))
        layout.addLayout(info)

        hist = results.get("history")
        if hist:
            layout.addWidget(QLabel("历史回测记录"))
            ht = PandasTableView()
            ht.set_dataframe(pd.DataFrame(hist))
            layout.addWidget(ht)

        layout.addWidget(QLabel("导出报告"))
        exp = QHBoxLayout()
        excel_btn = QPushButton("📊 导出CSV")
        excel_btn.clicked.connect(self._on_export_csv)
        pdf_btn = QPushButton("📑 导出PDF（开发中）")
        pdf_btn.setEnabled(False)
        exp.addWidget(excel_btn)
        exp.addWidget(pdf_btn)
        layout.addLayout(exp)

    def _on_export_csv(self):
        from PySide6.QtWidgets import QFileDialog
        if not self._mfbt_results:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出回测结果CSV", "mfbt_results.csv", "CSV (*.csv)")
        if not path:
            return
        out = {}
        if self._mfbt_results.get("trade_details") is not None:
            out["trade_details"] = self._mfbt_results["trade_details"]
        if self._mfbt_results.get("equity_curve") is not None:
            out["equity_curve"] = self._mfbt_results["equity_curve"]
        if not out:
            self._msg.warning("无可导出的结果数据")
            return
        base = path.rsplit(".", 1)[0]
        try:
            for name, df in out.items():
                df.to_csv(f"{base}_{name}.csv", encoding="utf-8-sig", index=False)
            self._msg.success(f"已导出至 {base}_*.csv")
        except Exception as e:
            self._msg.error(f"导出失败: {e}")

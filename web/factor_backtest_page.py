"""
因子回测页面
多因子策略回测的 Web 界面
"""
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# 导入后端模块
from data.data_manager import DataManager
from data.data_provider import CacheOnlyProvider
from strategy.fundamental_factors import FundamentalFactors
from portfolio.watchlist import filter_out_benchmark_stocks, filter_out_benchmark_symbols
from web.services.backtest_service import run_multi_factor_strategy_backtest


# =============================================================================
# 因子分类定义
# =============================================================================

FACTOR_CATEGORIES = {
    "基本面因子": {
        "roe": "ROE（净资产收益率）",
        "roe_avg": "净资产收益率(平均)",
        "roa": "ROA（资产收益率）",
        "gross_margin": "毛利率",
        "net_margin": "净利率",
        "np_margin": "销售净利率(npMargin)",
        "gp_margin": "销售毛利率(gpMargin)",
        "eps": "EPS（每股收益）",
        "eps_ttm": "epsTTM（每股收益TTM）",
        "net_profit": "netProfit（净利润）",
        "mb_revenue": "MBRevenue（主营业务收入）",
        "total_share": "totalShare（总股本）",
        "liqa_share": "liqaShare（流通股本）",
        "revenue_growth": "营收增长率",
        "profit_growth": "利润增长率",
        "asset_turnover": "资产周转率"
    },
    "估值因子": {
        "pe": "PE（市盈率）",
        "pb": "PB（市净率）",
        "ps": "PS（市销率）",
        "pcf": "PCF（现金流倍率）"
    },
    "技术因子": {
        "momentum_20": "20日动量",
        "momentum_60": "60日动量",
        "volatility_20": "20日波动率",
        "volume_ratio": "量比",
        "turnover_rate": "换手率"
    },
    "财务结构": {
        "debt_ratio": "资产负债率",
        "current_ratio": "流动比率",
        "quick_ratio": "速动比率"
    },
    "情绪因子": {
        "price_volume_trend": "价量趋势",
        "relative_strength": "相对强弱"
    }
}

# 默认因子配置
DEFAULT_FACTORS = {
    "基本面因子": ["roe", "revenue_growth"],
    "估值因子": ["pe", "pb"],
    "技术因子": ["momentum_20"],
    "财务结构": ["debt_ratio"],
    "情绪因子": ["turnover_rate"]
}


# =============================================================================
# 页面渲染函数
# =============================================================================

def _render_page_title():
    """渲染页面标题"""
    st.markdown(
        """
        <div class="section-title">
            <div class="main">📊 多因子回测</div>
            <div class="desc">统一配置因子、权重与风控参数，快速评估组合策略稳定性</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def _render_subsection_title(title: str, icon: str = "📌", desc: str = ""):
    """渲染子分区标题"""
    subtitle = f'<div class="desc">{desc}</div>' if desc else ""
    st.markdown(
        f"""
        <div class="section-title" style="margin-top: 0;">
            <div class="main">{icon} {title}</div>
            {subtitle}
        </div>
        """,
        unsafe_allow_html=True
    )

def render_factor_backtest_page(dm: DataManager, wl_manager):
    """
    渲染因子回测页面

    Args:
        dm: DataManager 实例
        wl_manager: WatchlistManager 实例
    """
    _render_page_title()

    # 初始化 session state
    _init_session_state()

    # 主内容区（因子配置 + 回测结果）
    config = _render_sidebar_config(dm, wl_manager)
    _render_main_content(dm, wl_manager, config)


def _init_session_state():
    """初始化 session state"""
    if 'mfbt_results' not in st.session_state:
        st.session_state.mfbt_results = None
    if 'mfbt_progress' not in st.session_state:
        st.session_state.mfbt_progress = 0
    if 'mfbt_status' not in st.session_state:
        st.session_state.mfbt_status = ""


# =============================================================================
# 侧边栏配置
# =============================================================================

def _render_sidebar_config(dm: DataManager, wl_manager) -> Dict[str, Any]:
    """
    渲染侧边栏配置

    Returns:
        配置字典
    """
    _render_subsection_title("因子配置", "📋", "选择可解释的因子组合并设置加权方式")

    # ---------- 因子选择 ----------
    selected_factors = {}
    factor_expanders = st.session_state.get('mfbt_factor_expanders', {})

    for category, factors in FACTOR_CATEGORIES.items():
        expanded = factor_expanders.get(category, True)
        with st.expander(f"☑️ {category}", expanded=expanded):
            # 默认选中的因子
            default_selected = list(DEFAULT_FACTORS.get(category, []))
            # 确保默认选项在可用因子中
            default_selected = [f for f in default_selected if f in factors]

            selected = st.multiselect(
                "选择因子",
                list(factors.keys()),
                default=default_selected,
                format_func=lambda x: factors[x],
                key=f"mfbt_factor_{category}"
            )
            for f in selected:
                selected_factors[f] = category

    # 保存 expander 状态
    if st.button("保存因子展开状态", key="mfbt_save_expanders"):
        st.session_state.mfbt_factor_expanders = factor_expanders

    # ---------- 权重设置模式 ----------
    st.markdown("---")
    weight_mode = st.radio(
        "权重设置模式",
        ["🤖 IC智能加权", "✏️ 手动设置权重"],
        index=0,
        help="IC智能加权：根据因子历史IC表现自动调整权重"
    )

    factor_weights = {}
    if weight_mode == "✏️ 手动设置权重":
        st.markdown("**因子权重（拖动调整）**")

        # 为每个因子显示滑块
        for factor in selected_factors:
            category = selected_factors[factor]
            factor_display = FACTOR_CATEGORIES[category].get(factor, factor)
            w = st.slider(
                factor_display,
                0.0, 1.0, 0.2, 0.05,
                key=f"mfbt_weight_{factor}"
            )
            factor_weights[factor] = w

        # 归一化按钮和显示
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 归一化", use_container_width=True):
                if sum(factor_weights.values()) > 0:
                    factor_weights = {k: v/sum(factor_weights.values()) for k, v in factor_weights.items()}
                    st.success("权重已归一化")
                    # 更新 session state 中的值
                    for k, v in factor_weights.items():
                        st.session_state[f"mfbt_weight_{k}"] = v

        total_weight = sum(factor_weights.values())
        st.caption(f"当前权重总和: {total_weight:.2%}")
    else:
        # IC 加权模式参数
        st.markdown("**IC 加权参数**")
        ic_update_freq = st.slider(
            "IC更新频率（天）",
            20, 120, 60, 10,
            key="mfbt_ic_update_freq"
        )
        ic_lookback = st.slider(
            "IC历史窗口（天）",
            60, 252, 120, 20,
            key="mfbt_ic_lookback"
        )
        st.caption("IC智能加权将根据因子历史表现动态调整权重")

        # 从 selected_factors 生成等权基础权重
        factor_weights = {f: 1.0/len(selected_factors) if selected_factors else 0 for f in selected_factors}

    # ---------- 回测参数 ----------
    st.markdown("---")
    _render_subsection_title("回测参数", "⚙️", "设置股票池、资金规模、调仓与风控约束")

    # 股票池来源
    stock_source = st.selectbox(
        "股票池来源",
        ["📈 自选股", "📋 自定义列表"],
        index=0,
        key="mfbt_stock_source"
    )

    symbols = []
    if stock_source == "📈 自选股":
        watchlist_stocks = filter_out_benchmark_stocks(wl_manager.get_all_stocks())
        if watchlist_stocks:
            symbols = [s.symbol for s in watchlist_stocks]
            st.caption(f"将使用 {len(symbols)} 只自选股")
        else:
            st.warning("自选股为空（默认指数已自动排除），请先添加股票")
    else:
        stock_list_input = st.text_area(
            "股票代码（逗号分隔）",
            "000001.SZ, 600000.SH, 600519.SH",
            height=80,
            key="mfbt_stock_list"
        )
        symbols = [s.strip() for s in stock_list_input.split(",") if s.strip()]
        symbols = filter_out_benchmark_symbols(symbols)

    # 回测期间
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "开始日期",
            datetime(2023, 1, 1),
            key="mfbt_start_date"
        )
    with col2:
        end_date = st.date_input(
            "结束日期",
            datetime.now().date(),
            key="mfbt_end_date"
        )

    # 资金参数
    initial_capital = st.number_input(
        "初始资金（元）",
        min_value=100000,
        max_value=100000000,
        value=1000000,
        step=100000,
        format="%d",
        key="mfbt_initial_capital"
    )

    col1, col2 = st.columns(2)
    with col1:
        max_positions = st.number_input(
            "最大持仓数",
            1, 20, 5,
            key="mfbt_max_positions"
        )
    with col2:
        rebalance_days = st.number_input(
            "调仓周期（天）",
            1, 60, 5,
            key="mfbt_rebalance_days"
        )

    # 仓位分配方法
    position_method = st.selectbox(
        "仓位分配方法",
        ["equal", "factor_weighted", "risk_parity"],
        index=0,
        format_func=lambda x: {
            "equal": "等权分配",
            "factor_weighted": "因子加权",
            "risk_parity": "风险平价"
        }[x],
        key="mfbt_position_method"
    )

    # 风控参数
    st.markdown("**🛡️ 风控参数**")
    col1, col2 = st.columns(2)
    with col1:
        stop_loss = st.slider(
            "止损比例（%）",
            0, 30, 10, 1,
            key="mfbt_stop_loss"
        ) / 100
    with col2:
        max_single_position = st.slider(
            "单一持仓上限（%）",
            10, 50, 20, 5,
            key="mfbt_max_single"
        ) / 100

    # ---------- 执行按钮 ----------
    st.markdown("---")
    _render_subsection_title("执行回测", "🚀", "检查参数后启动策略回放")

    auto_backfill_to_start = st.checkbox(
        "回测前自动补齐历史行情到开始日期（会写入数据库）",
        value=True,
        key="mfbt_auto_backfill_to_start",
        help="开启后将对股票池尝试在线补数并写入数据库，再开始回测。"
    )

    col1, col2 = st.columns(2)
    with col1:
        run_button = st.button(
            "▶️ 开始回测",
            type="primary",
            use_container_width=True,
            key="mfbt_run_button"
        )
    with col2:
        stop_button = st.button(
            "⏹️ 中断",
            use_container_width=True,
            key="mfbt_stop_button"
        )

    # 进度显示
    progress_bar = st.progress(st.session_state.mfbt_progress)
    status_text = st.empty()

    # 构建配置字典
    config = {
        'factor_weights': factor_weights,
        'weight_mode': weight_mode,
        'use_ic_weighting': (weight_mode == "🤖 IC智能加权"),
        'ic_update_freq': ic_update_freq if weight_mode == "🤖 IC智能加权" else None,
        'ic_lookback': ic_lookback if weight_mode == "🤖 IC智能加权" else None,
        'stock_source': stock_source,
        'symbols': symbols,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'initial_capital': initial_capital,
        'max_positions': max_positions,
        'rebalance_days': rebalance_days,
        'position_method': position_method,
        'stop_loss': stop_loss,
        'max_single_position': max_single_position,
        'auto_backfill_to_start': auto_backfill_to_start,
        'run_button': run_button,
        'stop_button': stop_button,
        'progress_bar': progress_bar,
        'status_text': status_text
    }

    return config


# =============================================================================
# 主内容区
# =============================================================================

def _render_main_content(dm: DataManager, wl_manager, config: Dict[str, Any]):
    """渲染主内容区"""

    # 处理回测执行
    if config['run_button']:
        _execute_backtest(dm, wl_manager, config)

    # 处理中断
    if config['stop_button']:
        st.session_state.mfbt_running = False
        st.warning("回测已中断")

    # 结果展示
    if st.session_state.mfbt_results:
        _render_results(st.session_state.mfbt_results)
    else:
        _render_empty_state(dm, config)


def _execute_backtest(dm: DataManager, wl_manager, config: Dict[str, Any]):
    """执行回测"""
    symbols = config['symbols']

    if not symbols:
        st.warning("请先选择股票")
        return

    # 更新状态
    st.session_state.mfbt_running = True
    st.session_state.mfbt_progress = 0

    try:
        # 进度回调函数
        def progress_callback(percent, message):
            if not st.session_state.mfbt_running:
                return False
            st.session_state.mfbt_progress = percent
            config['progress_bar'].progress(percent / 100)
            config['status_text'].text(f"{message}...")
            return True

        with st.spinner("正在运行回测，请稍候..."):
            if config.get('auto_backfill_to_start', False):
                progress_callback(5, "回测前补齐历史数据并写库")
                backfill_stats = _backfill_stock_data_to_start_date(
                    dm=dm,
                    symbols=symbols,
                    start_date=config['start_date'],
                    end_date=config['end_date'],
                )
                if backfill_stats["attempted"] > 0:
                    st.info(
                        f"已执行历史补齐：尝试 {backfill_stats['attempted']} 只，"
                        f"新增/更新 {backfill_stats['updated']} 只，"
                        f"仍无更早数据 {backfill_stats['unchanged']} 只。"
                    )

            # 获取股票数据
            progress_callback(10, "获取股票数据")
            stock_data = _fetch_stock_data(dm, symbols, config['start_date'], config['end_date'])

            if not stock_data:
                st.error("无法获取股票数据")
                return

            # 计算实际可回测窗口（按股票池共同可用区间）
            requested_start = config['start_date']
            requested_end = config['end_date']
            effective_start, effective_end = _compute_effective_backtest_window(
                stock_data, requested_start, requested_end
            )
            if effective_start is None or effective_end is None:
                st.error("所选股票在指定区间内无共同可回测交易日，请调整股票池或日期范围")
                return
            if effective_start > requested_start:
                st.warning(
                    f"你设置的开始日期为 {requested_start}，但当前股票池共同可用数据从 {effective_start} 才开始。"
                    f"本次将按 {effective_start} ~ {effective_end} 执行回测。"
                )
            if effective_end < requested_end:
                st.info(f"当前股票池共同可用数据截止 {effective_end}，已自动按此日期结束回测。")

            # 构建股票名称映射
            stock_names = {}
            for s in symbols:
                info = wl_manager.get_stock(s)
                if info and info.name:
                    stock_names[s] = info.name
                else:
                    stock_names[s] = s

            progress_callback(30, "准备因子数据")
            factor_data = _prepare_factor_data(stock_data, list(config['factor_weights'].keys()))

            if not factor_data:
                st.error("因子数据准备失败：未生成有效因子面板")
                return

            # 运行回测（统一走服务层契约校验）
            run_result = run_multi_factor_strategy_backtest(
                symbols=symbols,
                db_path=dm.db_path,
                stock_data=stock_data,
                start_date=effective_start,
                end_date=effective_end,
                initial_capital=config['initial_capital'],
                max_positions=config['max_positions'],
                rebalance_days=config['rebalance_days'],
                factor_weights=config['factor_weights'],
                use_ic_weighting=config['use_ic_weighting'],
                ic_update_freq=config['ic_update_freq'] or 60,
                commission_rate=0.0003,
                max_single_position=config.get('max_single_position', 0.2),
                max_total_position=config.get('max_total_position', 0.8),
                stop_loss=config.get('stop_loss', 0.0),
                factor_data=factor_data,
                progress_callback=progress_callback,
                stock_names=stock_names,
            )

            if run_result.get("error"):
                st.error(run_result["error"])
                for warning_msg in run_result.get("warnings", []):
                    st.warning(warning_msg)
                return

            results = run_result["results"]
            results["requested_window"] = {"start": requested_start, "end": requested_end}
            results["effective_window"] = {"start": effective_start, "end": effective_end}
            for warning_msg in run_result.get("warnings", []):
                st.warning(warning_msg)

            config['status_text'].text("回测完成！")

            # 保存结果
            st.session_state.mfbt_results = results
            st.session_state.mfbt_config = config

            st.success("✅ 回测完成！")

    except Exception as e:
        st.error(f"回测出错: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
    finally:
        st.session_state.mfbt_running = False


def _fetch_stock_data(dm: DataManager, symbols: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
    """
    获取股票数据（回测专用，只读缓存）

    使用 CacheOnlyProvider 避免触发网络请求，确保回测稳定性
    """
    # 使用 CacheOnlyProvider，只读数据库，不触发网络请求
    cache_provider = CacheOnlyProvider(dm.db_path)

    stock_data = {}
    for symbol in symbols:
        try:
            df = cache_provider.get_stock_data(symbol, start_date, end_date)
            if not df.empty:
                stock_data[symbol] = df
        except Exception as e:
            continue

    return stock_data


def _compute_effective_backtest_window(
    stock_data: Dict[str, pd.DataFrame],
    requested_start: str,
    requested_end: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    计算股票池共同可用回测窗口（交集区间）。

    返回:
        (effective_start, effective_end)
        若无有效交集，返回 (None, None)
    """
    if not stock_data:
        return None, None

    req_start_dt = pd.to_datetime(requested_start)
    req_end_dt = pd.to_datetime(requested_end)

    min_dates = []
    max_dates = []
    for df in stock_data.values():
        if df is None or df.empty or 'date' not in df.columns:
            continue
        dt_series = pd.to_datetime(df['date'], errors='coerce').dropna()
        if dt_series.empty:
            continue
        min_dates.append(dt_series.min())
        max_dates.append(dt_series.max())

    if not min_dates or not max_dates:
        return None, None

    common_start_dt = max(min_dates)
    common_end_dt = min(max_dates)

    effective_start_dt = max(req_start_dt, common_start_dt)
    effective_end_dt = min(req_end_dt, common_end_dt)

    if effective_start_dt > effective_end_dt:
        return None, None

    return effective_start_dt.strftime('%Y-%m-%d'), effective_end_dt.strftime('%Y-%m-%d')


def _backfill_stock_data_to_start_date(
    dm: DataManager,
    symbols: List[str],
    start_date: str,
    end_date: str,
) -> Dict[str, int]:
    """
    尝试将股票池行情补齐到回测开始日期，并保存到数据库。

    说明：
    - 会触发 DataManager 在线获取流程（KlineManager.fetch_daily_kline）；
    - 是否能补到开始日期取决于数据源可得性与股票上市日期。
    """
    cache_provider = CacheOnlyProvider(dm.db_path)
    attempted = 0
    updated = 0
    unchanged = 0

    for symbol in symbols:
        try:
            before_df = cache_provider.get_stock_data(symbol, start_date, end_date)
            before_min = None if before_df.empty else pd.to_datetime(before_df['date']).min()

            attempted += 1
            # 调用在线路径：若数据库不完整会自动拉取并写库
            _ = dm.get_daily_kline(symbol, start_date, end_date)

            after_df = cache_provider.get_stock_data(symbol, start_date, end_date)
            after_min = None if after_df.empty else pd.to_datetime(after_df['date']).min()

            if before_min is None and after_min is not None:
                updated += 1
            elif before_min is not None and after_min is not None and after_min < before_min:
                updated += 1
            else:
                unchanged += 1
        except Exception:
            unchanged += 1

    return {"attempted": attempted, "updated": updated, "unchanged": unchanged}


def _prepare_factor_data(stock_data: Dict[str, pd.DataFrame], factor_names: List[str]) -> Dict[str, pd.DataFrame]:
    """
    准备因子数据

    Args:
        stock_data: 股票数据
        factor_names: 因子名称列表

    Returns:
        因子数据字典
    """
    factor_data = {}
    ff = FundamentalFactors()
    cached_rows = []

    try:
        # 技术/情绪类因子可以直接从行情计算，其他因子优先走数据库缓存表（factor_values）。
        price_driven_factors = {
            'momentum_20', 'momentum_60', 'volatility_20',
            'price_volume_trend', 'relative_strength', 'volume_ratio'
        }
        db_factor_names = [f for f in factor_names if f not in price_driven_factors and f != 'turnover_rate']

        for symbol, df in stock_data.items():
            factor_df = pd.DataFrame(index=df.index)
            factor_df['date'] = df['date'] if 'date' in df.columns else df.index
            factor_df['symbol'] = symbol

            # 统一日期格式，避免查询时出现 Timestamp / str 混用
            date_series = pd.to_datetime(factor_df['date']).dt.strftime('%Y-%m-%d')
            start_date = date_series.iloc[0] if len(date_series) > 0 else None
            end_date = date_series.iloc[-1] if len(date_series) > 0 else None

            # 先计算技术与情绪因子（基于价格成交量）
            if 'close' in df.columns:
                close = pd.to_numeric(df['close'], errors='coerce')
                returns = close.pct_change()
                factor_df['momentum_20'] = returns.rolling(20).sum()
                factor_df['momentum_60'] = returns.rolling(60).sum()
                factor_df['volatility_20'] = returns.rolling(20).std()
                factor_df['price_volume_trend'] = (returns.fillna(0) * pd.to_numeric(df.get('volume', 0), errors='coerce').fillna(0)).cumsum()
                # 相对强弱：用20日收益近似（无基准指数时的保守替代）
                factor_df['relative_strength'] = close / close.shift(20) - 1

            if 'volume' in df.columns:
                vol = pd.to_numeric(df['volume'], errors='coerce')
                factor_df['volume_ratio'] = vol / vol.rolling(20).mean()

            # 批量加载数据库缓存的因子值（避免逐日逐股计算）
            if db_factor_names and start_date and end_date:
                conn = sqlite3.connect(ff.fdm.db_path)
                try:
                    placeholders = ",".join(["?" for _ in db_factor_names])
                    query = f"""
                        SELECT trade_date, factor_name, factor_value
                        FROM factor_values
                        WHERE symbol = ?
                          AND trade_date BETWEEN ? AND ?
                          AND factor_name IN ({placeholders})
                        ORDER BY trade_date
                    """
                    params = [symbol, start_date, end_date] + db_factor_names
                    cached_df = pd.read_sql_query(query, conn, params=params)
                except Exception:
                    cached_df = pd.DataFrame()
                finally:
                    conn.close()

                if not cached_df.empty:
                    cached_df['trade_date'] = pd.to_datetime(cached_df['trade_date']).dt.strftime('%Y-%m-%d')
                    pivot_df = cached_df.pivot_table(
                        index='trade_date',
                        columns='factor_name',
                        values='factor_value',
                        aggfunc='last'
                    )
                    trade_date_map = date_series.to_dict()

                    for factor in db_factor_names:
                        source_factor = factor
                        if factor == 'eps' and source_factor not in pivot_df.columns and 'eps_ttm' in pivot_df.columns:
                            source_factor = 'eps_ttm'
                        if source_factor in pivot_df.columns:
                            series_map = pivot_df[source_factor].to_dict()
                            factor_df[factor] = pd.Series(trade_date_map).map(series_map).values

            # 换手率：优先批量从估值表读取 float_shares，按交易日向前匹配
            if 'turnover_rate' in factor_names and 'volume' in df.columns and start_date and end_date:
                conn = sqlite3.connect(ff.fdm.db_path)
                try:
                    valuation_df = pd.read_sql_query(
                        """
                        SELECT trade_date, float_shares
                        FROM valuation_data
                        WHERE symbol = ?
                          AND trade_date BETWEEN ? AND ?
                        ORDER BY trade_date
                        """,
                        conn,
                        params=(symbol, start_date, end_date)
                    )
                except Exception:
                    valuation_df = pd.DataFrame()
                finally:
                    conn.close()

                if not valuation_df.empty:
                    trade_dates_df = pd.DataFrame({
                        'trade_date': pd.to_datetime(date_series)
                    }).sort_values('trade_date')
                    valuation_df['trade_date'] = pd.to_datetime(valuation_df['trade_date'])
                    valuation_df['float_shares'] = pd.to_numeric(valuation_df['float_shares'], errors='coerce')
                    valuation_df = valuation_df.dropna(subset=['float_shares']).sort_values('trade_date')

                    if not valuation_df.empty:
                        merged_df = pd.merge_asof(
                            trade_dates_df,
                            valuation_df[['trade_date', 'float_shares']],
                            on='trade_date',
                            direction='backward'
                        )
                        volume_series = pd.to_numeric(df.get('volume', np.nan), errors='coerce')
                        factor_df['turnover_rate'] = np.where(
                            merged_df['float_shares'].fillna(0) > 0,
                            (volume_series.values / merged_df['float_shares'].values) * 100,
                            np.nan
                        )

            # 对数据库没有命中的因子做兜底按日计算（保持结果兼容）
            fallback_factors = [
                f for f in factor_names
                if f not in factor_df.columns or factor_df[f].isna().all()
            ]
            if fallback_factors:
                for idx, trade_date in enumerate(date_series):
                    try:
                        day_factors = ff.calculate_all_factors(symbol, trade_date)
                    except Exception:
                        day_factors = {}

                    for factor in fallback_factors:
                        current_val = factor_df.at[factor_df.index[idx], factor] if factor in factor_df.columns else np.nan
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

            # 对估值与财务因子做前向填充，保证季度/日频数据对齐到交易日
            for factor in factor_names:
                if factor in factor_df.columns:
                    factor_df[factor] = pd.to_numeric(factor_df[factor], errors='coerce').ffill()

            # 仅保留所需因子列 + 基础列
            keep_cols = ['date', 'symbol'] + [f for f in factor_names if f in factor_df.columns]
            factor_data[symbol] = factor_df[keep_cols].copy()

        # 将兜底现算结果回写缓存，加速后续回测
        if cached_rows:
            conn = sqlite3.connect(ff.fdm.db_path)
            try:
                cursor = conn.cursor()
                cursor.executemany(
                    """
                    INSERT OR REPLACE INTO factor_values
                    (symbol, trade_date, factor_name, factor_value, update_time)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    cached_rows
                )
                conn.commit()
            except Exception:
                conn.rollback()
            finally:
                conn.close()
    finally:
        ff.close()

    return factor_data


# =============================================================================
# 结果展示
# =============================================================================

def _render_results(results: Dict[str, Any]):
    """渲染回测结果"""

    # 结果标签页
    result_tabs = st.tabs([
        "📈 收益概览",
        "📊 因子分析",
        "📋 交易明细",
        "🔄 调仓记录",
        "💾 配置管理"
    ])

    # 标签页1: 收益概览
    with result_tabs[0]:
        _render_returns_overview(results)

    # 标签页2: 因子分析
    with result_tabs[1]:
        _render_factor_analysis(results)

    # 标签页3: 交易明细
    with result_tabs[2]:
        _render_trade_details(results)

    # 标签页4: 调仓记录
    with result_tabs[3]:
        _render_rebalance_history(results)

    # 标签页5: 配置管理
    with result_tabs[4]:
        _render_config_management(results)


def _render_returns_overview(results: Dict[str, Any]):
    """渲染收益概览"""
    _render_subsection_title("收益概览", "📈", "查看核心收益风险指标与权益曲线")

    # 收益指标卡片
    col1, col2, col3, col4, col5 = st.columns(5)

    metrics = [
        ("总收益率", f"{results.get('total_return', 0):.2%}", "📈"),
        ("年化收益率", f"{results.get('annual_return', 0):.2%}", "📊"),
        ("夏普比率", f"{results.get('sharpe_ratio', 0):.2f}", "⚖️"),
        ("最大回撤", f"{results.get('max_drawdown', 0):.2%}", "📉"),
        ("波动率", f"{results.get('volatility', 0):.2%}", "🌊")
    ]

    for col, (label, value, icon) in zip([col1, col2, col3, col4, col5], metrics):
        with col:
            st.metric(label, value, delta=icon)

    # 首笔交易诊断：解释“回测开始后长期空仓”
    backtest_dates = results.get('dates', {}) or {}
    backtest_start = str(backtest_dates.get('start', ''))[:10]
    first_buy_date = results.get('first_buy_date')
    pre_buy_debug = results.get('pre_first_buy_diagnostics', []) or []
    if first_buy_date and backtest_start and first_buy_date > backtest_start:
        st.info(f"首笔买入发生在 `{first_buy_date}`，晚于回测起始 `{backtest_start}`。可在下方查看首笔买入前调仓诊断。")
    elif not first_buy_date and pre_buy_debug:
        st.warning("本次回测未发生买入，已记录调仓诊断，可展开查看。")

    if pre_buy_debug:
        with st.expander("🔍 首笔买入前空仓诊断", expanded=False):
            debug_df = pd.DataFrame(pre_buy_debug)
            preferred_cols = [
                "date",
                "reason",
                "candidate_count",
                "allocation_count",
                "price_available_count",
                "executed_buy_count",
                "skip_non_positive_weight",
                "skip_missing_price",
                "skip_target_already_reached",
                "skip_lot_too_small",
                "cash",
                "positions_count",
            ]
            show_cols = [c for c in preferred_cols if c in debug_df.columns]
            st.dataframe(debug_df[show_cols] if show_cols else debug_df, use_container_width=True, hide_index=True)

    # 权益曲线
    st.markdown("### 权益曲线")

    equity_df = results.get('equity_curve')
    if equity_df is not None and not equity_df.empty:
        fig = go.Figure()

        # 组合权益曲线
        fig.add_trace(go.Scatter(
            x=equity_df['date'],
            y=equity_df['total_value'],
            mode='lines',
            name='组合权益',
            line=dict(color='#1f77b4', width=2)
        ))

        # 基准曲线（如果有）
        if 'benchmark' in equity_df.columns:
            fig.add_trace(go.Scatter(
                x=equity_df['date'],
                y=equity_df['benchmark'],
                mode='lines',
                name='基准',
                line=dict(color='#888888', width=1, dash='dash')
            ))

        fig.update_layout(
            height=400,
            xaxis_title="日期",
            yaxis_title="权益",
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02)
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("无权益曲线数据")

    # 月度收益统计
    st.markdown("### 月度收益统计")

    monthly_returns = results.get('monthly_returns')
    if monthly_returns is not None and not monthly_returns.empty:
        # 应用颜色
        def color_return(val):
            if val > 0:
                return 'color: #dc3545'  # 红色涨
            elif val < 0:
                return 'color: #28a745'  # 绿色跌
            return ''

        styled = monthly_returns.style.applymap(color_return, subset=['收益率'])
        st.dataframe(styled, use_container_width=True)
    else:
        st.info("无月度收益数据")


def _render_factor_analysis(results: Dict[str, Any]):
    """渲染因子分析"""
    _render_subsection_title("因子分析", "🧪", "追踪权重变化、有效性和收益归因")

    factor_report = results.get('factor_report', {})

    # 因子配置概览
    st.markdown("### 因子配置概览")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**权重对比**")
        factor_weights = factor_report.get('factor_weights', {})
        ic_weights = factor_report.get('ic_weights', {})

        weight_data = []
        for factor in factor_weights:
            weight_data.append({
                '因子': factor,
                '基础权重': f"{factor_weights[factor]:.1%}",
                'IC权重': f"{ic_weights.get(factor, 0):.1%}",
                '变化': f"{ic_weights.get(factor, 0) - factor_weights[factor]:+.1%}"
            })

        if weight_data:
            st.dataframe(pd.DataFrame(weight_data), use_container_width=True)
        else:
            st.info("无权重数据")

    with col2:
        st.markdown("**IC 有效性判定**")
        ic_validity = factor_report.get('ic_validity_report', {})

        validity_colors = {
            'strong': '🟢',
            'normal': '🟡',
            'weak': '🟠',
            'invalid': '🔴'
        }

        validity_data = []
        for factor, stats in ic_validity.items():
            validity_data.append({
                '因子': factor,
                'IC均值': f"{stats.get('ic_mean', 0):.3f}",
                'IR': f"{stats.get('ir', 0):.2f}",
                '判定': f"{validity_colors.get(stats.get('validity', 'invalid'), '⚪')} {stats.get('validity', 'unknown')}"
            })

        if validity_data:
            st.dataframe(pd.DataFrame(validity_data), use_container_width=True)
        else:
            st.info("无IC有效性数据")

    # 因子暴露度时序
    st.markdown("### 因子暴露度时序")

    exposure_df = factor_report.get('exposure_timeseries')
    if exposure_df is not None and not exposure_df.empty:
        fig = go.Figure()

        for col in exposure_df.columns:
            fig.add_trace(go.Scatter(
                x=exposure_df.index,
                y=exposure_df[col],
                mode='lines',
                name=col,
                stackgroup='one' if len(exposure_df.columns) <= 3 else None
            ))

        fig.update_layout(
            height=400,
            xaxis_title="日期",
            yaxis_title="暴露度"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("无暴露度数据")

    # 因子收益归因
    st.markdown("### 因子收益归因")

    attribution = factor_report.get('attribution', {})
    if attribution:
        factors = list(attribution.keys())
        contributions = [attribution[f].get('contribution', 0) for f in factors]
        returns = [attribution[f].get('factor_return', 0) for f in factors]

        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=("收益贡献", "因子收益率")
        )

        colors = ['#dc3545' if c > 0 else '#28a745' for c in contributions]
        fig.add_trace(
            go.Bar(x=factors, y=contributions, marker_color=colors, name="贡献"),
            row=1, col=1
        )

        colors2 = ['#dc3545' if r > 0 else '#28a745' for r in returns]
        fig.add_trace(
            go.Bar(x=factors, y=returns, marker_color=colors2, name="收益率"),
            row=1, col=2
        )

        fig.update_layout(height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("无归因数据")


def _render_trade_details(results: Dict[str, Any]):
    """渲染交易明细（含因子信息）"""
    _render_subsection_title("交易明细", "📋", "支持筛选交易记录并查看因子得分")

    trade_details = results.get('trade_details')

    if trade_details is not None and not trade_details.empty:
        # ===== 因子列展示控制 =====
        factor_names = results.get('factor_names', [])
        show_factors = st.checkbox("显示因子得分列", value=False, key="mfbt_show_factors")

        # 筛选器
        col1, col2 = st.columns(2)
        with col1:
            if '股票' in trade_details.columns:
                symbol_filter = st.multiselect(
                    "股票筛选",
                    trade_details['股票'].unique(),
                    default=[],
                    key="mfbt_symbol_filter"
                )
            else:
                symbol_filter = []
        with col2:
            status_filter = st.selectbox(
                "状态筛选",
                ["全部", "已卖出", "持有中"],
                key="mfbt_status_filter"
            )

        # 应用筛选
        filtered = trade_details.copy()
        if symbol_filter:
            filtered = filtered[filtered['股票'].isin(symbol_filter)]
        if status_filter == "已卖出":
            filtered = filtered[filtered.get('状态', '') == '已卖出']
        elif status_filter == "持有中":
            filtered = filtered[filtered.get('状态', '') == '持有中']

        # 颜色函数
        def color_return(val):
            if isinstance(val, (int, float)):
                if val > 0:
                    return 'color: #dc3545'
                elif val < 0:
                    return 'color: #28a745'
            return ''

        # 构建显示列顺序
        base_cols = ['股票', '买入日期', '买入价格（元）', '买入数量', '买入金额（元）',
                     '卖出日期', '卖出价格（元）', '收益率（%）', '净收益率（%）', '收益金额（元）',
                     '持有天数', '状态', '卖出原因']
        factor_cols = []
        if show_factors and factor_names:
            for f in factor_names:
                if f'{f}_得分' in filtered.columns:
                    factor_cols.append(f'{f}_得分')
            if '综合得分' in filtered.columns:
                factor_cols.append('综合得分')
            if '排名' in filtered.columns:
                factor_cols.append('排名')

        display_cols = [c for c in base_cols + factor_cols if c in filtered.columns]

        # 使用实际列名渲染
        display_df = filtered[display_cols]
        float_cols = display_df.select_dtypes(include=["float", "floating"]).columns.tolist()
        styled = display_df.style.applymap(
            color_return, subset=['收益率（%）', '收益金额（元）']
        )
        if float_cols:
            styled = styled.format("{:.2f}", subset=float_cols)
        st.dataframe(styled, use_container_width=True)

        # ===== 展开详情：雷达图 =====
        if show_factors and factor_names and not filtered.empty:
            st.markdown("**交易因子详情**")
            selected_trade = st.selectbox(
                "选择交易查看因子雷达图",
                filtered['交易ID'].tolist(),
                key="mfbt_radar_trade"
            )
            row = filtered[filtered['交易ID'] == selected_trade]
            if not row.empty:
                _render_trade_radar(row.iloc[0], factor_names)

        # 统计摘要
        st.markdown("**交易统计**")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("总交易次数", len(filtered))
        with col2:
            sell_trades = len(filtered[filtered.get('状态', '') == '已卖出'])
            st.metric("已卖出次数", sell_trades)
        with col3:
            open_trades = len(filtered[filtered.get('状态', '') == '持有中'])
            st.metric("持有中次数", open_trades)
        with col4:
            if '持有天数' in filtered.columns:
                avg_days = filtered['持有天数'].mean()
                st.metric("平均持有天数", str(int(round(avg_days))))
    else:
        st.info("无交易明细数据")


def _render_trade_radar(row: pd.Series, factor_names: List[str]):
    """渲染单只交易的因子雷达图"""
    # 收集因子得分
    theta = []
    r = []
    for f in factor_names:
        col = f'{f}_得分'
        if col in row and pd.notna(row[col]):
            theta.append(f)
            r.append(row[col])

    if len(theta) < 3:
        st.info("因子数据不足，无法绘制雷达图")
        return

    fig = go.Figure(data=go.Scatterpolar(
        r=r + [r[0]],
        theta=theta + [theta[0]],
        fill='toself',
        name='该股票'
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False,
        height=400,
        title=f"交易 {row.get('股票', '')} 因子得分雷达图"
    )
    st.plotly_chart(fig, use_container_width=True)

    # 显示综合得分和排名
    col1, col2 = st.columns(2)
    with col1:
        score = row.get('综合得分', 0)
        st.metric("综合得分", f"{score:.1f}" if score else "N/A")
    with col2:
        rank = row.get('排名', 0)
        # 排名可能是 "4 / 8" 格式的字符串，需要解析
        if isinstance(rank, str) and '/' in rank:
            rank_num = int(rank.split('/')[0].strip())
        elif rank:
            rank_num = int(rank)
        else:
            rank_num = None
        st.metric("当日排名", f"第 {rank_num} 名" if rank_num else "N/A")


def _render_rebalance_history(results: Dict[str, Any]):
    """渲染调仓记录"""
    _render_subsection_title("调仓记录", "🔄", "按调仓日复盘买卖逻辑与候选池变化")

    snapshots = results.get('rebalance_snapshots', [])
    factor_names = results.get('factor_names', [])

    if not snapshots:
        st.info("无调仓记录数据")
        return

    # 调仓时间轴概览
    st.markdown(f"### 调仓概览（共 {len(snapshots)} 次）")

    overview_data = []
    for snap in snapshots:
        overview_data.append({
            '调仓日期': snap.date,
            '买入股票数': len(snap.selected_symbols),
            '卖出股票数': len(snap.sold_symbols),
            '候选股票数': len(snap.all_scores)
        })
    st.dataframe(pd.DataFrame(overview_data), use_container_width=True)

    # 选择单次调仓查看详情
    st.markdown("### 单次调仓详情")
    selected_date = st.selectbox(
        "选择调仓日期",
        [s.date for s in snapshots],
        key="mfbt_rebalance_date"
    )

    snapshot = next((s for s in snapshots if s.date == selected_date), None)
    if not snapshot:
        return

    # 显示买入/卖出股票
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**买入股票**")
        if snapshot.selected_symbols:
            for sym in snapshot.selected_symbols:
                score = snapshot.all_scores.get(sym, 0)
                st.markdown(f"- `{sym}` 综合得分: {score:.1f}")
        else:
            st.caption("无")
    with col2:
        st.markdown("**卖出股票**")
        if snapshot.sold_symbols:
            for sym in snapshot.sold_symbols:
                st.markdown(f"- `{sym}`")
        else:
            st.caption("无")

    # 因子面板表格
    if snapshot.all_scores:
        st.markdown("**当日全部候选股票因子面板**")

        panel_data = []
        for symbol in sorted(snapshot.all_scores.keys(), key=lambda x: snapshot.all_scores.get(x, 0), reverse=True):
            row = {'股票': symbol, '综合得分': round(snapshot.all_scores.get(symbol, 0), 1)}

            # 因子原始值
            vals = snapshot.all_factor_values.get(symbol, {})
            for f in factor_names:
                if f in vals:
                    row[f] = round(vals[f], 4) if isinstance(vals[f], float) else vals[f]

            # 因子百分位得分
            percs = snapshot.all_factor_percentiles.get(symbol, {})
            for f in factor_names:
                if f in percs:
                    row[f'{f}_得分'] = round(percs[f], 1)

            # 是否被选中
            row['是否买入'] = '是' if symbol in snapshot.selected_symbols else '否'
            row['是否卖出'] = '是' if symbol in snapshot.sold_symbols else '否'

            panel_data.append(row)

        panel_df = pd.DataFrame(panel_data)

        # 高亮显示
        def highlight_selected(row_df):
            if row_df['是否买入'] == '是':
                return ['background-color: #d4edda'] * len(row_df)
            elif row_df['是否卖出'] == '是':
                return ['background-color: #f8d7da'] * len(row_df)
            return [''] * len(row_df)

        styled = panel_df.style.apply(highlight_selected, axis=1)
        st.dataframe(styled, use_container_width=True)

        # 因子得分热力图
        if factor_names and any(f'{f}_得分' in panel_df.columns for f in factor_names):
            st.markdown("**因子得分热力图**")
            score_cols = [f'{f}_得分' for f in factor_names if f'{f}_得分' in panel_df.columns]
            if score_cols:
                heatmap_df = panel_df[['股票'] + score_cols].set_index('股票')
                fig = go.Figure(data=go.Heatmap(
                    z=heatmap_df.values,
                    x=heatmap_df.columns,
                    y=heatmap_df.index,
                    colorscale='RdYlGn',
                    zmin=0, zmax=100,
                    text=heatmap_df.values,
                    texttemplate="%{text:.0f}",
                    textfont={"size": 10}
                ))
                fig.update_layout(height=max(300, len(heatmap_df) * 25 + 100))
                st.plotly_chart(fig, use_container_width=True)


def _render_config_management(results: Dict[str, Any]):
    """渲染配置管理"""
    _render_subsection_title("配置管理", "💾", "保存策略参数并管理回测输出")

    config = st.session_state.get('mfbt_config', {})

    # 显示当前配置
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**📤 保存当前配置**")
        config_name = st.text_input(
            "配置名称",
            placeholder="我的因子配置_v1",
            key="mfbt_config_name"
        )

        if st.button("💾 保存", use_container_width=True, key="mfbt_save_config"):
            if config_name:
                # TODO: 保存到数据库
                st.success(f"配置「{config_name}」已保存")
            else:
                st.warning("请输入配置名称")

    with col2:
        st.markdown("**📥 加载已有配置**")

        # TODO: 从数据库加载配置列表
        saved_configs = []

        if saved_configs:
            config_to_load = st.selectbox(
                "选择配置",
                saved_configs,
                format_func=lambda x: x['name'],
                key="mfbt_load_config"
            )

            if st.button("📥 加载", use_container_width=True, key="mfbt_load_btn"):
                st.success(f"已加载配置「{config_to_load['name']}」")
        else:
            st.info("暂无保存的配置")

    # 历史回测记录
    st.markdown("### 📜 历史回测记录")

    history = results.get('history', [])

    if history:
        st.dataframe(pd.DataFrame(history), use_container_width=True)
    else:
        st.info("暂无历史回测记录")

    # 导出按钮
    st.markdown("### 📤 导出报告")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 导出Excel", use_container_width=True, key="mfbt_export_excel"):
            # TODO: 实现 Excel 导出
            st.info("Excel导出功能开发中")

    with col2:
        if st.button("📑 导出PDF", use_container_width=True, key="mfbt_export_pdf"):
            # TODO: 实现 PDF 导出
            st.info("PDF导出功能开发中")


# =============================================================================
# 空状态展示
# =============================================================================

def _render_empty_state(dm: DataManager, config: Dict[str, Any]):
    """渲染空状态（无结果时）"""

    st.info("👈 请在左侧配置参数后点击「开始回测」")

    # 显示近期 IC 表现（示例数据）
    st.markdown("### 最近 IC 表现")
    st.caption("基于最近 60 个交易日统计（示例数据）")

    sample_ic_data = pd.DataFrame({
        '因子': ['roe', 'pe', 'momentum_20', 'revenue_growth', 'debt_ratio', 'turnover_rate'],
        'IC均值': [0.052, -0.008, 0.031, 0.018, -0.012, 0.015],
        'IC标准差': [0.076, 0.082, 0.074, 0.068, 0.065, 0.071],
        'IR': [0.68, -0.10, 0.42, 0.26, -0.18, 0.21],
        '判定': ['🟢 强有效', '🔴 无效', '🟡 有效', '🟠 弱有效', '🔴 无效', '🟠 弱有效']
    })

    st.dataframe(sample_ic_data, use_container_width=True)

    # 快速开始指南
    with st.expander("📖 快速开始指南", expanded=False):
        st.markdown("""
        **多因子回测快速指南**

        1. **选择因子**：在左侧选择要使用的因子，建议初学者使用默认配置

        2. **设置权重**：
           - 🤖 IC智能加权：根据因子历史表现自动调整权重
           - ✏️ 手动设置：手动拖动滑块设置各因子权重

        3. **选择股票池**：使用自选股或输入自定义股票列表

        4. **设置回测参数**：
           - 回测期间：建议至少1年
           - 初始资金：根据实际需求设置
           - 最大持仓数：建议5-10只
           - 调仓周期：建议5-20天

        5. **点击开始回测**：等待回测完成，查看结果

        **IC 判定标准**：
        - 🟢 强有效：IC > 3% 且 IR > 0.5
        - 🟡 有效：IC > 2% 且 IR > 0.3
        - 🟠 弱有效：IC > 1% 且 IR > 0.2
        - 🔴 无效：IC < 0 或 IR < 0.2
        """)


# =============================================================================
# 便捷函数
# =============================================================================

def render_mini_factor_panel(dm: DataManager, wl_manager) -> Dict[str, Any]:
    """
    渲染精简版因子面板（用于嵌入其他页面）

    Returns:
        因子配置字典
    """
    # 简化版侧边栏
    with st.sidebar:
        st.markdown("### 📊 因子配置")

        # 快速选择预设
        preset = st.selectbox(
            "选择预设",
            ["默认（ROE+估值+动量）", "价值投资", "成长投资", "技术面", "自定义"]
        )

        if preset == "默认（ROE+估值+动量）":
            default_weights = {'roe': 0.3, 'pe': 0.2, 'pb': 0.1, 'momentum_20': 0.3, 'revenue_growth': 0.1}
        elif preset == "价值投资":
            default_weights = {'roe': 0.25, 'pe': 0.30, 'pb': 0.25, 'debt_ratio': 0.20}
        elif preset == "成长投资":
            default_weights = {'roe': 0.20, 'revenue_growth': 0.35, 'profit_growth': 0.25, 'momentum_20': 0.20}
        elif preset == "技术面":
            default_weights = {'momentum_20': 0.4, 'momentum_60': 0.3, 'volatility_20': 0.15, 'volume_ratio': 0.15}
        else:
            default_weights = {'roe': 0.25, 'pe': 0.15, 'momentum_20': 0.30, 'revenue_growth': 0.15, 'debt_ratio': 0.15}

        # IC 加权开关
        use_ic = st.checkbox("启用IC智能加权", value=True)

        st.markdown("---")

    return {
        'factor_weights': default_weights,
        'use_ic_weighting': use_ic
    }
"""
因子回测页面
多因子策略回测的 Web 界面
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# 导入后端模块
try:
    from quant_system.portfolio.multi_factor_backtest import MultiFactorBacktest, run_multi_factor_backtest
    from quant_system.portfolio.factor_ic_configurator import FactorICConfigurator
    from quant_system.portfolio.factor_signal_generator import FactorSignalGenerator
    from quant_system.data.data_manager import DataManager
except ImportError:
    from ..portfolio.multi_factor_backtest import MultiFactorBacktest, run_multi_factor_backtest
    from ..portfolio.factor_ic_configurator import FactorICConfigurator
    from ..portfolio.factor_signal_generator import FactorSignalGenerator
    from ..data.data_manager import DataManager


# =============================================================================
# 因子分类定义
# =============================================================================

FACTOR_CATEGORIES = {
    "基本面因子": {
        "roe": "ROE（净资产收益率）",
        "roa": "ROA（资产收益率）",
        "gross_margin": "毛利率",
        "net_margin": "净利率",
        "eps": "EPS（每股收益）",
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

def render_factor_backtest_page(dm: DataManager, wl_manager):
    """
    渲染因子回测页面

    Args:
        dm: DataManager 实例
        wl_manager: WatchlistManager 实例
    """
    st.header("📊 多因子回测")

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
    st.markdown("### 📋 因子配置")

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
    st.markdown("### ⚙️ 回测参数")

    # 股票池来源
    stock_source = st.selectbox(
        "股票池来源",
        ["📈 自选股", "📋 自定义列表"],
        index=0,
        key="mfbt_stock_source"
    )

    symbols = []
    if stock_source == "📈 自选股":
        watchlist_stocks = wl_manager.get_all_stocks()
        if watchlist_stocks:
            symbols = [s.symbol for s in watchlist_stocks]
            st.caption(f"将使用 {len(symbols)} 只自选股")
        else:
            st.warning("自选股为空，请先添加股票")
    else:
        stock_list_input = st.text_area(
            "股票代码（逗号分隔）",
            "000001.SZ, 600000.SH, 600519.SH",
            height=80,
            key="mfbt_stock_list"
        )
        symbols = [s.strip() for s in stock_list_input.split(",") if s.strip()]

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
            datetime(2024, 3, 19),
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
    st.markdown("### 🚀 执行回测")

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
        _execute_backtest(dm, config)

    # 处理中断
    if config['stop_button']:
        st.session_state.mfbt_running = False
        st.warning("回测已中断")

    # 结果展示
    if st.session_state.mfbt_results:
        _render_results(st.session_state.mfbt_results)
    else:
        _render_empty_state(dm, config)


def _execute_backtest(dm: DataManager, config: Dict[str, Any]):
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
            # 获取股票数据
            progress_callback(10, "获取股票数据")
            stock_data = _fetch_stock_data(dm, symbols, config['start_date'], config['end_date'])

            if not stock_data:
                st.error("无法获取股票数据")
                return

            progress_callback(30, "准备因子数据")

            # 构建因子数据
            factor_data = _prepare_factor_data(stock_data, list(config['factor_weights'].keys()))

            progress_callback(50, "运行多因子回测")

            # 运行回测
            results = run_multi_factor_backtest(
                symbols=symbols,
                stock_data=stock_data,
                factor_data=factor_data,
                start_date=config['start_date'],
                end_date=config['end_date'],
                initial_capital=config['initial_capital'],
                max_positions=config['max_positions'],
                rebalance_days=config['rebalance_days'],
                factor_weights=config['factor_weights'],
                use_ic_weighting=config['use_ic_weighting'],
                ic_update_freq=config['ic_update_freq'] or 60,
                progress_callback=progress_callback
            )

            progress_callback(100, "回测完成")
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
    """获取股票数据"""
    stock_data = {}

    for symbol in symbols:
        try:
            df = dm.get_daily_kline(symbol, start_date, end_date)
            if not df.empty:
                stock_data[symbol] = df
        except Exception as e:
            continue

    return stock_data


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

    for symbol, df in stock_data.items():
        # 这里简化处理，实际应该从 FactorData 或 FinancialDataManager 获取
        # 当前模拟生成因子数据
        np.random.seed(hash(symbol) % 2**32)

        factor_df = pd.DataFrame(index=df.index)
        factor_df['date'] = df['date'] if 'date' in df.columns else df.index
        factor_df['symbol'] = symbol

        for factor in factor_names:
            if factor == 'roe':
                factor_df['roe'] = np.random.uniform(0.05, 0.25, len(df))
            elif factor == 'pe':
                factor_df['pe'] = np.random.uniform(5, 30, len(df))
            elif factor == 'pb':
                factor_df['pb'] = np.random.uniform(0.5, 5, len(df))
            elif factor == 'momentum_20':
                # 计算20日动量
                if 'close' in df.columns:
                    returns = df['close'].pct_change()
                    factor_df['momentum_20'] = returns.rolling(20).sum()
                else:
                    factor_df['momentum_20'] = np.random.uniform(-0.1, 0.1, len(df))
            elif factor == 'revenue_growth':
                factor_df['revenue_growth'] = np.random.uniform(-0.2, 0.5, len(df))
            elif factor == 'debt_ratio':
                factor_df['debt_ratio'] = np.random.uniform(0.2, 0.8, len(df))
            elif factor == 'turnover_rate':
                factor_df['turnover_rate'] = np.random.uniform(0.5, 10, len(df))
            elif factor == 'volume_ratio':
                factor_df['volume_ratio'] = np.random.uniform(0.5, 3, len(df))
            else:
                factor_df[factor] = np.random.randn(len(df))

        factor_data[symbol] = factor_df

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

    # 标签页4: 配置管理
    with result_tabs[3]:
        _render_config_management(results)


def _render_returns_overview(results: Dict[str, Any]):
    """渲染收益概览"""

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
    """渲染交易明细"""

    trade_details = results.get('trade_details')

    if trade_details is not None and not trade_details.empty:
        # 筛选器
        col1, col2 = st.columns(2)

        # 股票筛选 - get_trade_details_df 使用 '股票' 列名
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

        # 状态筛选 - 根据 '状态' 列筛选
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

        # 使用实际列名 '收益率（%）' 和 '收益金额（元）'
        styled = filtered.style.applymap(color_return, subset=['收益率（%）', '收益金额（元）'])

        # 显示表格
        st.dataframe(styled, use_container_width=True)

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
                st.metric("平均持有天数", f"{avg_days:.1f}")
    else:
        st.info("无交易明细数据")


def _render_config_management(results: Dict[str, Any]):
    """渲染配置管理"""

    st.markdown("### 💾 配置管理")

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
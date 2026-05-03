"""
量化交易系统 Web 界面
基于 Streamlit 的交互式分析界面
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import atexit

from data.data_manager import DataManager
from portfolio.watchlist import WatchlistManager, filter_out_benchmark_stocks, filter_out_benchmark_symbols
from portfolio.signal_scanner import SignalScanner, ScanResult, ScanSignal
from web.factor_backtest_page import render_factor_backtest_page
from web.factor_analysis_page import render_factor_analysis_page
from web.pages.data_management import render_data_management_page
from web.services.backtest_service import (
    load_backtest_stock_data,
    run_multi_factor_strategy_backtest,
    run_standard_strategy_backtest,
)
from web.services.backtest_params_service import build_run_config, validate_run_config
from web.services.backtest_presenter import (
    render_multi_factor_results,
    render_standard_results,
)

# 页面配置
st.set_page_config(
    page_title="量化交易系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"  # 默认收起侧边栏
)

# 自定义样式（产品化视觉）
st.markdown("""
<style>
    :root {
        --primary-50: #eff6ff;
        --primary-500: #2563eb;
        --primary-600: #1d4ed8;
        --slate-100: #f1f5f9;
        --slate-200: #e2e8f0;
        --slate-300: #cbd5e1;
        --slate-500: #64748b;
        --slate-700: #334155;
        --slate-800: #1e293b;
        --success: #16a34a;
        --danger: #dc2626;
    }

    .stApp {
        background:
            radial-gradient(circle at 20% -20%, #dbeafe 0%, rgba(219, 234, 254, 0) 40%),
            radial-gradient(circle at 85% -25%, #e0e7ff 0%, rgba(224, 231, 255, 0) 35%),
            #f8fafc;
    }

    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
    }

    .app-hero {
        border: 1px solid #dbe4ff;
        background: linear-gradient(135deg, #1e3a8a 0%, #1d4ed8 55%, #2563eb 100%);
        color: #ffffff;
        border-radius: 16px;
        padding: 20px 24px;
        margin-bottom: 18px;
        box-shadow: 0 10px 24px rgba(37, 99, 235, 0.18);
    }

    .app-hero .title {
        font-size: 1.9rem;
        font-weight: 800;
        line-height: 1.2;
        margin-bottom: 6px;
    }

    .app-hero .subtitle {
        font-size: 0.96rem;
        color: #dbeafe;
    }

    .hero-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 14px;
    }

    .hero-badge {
        background: rgba(255, 255, 255, 0.14);
        border: 1px solid rgba(255, 255, 255, 0.25);
        border-radius: 999px;
        padding: 4px 10px;
        font-size: 0.8rem;
        color: #eff6ff;
    }

    .section-title {
        margin: 4px 0 14px;
        padding: 10px 14px;
        border-left: 4px solid var(--primary-500);
        border-radius: 8px;
        background: linear-gradient(90deg, #eff6ff 0%, #f8fafc 100%);
    }

    .section-title .main {
        font-size: 1.1rem;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 2px;
    }

    .section-title .desc {
        font-size: 0.86rem;
        color: var(--slate-500);
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        padding: 8px;
        border-radius: 12px;
        background: #eef2ff;
        border: 1px solid #dbe4ff;
        margin-bottom: 16px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 9px;
        color: var(--slate-700);
        font-weight: 600;
        padding: 10px 16px;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
        color: white !important;
        box-shadow: 0 6px 14px rgba(37, 99, 235, 0.25);
    }

    .stock-card {
        background: #ffffff;
        padding: 1rem;
        border-radius: 12px;
        margin: 0.5rem 0;
        border: 1px solid var(--slate-200);
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.05);
        transition: all 0.2s ease;
    }

    .stock-card:hover {
        transform: translateY(-2px);
        border-color: #bfdbfe;
        box-shadow: 0 10px 20px rgba(30, 58, 138, 0.1);
        cursor: pointer;
    }

    .watchlist-overview {
        display: flex;
        gap: 8px;
        margin: 8px 0 12px;
    }

    .watchlist-overview .item {
        flex: 1;
        border-radius: 10px;
        border: 1px solid var(--slate-200);
        background: #ffffff;
        padding: 8px 10px;
        text-align: center;
    }

    .watchlist-overview .label {
        font-size: 0.76rem;
        color: var(--slate-500);
        margin-bottom: 2px;
    }

    .watchlist-overview .value {
        font-size: 1.05rem;
        font-weight: 700;
    }

    .watchlist-symbol {
        font-size: 1.45rem;
        font-weight: 700;
        color: #0f172a;
    }

    .watchlist-name {
        font-size: 1rem;
        color: #64748b;
        margin-left: 6px;
    }

    .watchlist-group {
        display: inline-block;
        margin-top: 6px;
        padding: 2px 8px;
        border-radius: 999px;
        background: #f1f5f9;
        color: #334155;
        font-size: 0.74rem;
        border: 1px solid #e2e8f0;
    }

    .watchlist-price {
        text-align: right;
    }

    .watchlist-price .px {
        font-size: 1.55rem;
        font-weight: 800;
        line-height: 1.1;
        color: #0f172a;
        white-space: nowrap;
    }

    .watchlist-price .chg {
        font-size: 1.02rem;
        font-weight: 700;
        margin-top: 3px;
        white-space: nowrap;
    }

    .watchlist-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
    }

    .watchlist-left {
        min-width: 0;
    }

    .watchlist-right {
        text-align: right;
        min-width: 96px;
    }

    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid var(--slate-200);
        border-radius: 12px;
        padding: 8px 14px;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.05);
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid var(--slate-200);
        border-radius: 12px;
        overflow: hidden;
    }

    .stButton > button {
        border-radius: 10px;
        border: 1px solid var(--slate-300);
    }

    .stButton > button[kind="primary"] {
        border: none;
        background: linear-gradient(135deg, var(--primary-600) 0%, var(--primary-500) 100%);
        color: white;
        box-shadow: 0 6px 14px rgba(37, 99, 235, 0.3);
    }

    .positive {
        color: var(--danger) !important;  /* A股红色表示涨 */
    }

    .negative {
        color: var(--success) !important;  /* A股绿色表示跌 */
    }

    .metric-value {
        font-size: 1.45rem;
        font-weight: 700;
    }

    .metric-label {
        font-size: 0.82rem;
        color: #64748b;
        margin-bottom: 2px;
    }

    .market-page-title {
        border: 1px solid #dbe4ff;
        border-radius: 14px;
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 75%);
        color: #e2e8f0;
        padding: 14px 16px;
        margin: 2px 0 14px;
        box-shadow: 0 8px 18px rgba(15, 23, 42, 0.2);
    }

    .market-page-title .main {
        font-size: 1.18rem;
        font-weight: 800;
        color: #f8fafc;
        margin-bottom: 4px;
    }

    .market-page-title .sub {
        font-size: 0.86rem;
        color: #bfdbfe;
    }

    .market-toolbar {
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        background: #ffffff;
        padding: 10px 12px;
        margin: 8px 0 12px;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
    }

    .market-toolbar .label {
        color: #64748b;
        font-size: 0.78rem;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        margin-bottom: 3px;
    }

    .market-toolbar .value {
        color: #0f172a;
        font-size: 0.95rem;
        font-weight: 700;
    }

    .table-caption {
        color: #64748b;
        font-size: 0.8rem;
        margin-top: 6px;
    }
</style>
""", unsafe_allow_html=True)

# 初始化数据管理器
@st.cache_resource
def get_data_manager():
    manager = DataManager()
    print(f"[CONFIG] 当前数据库路径: {manager.db_path}")
    atexit.register(manager.close)
    return manager

dm = get_data_manager()

# 初始化自选股管理器
@st.cache_resource
def get_watchlist_manager():
    return WatchlistManager()

wl_manager = get_watchlist_manager()

# 通用标题组件
def render_section_title(title, icon="📌", desc=""):
    subtitle = f'<div class="desc">{desc}</div>' if desc else ""
    st.markdown(
        f"""
        <div class="section-title">
            <div class="main">{icon} {title}</div>
            {subtitle}
        </div>
        """,
        unsafe_allow_html=True
    )


# 顶部产品头部
def render_app_hero():
    stocks = wl_manager.get_all_stocks()
    groups = sorted({s.group for s in stocks}) if stocks else []
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M")

    st.markdown(
        f"""
        <div class="app-hero">
            <div class="title">量化交易系统 · 专业版工作台</div>
            <div class="subtitle">聚合行情、策略回测、因子研究与数据管理，构建一站式股票研究流程</div>
            <div class="hero-badges">
                <span class="hero-badge">自选股 {len(stocks)} 只</span>
                <span class="hero-badge">分组 {len(groups)} 个</span>
                <span class="hero-badge">环境 Streamlit</span>
                <span class="hero-badge">更新时间 {now_text}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


# 主页面
render_app_hero()

# 创建标签页
# 7个标签页：自选股管理、策略回测、财务数据管理、因子分析、多因子回测、信号扫描、绩效分析
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "⭐ 自选股管理",
    "🎯 策略回测",
    "📥 财务数据管理",
    "🔬 因子分析",
    "📊 多因子回测",
    "📈 信号扫描",
    "📉 绩效分析"
])

# 辅助函数：获取最近交易日行情（仅从数据库读取，不触发网络更新）
def get_latest_quote(symbol):
    """获取股票最近一个交易日的行情数据（仅从数据库读取，不触发网络更新）"""
    try:
        # 获取最近30天的数据
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        # 【修改】只从数据库读取，不触发网络更新
        # 使用 _get_kline_from_db 直接读取，绕过 get_daily_kline 的完整性检查
        df = dm._get_kline_from_db(
            symbol,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        )

        if df.empty:
            return None

        # 返回最近一天的数据
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        return {
            'symbol': symbol,
            'date': latest['date'],
            'close': latest['close'],
            'open': latest['open'],
            'high': latest['high'],
            'low': latest['low'],
            'volume': latest['volume'],
            'pct_change': ((latest['close'] - prev['close']) / prev['close'] * 100) if len(df) > 1 else 0
        }
    except Exception as e:
        return None


def resample_kline(df, period='M'):
    """
    将日K线数据重采样为周K/月K/年K

    Args:
        df: 日K线DataFrame
        period: 'W' 周K, 'M' 月K, 'Y' 年K

    Returns:
        重采样后的DataFrame
    """
    if df.empty:
        return df

    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')

    # 重采样规则
    if period == 'W':
        rule = 'W-FRI'  # 按周收盘（周五）
        label_rule = 'W-FRI'
    elif period == 'M':
        rule = 'M'  # 按月收盘
        label_rule = 'M'
    elif period == 'Y':
        rule = 'Y'  # 按年收盘
        label_rule = 'Y'
    else:
        return df.reset_index()

    # 重采样
    resampled = df.resample(rule).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        'amount': 'sum',
        'symbol': 'last'
    })
    resampled = resampled.dropna(subset=['open', 'high', 'low', 'close'])
    resampled = resampled.reset_index()

    # 重置symbol列
    if 'symbol' not in resampled.columns or resampled['symbol'].isna().all():
        resampled['symbol'] = df['symbol'].iloc[0] if 'symbol' in df.columns else ''

    # 格式化日期
    if period == 'W':
        resampled['date'] = resampled['date'].dt.strftime('%Y-%m-%d') + ' (周线)'
    elif period == 'M':
        resampled['date'] = resampled['date'].dt.strftime('%Y-%m')
    elif period == 'Y':
        resampled['date'] = resampled['date'].dt.strftime('%Y')

    return resampled

# 辅助函数：绘制K线图
def plot_kline(df, symbol, period='D'):
    """
    绘制专业的K线图

    Args:
        df: K线DataFrame
        symbol: 股票代码
        period: 'D' 日K, 'W' 周K, 'M' 月K, 'Y' 年K
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    # 计算涨跌
    df = df.copy()
    df['color'] = df.apply(lambda x: 'rise' if x['close'] >= x['open'] else 'fall', axis=1)

    # 创建子图：K线图 + 成交量
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3],
        subplot_titles=('', '成交量')
    )

    # K线 - 使用中国颜色惯例：红涨绿跌
    fig.add_trace(
        go.Candlestick(
            x=df['date'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='K线',
            increasing_line_color='#FF0000',  # 红色涨
            decreasing_line_color='#00A000',  # 绿色跌
            increasing_fillcolor='#FF0000',
            decreasing_fillcolor='#00A000',
        ),
        row=1, col=1
    )

    # 添加MA均线（根据周期调整参数）
    if period == 'D':  # 日K
        ma_periods = [5, 10, 20, 60]
        ma_labels = ['MA5', 'MA10', 'MA20', 'MA60']
    elif period == 'W':  # 周K
        ma_periods = [5, 10, 20]
        ma_labels = ['MA5', 'MA10', 'MA20']
    elif period == 'M':  # 月K
        ma_periods = [3, 6, 12]
        ma_labels = ['MA3', 'MA6', 'MA12']
    elif period == 'Y':  # 年K
        ma_periods = [3, 5]
        ma_labels = ['MA3', 'MA5']

    ma_color_map = {
        'MA3': '#6366f1',
        'MA5': '#2563eb',
        'MA6': '#0ea5e9',
        'MA10': '#ef4444',
        'MA12': '#f59e0b',
        'MA20': '#10b981',
        'MA60': '#14b8a6'
    }

    for ma_period, ma_label in zip(ma_periods, ma_labels):
        if len(df) >= ma_period:
            df[f'ma{ma_period}'] = df['close'].rolling(ma_period).mean()
            fig.add_trace(go.Scatter(
                x=df['date'], y=df[f'ma{ma_period}'],
                name=ma_label,
                line=dict(width=1.6, color=ma_color_map.get(ma_label, '#64748b'))
            ), row=1, col=1)

    # 成交量柱状图
    colors = ['#FF0000' if c >= o else '#00A000' for c, o in zip(df['close'], df['open'])]
    fig.add_trace(
        go.Bar(
            x=df['date'],
            y=df['volume'],
            marker_color=colors,
            name='成交量',
            opacity=0.7
        ),
        row=2, col=1
    )

    # 周期标题
    period_names = {'D': '日K', 'W': '周K', 'M': '月K', 'Y': '年K'}

    # 更新布局
    fig.update_layout(
        title=dict(
            text=f'<b>{symbol}</b> {period_names.get(period, "K线")}走势',
            x=0.5,
            font=dict(size=18)
        ),
        height=820,
        showlegend=True,
        template='plotly_white',
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1
        ),
        hovermode='x unified',
        dragmode='pan',
        xaxis=dict(
            rangeslider=dict(visible=False),
            type='category',
            tickangle=45,
            showgrid=True,
            gridcolor='rgba(148, 163, 184, 0.18)',
            showspikes=True,
            spikemode='across',
            spikesnap='cursor',
            spikethickness=1
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(148, 163, 184, 0.18)',
            showspikes=True,
            spikethickness=1,
            tickformat='.2f'
        ),
        yaxis2=dict(
            tickformat='.0f',
            showgrid=True,
            gridcolor='rgba(148, 163, 184, 0.18)'
        ),
        plot_bgcolor='#ffffff',
        paper_bgcolor='white',
        margin=dict(t=80, l=60, r=40, b=70)
    )

    # 隐藏周末空白（仅日K需要）
    if period == 'D':
        fig.update_xaxes(
            rangebreaks=[dict(bounds=['sat', 'mon'])],
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label='1M', step='month', stepmode='backward'),
                    dict(count=3, label='3M', step='month', stepmode='backward'),
                    dict(count=6, label='6M', step='month', stepmode='backward'),
                    dict(count=1, label='1Y', step='year', stepmode='backward'),
                    dict(step='all', label='ALL')
                ])
            )
        )

    return fig


def plot_kline_with_signals(df, symbol, signals, period='D'):
    """
    绘制带交易信号的K线图

    Args:
        df: K线DataFrame
        symbol: 股票代码
        signals: 信号序列 (1=买入, -1=卖出, 0=持仓)
        period: 'D' 日K, 'W' 周K, 'M' 月K, 'Y' 年K
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    df = df.copy()

    # 确保信号索引与日期对齐
    if len(signals) != len(df):
        # 如果长度不匹配，使用前n个
        signals = signals[:len(df)]

    # 创建子图：K线图 + 成交量 + 信号
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.55, 0.25, 0.20],
        subplot_titles=('', '成交量', '交易信号')
    )

    # K线 - 使用中国颜色惯例：红涨绿跌
    fig.add_trace(
        go.Candlestick(
            x=df['date'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='K线',
            increasing_line_color='#FF0000',
            decreasing_line_color='#00A000',
            increasing_fillcolor='#FF0000',
            decreasing_fillcolor='#00A000',
        ),
        row=1, col=1
    )

    # 添加MA均线
    if period == 'D':
        ma_periods = [5, 10, 20, 60]
        ma_labels = ['MA5', 'MA10', 'MA20', 'MA60']
    elif period == 'W':
        ma_periods = [5, 10, 20]
        ma_labels = ['MA5', 'MA10', 'MA20']
    elif period == 'M':
        ma_periods = [3, 6, 12]
        ma_labels = ['MA3', 'MA6', 'MA12']
    else:
        ma_periods = [3, 5]
        ma_labels = ['MA3', 'MA5']

    for ma_period, ma_label in zip(ma_periods, ma_labels):
        if len(df) >= ma_period:
            df[f'ma{ma_period}'] = df['close'].rolling(ma_period).mean()
            fig.add_trace(go.Scatter(
                x=df['date'], y=df[f'ma{ma_period}'],
                name=ma_label,
                line=dict(width=1.5)
            ), row=1, col=1)

    # 成交量柱状图
    colors = ['#FF0000' if c >= o else '#00A000' for c, o in zip(df['close'], df['open'])]
    fig.add_trace(
        go.Bar(
            x=df['date'],
            y=df['volume'],
            marker_color=colors,
            name='成交量',
            opacity=0.7
        ),
        row=2, col=1
    )

    # 计算买卖信号点
    # 信号变化检测：从-1到1是买入，从1到-1是卖出
    buy_signals = []
    sell_signals = []

    prev_signal = 0
    for i, (date, row) in enumerate(df.iterrows()):
        current_signal = signals.iloc[i] if hasattr(signals, 'iloc') else signals[i]

        # 买入信号：从前一个非1信号变为1
        if prev_signal != 1 and current_signal == 1:
            buy_signals.append({
                'date': date,
                'price': row['low'] * 0.98,  # 标记在K线下方
                'signal': 1
            })

        # 卖出信号：从前一个非-1信号变为-1
        if prev_signal != -1 and current_signal == -1:
            sell_signals.append({
                'date': date,
                'price': row['high'] * 1.02,  # 标记在K线上方
                'signal': -1
            })

        prev_signal = current_signal

    # 添加买入信号标记 (红色三角形▲) - 中国市场红色=涨=买入
    if buy_signals:
        fig.add_trace(
            go.Scatter(
                x=[s['date'] for s in buy_signals],
                y=[s['price'] for s in buy_signals],
                mode='markers+text',
                marker=dict(
                    symbol='triangle-up',
                    size=18,
                    color='#FF0000',  # 红色=买入
                    line=dict(width=2, color='#8B0000')
                ),
                text=['▲'] * len(buy_signals),
                textposition='bottom center',
                textfont=dict(color='#FF0000', size=12),
                name='买入信号',
                hovertemplate='买入信号<br>日期: %{x}<br>价格: ¥%{y:.2f}<extra></extra>'
            ),
            row=1, col=1
        )

    # 添加卖出信号标记 (绿色三角形▼) - 中国市场绿色=跌=卖出
    if sell_signals:
        fig.add_trace(
            go.Scatter(
                x=[s['date'] for s in sell_signals],
                y=[s['price'] for s in sell_signals],
                mode='markers+text',
                marker=dict(
                    symbol='triangle-down',
                    size=18,
                    color='#00A000',  # 绿色=卖出
                    line=dict(width=2, color='#006400')
                ),
                text=['▼'] * len(sell_signals),
                textposition='top center',
                textfont=dict(color='#00A000', size=12),
                name='卖出信号',
                hovertemplate='卖出信号<br>日期: %{x}<br>价格: ¥%{y:.2f}<extra></extra>'
            ),
            row=1, col=1
        )

    # 交易信号子图（显示-1, 0, 1信号）
    signal_colors = []
    for sig in signals:
        if sig == 1:
            signal_colors.append('#00A000')  # 绿色=买入
        elif sig == -1:
            signal_colors.append('#FF0000')  # 红色=卖出
        else:
            signal_colors.append('#E0E0E0')  # 灰色=持仓

    fig.add_trace(
        go.Bar(
            x=df['date'],
            y=signals,
            marker_color=signal_colors,
            name='信号',
            hovertemplate='信号值: %{y}<extra></extra>'
        ),
        row=3, col=1
    )

    # 更新信号子图布局
    fig.update_yaxes(range=[-1.5, 1.5], row=3, col=1)
    fig.update_yaxes(title_text='信号', row=3, col=1)

    period_names = {'D': '日K', 'W': '周K', 'M': '月K', 'Y': '年K'}

    # 更新布局
    fig.update_layout(
        title=dict(
            text=f'<b>{symbol}</b> {period_names.get(period, "K线")}走势（带交易信号）',
            x=0.5,
            font=dict(size=18)
        ),
        height=800,
        showlegend=True,
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1
        ),
        xaxis=dict(
            rangeslider=dict(visible=False),
            type='category',
            tickangle=45,
            showgrid=True,
            gridcolor='#E5E5E5'
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='#E5E5E5',
            tickformat='.2f'
        ),
        yaxis2=dict(
            tickformat='.0f',
            showgrid=True,
            gridcolor='#E5E5E5'
        ),
        yaxis3=dict(
            showgrid=True,
            gridcolor='#E5E5E5'
        ),
        plot_bgcolor='#FAFAFA',
        paper_bgcolor='white',
        margin=dict(t=80, l=60, r=40, b=60)
    )

    # 隐藏周末空白
    if period == 'D':
        fig.update_xaxes(
            rangebreaks=[dict(bounds=['sat', 'mon'])]
        )

    return fig


def plot_signals_only(df, symbol, signals):
    """
    简洁的交易信号柱状图
    横轴：日期，纵轴：-1（卖出）/ 0（持仓）/ 1（买入）

    Args:
        df: K线DataFrame
        symbol: 股票代码
        signals: 信号序列 (1=买入, -1=卖出, 0=持仓)
    """
    import plotly.graph_objects as go

    df = df.copy()

    if len(signals) != len(df):
        signals = signals[:len(df)]

    # 颜色：中国市场惯例 - 红涨(买)绿跌(卖)
    colors = ['#FF0000' if s == 1 else '#00A000' if s == -1 else '#CCCCCC' for s in signals]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df['date'],
        y=signals,
        marker_color=colors,
        hovertemplate='日期: %{x}<br>信号: %{y}<extra></extra>'
    ))

    # 参考线
    fig.add_hline(y=1, line_dash='dot', line_color='#FF0000', annotation_text='买入', annotation_position='top right')
    fig.add_hline(y=-1, line_dash='dot', line_color='#00A000', annotation_text='卖出', annotation_position='bottom right')
    fig.add_hline(y=0, line_dash='dash', line_color='gray')

    fig.update_layout(
        title=f'<b>{symbol}</b> 交易信号',
        height=250,
        showlegend=False,
        xaxis=dict(
            type='category',
            tickangle=45,
            showgrid=False,
            title='日期'
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='#E5E5E5',
            range=[-1.5, 1.5],
            tickvals=[-1, 0, 1],
            title='信号'
        ),
        plot_bgcolor='white',
        margin=dict(t=40, l=50, r=30, b=60)
    )

    fig.update_xaxes(rangebreaks=[dict(bounds=['sat', 'mon'])])
    return fig


def plot_multi_stock_signals(stock_data, signals, symbols):
    """
    多股票信号子图 - 每只股票一行，简洁展示

    Args:
        stock_data: dict, {symbol: df}
        signals: dict, {symbol: signal_series}
        symbols: list, 股票代码列表
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    n = min(len(symbols), 6)
    if n == 0:
        return None

    symbols = list(symbols)[:n]

    fig = make_subplots(
        rows=n, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=symbols,
        row_heights=[1/n] * n
    )

    for i, sym in enumerate(symbols, 1):
        if sym not in signals or sym not in stock_data:
            continue

        sig = signals[sym]
        df = stock_data[sym]

        if len(sig) != len(df):
            sig = sig[:len(df)]

        colors = ['#FF0000' if s == 1 else '#00A000' if s == -1 else '#CCCCCC' for s in sig]

        fig.add_trace(go.Bar(
            x=df['date'],
            y=sig,
            marker_color=colors,
            hovertemplate=f'{sym}<br>%{{x}}<br>信号: %{{y}}<extra></extra>'
        ), row=i, col=1)

        fig.update_yaxes(range=[-1.5, 1.5], tickvals=[-1, 0, 1], row=i, col=1)

    fig.update_layout(
        title='<b>多股票信号图</b> (红=买入, 绿=卖出)',
        height=max(300, 120 * n),
        showlegend=False,
        plot_bgcolor='white',
        margin=dict(t=40, l=50, r=30, b=60)
    )

    fig.update_xaxes(rangebreaks=[dict(bounds=['sat', 'mon'])], tickangle=45)
    return fig


def plot_signals_heatmap(signals, symbols, dates):
    """
    多股票信号热力图 - 日期×股票的信号强度矩阵

    Args:
        signals: dict, {symbol: signal_series}
        symbols: list, 股票代码列表
        dates: list, 日期列表
    """
    import plotly.graph_objects as go
    import numpy as np

    if not symbols or not dates:
        return None

    # 构建矩阵
    matrix = []
    for date in dates:
        row = []
        for sym in symbols:
            if sym in signals:
                sig = signals[sym]
                val = 0
                for i, d in enumerate(sig.index if hasattr(sig, 'index') else range(len(sig))):
                    d_str = str(d)[:10]
                    if d_str == str(date)[:10]:
                        val = sig.iloc[i] if hasattr(sig, 'iloc') else sig[i]
                        break
                row.append(val)
            else:
                row.append(0)
        matrix.append(row)

    fig = go.Figure(data=go.Heatmap(
        z=np.array(matrix),
        x=list(symbols),
        y=[str(d)[:10] for d in dates],
        colorscale=[[0, '#00A000'], [0.5, '#E0E0E0'], [1, '#FF0000']],
        zmid=0,
        colorbar=dict(title='信号', tickvals=[-1, 0, 1], ticktext=['卖', '持仓', '买']),
        hovertemplate='%{y}<br>%{x}<br>信号: %{z}<extra></extra>'
    ))

    fig.update_layout(
        title='<b>信号热力图</b> (红=买入, 绿=卖出)',
        height=max(300, 20 * len(dates)),
        margin=dict(t=40, l=100, r=30, b=80)
    )

    return fig


def export_signals_to_csv(signals, symbols, output_path='signals_export.csv'):
    """
    导出信号数据到CSV文件

    Args:
        signals: dict, {symbol: signal_series}
        symbols: list, 股票代码列表
        output_path: str, 输出文件路径
    """
    import pandas as pd

    records = []
    for sym in symbols:
        if sym not in signals:
            continue
        sig = signals[sym]
        for i, (date, val) in enumerate(sig.items() if hasattr(sig, 'items') else enumerate(sig)):
            records.append({
                '股票代码': sym,
                '日期': str(date)[:10],
                '信号': val,
                '信号描述': '买入' if val == 1 else ('卖出' if val == -1 else '持仓')
            })

    df = pd.DataFrame(records)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    return output_path


# Tab 1: 自选股管理（包含行情展示）
with tab1:
    if 'watchlist_view_mode' not in st.session_state:
        st.session_state.watchlist_view_mode = 'list'

    all_watchlist_stocks = wl_manager.get_all_stocks()
    all_watchlist_symbols = [s.symbol for s in all_watchlist_stocks]
    if all_watchlist_symbols and st.session_state.get('selected_stock') not in all_watchlist_symbols:
        st.session_state['selected_stock'] = all_watchlist_symbols[0]

    # 详情页：全宽显示K线和指标，并提供返回按钮
    if st.session_state.watchlist_view_mode == 'detail' and st.session_state.get('selected_stock'):
        selected_stock = st.session_state['selected_stock']
        st.markdown(
            """
            <div class="market-page-title">
                <div class="main">📈 行情详情终端</div>
                <div class="sub">多周期K线 · 关键指标 · 明细数据</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        toolbar_col1, toolbar_col2, toolbar_col3 = st.columns([1, 2, 1])
        with toolbar_col1:
            if st.button("← 返回自选股列表", use_container_width=True):
                st.session_state.watchlist_view_mode = 'list'
                st.rerun()
        with toolbar_col2:
            if all_watchlist_symbols:
                selected_stock = st.selectbox(
                    "切换股票",
                    options=all_watchlist_symbols,
                    index=all_watchlist_symbols.index(selected_stock) if selected_stock in all_watchlist_symbols else 0,
                    key="detail_symbol_selector"
                )
                st.session_state['selected_stock'] = selected_stock
        with toolbar_col3:
            if st.button("刷新数据", use_container_width=True):
                with st.spinner("正在更新行情数据..."):
                    dm.update_recent_data([selected_stock], days=5)
                st.rerun()

        st.subheader(f"📊 {selected_stock} 行情详情")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=365*3)
        with st.spinner(f"正在加载 {selected_stock} 数据..."):
            df = dm.get_daily_kline(
                selected_stock,
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d")
            )

        if not df.empty:
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            change = latest['close'] - prev['close']
            change_pct = (change / prev['close'] * 100) if prev['close'] != 0 else 0
            color_class = "positive" if change >= 0 else "negative"

            metrics_col1, metrics_col2, metrics_col3, metrics_col4, metrics_col5 = st.columns(5)
            with metrics_col1:
                st.markdown("<div class='metric-label'>最新价</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='metric-value {color_class}'>{latest['close']:.2f}</div>", unsafe_allow_html=True)
            with metrics_col2:
                st.markdown("<div class='metric-label'>涨跌额</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='metric-value {color_class}'>{change:+.2f}</div>", unsafe_allow_html=True)
            with metrics_col3:
                st.markdown("<div class='metric-label'>涨跌幅</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='metric-value {color_class}'>{change_pct:+.2f}%</div>", unsafe_allow_html=True)
            with metrics_col4:
                st.markdown("<div class='metric-label'>成交量</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='metric-value'>{latest['volume']/10000:.0f}万</div>", unsafe_allow_html=True)
            with metrics_col5:
                st.markdown("<div class='metric-label'>成交额</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='metric-value'>{latest['amount']/100000000:.2f}亿</div>", unsafe_allow_html=True)

            st.divider()
            kline_period = st.radio(
                "K线周期",
                ["日K", "周K", "月K", "年K"],
                horizontal=True,
                index=0,
                key="kline_period_selector"
            )
            period_map = {"日K": "D", "周K": "W", "月K": "M", "年K": "Y"}
            period_code = period_map[kline_period]
            df_display = resample_kline(df, period_code) if period_code != "D" else df.copy()

            fig = plot_kline(df_display, selected_stock, period=period_code)
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("📋 查看数据表格"):
                st.dataframe(df.sort_values('date', ascending=False).head(50), use_container_width=True)
        else:
            st.error(f"无法获取 {selected_stock} 的数据")
    else:
        # 列表页：全宽展示，适配大量股票
        st.markdown(
            """
            <div class="market-page-title">
                <div class="main">📋 自选股交易看板</div>
                <div class="sub">集中管理股票池，快速筛选并一键进入行情详情</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.subheader("📋 自选股列表")

        with st.expander("➕ 添加自选股", expanded=False):
            new_symbol = st.text_input("股票代码", value="", placeholder="如: 000001.SH（上证指数）或 000001.SZ（平安银行）")
            new_name = st.text_input("股票名称", value="", placeholder="如: 平安银行")
            new_group = st.selectbox("分组", ["默认", "持仓股", "银行", "消费", "科技", "医药", "新能源", "自定义"])
            if new_group == "自定义":
                new_group = st.text_input("自定义分组名")
            if st.button("添加", key="add_stock"):
                if new_symbol:
                    symbol = new_symbol.strip()
                    name = new_name.strip() if new_name.strip() else symbol
                    success = wl_manager.add_stock(symbol, name, new_group)
                    if success:
                        st.success(f"✅ 已添加 {symbol}")
                        st.rerun()
                    else:
                        st.error("添加失败")
                else:
                    st.warning("请输入股票代码")

        groups = wl_manager.get_groups()
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        with filter_col1:
            selected_group = st.selectbox("筛选分组", ["全部"] + groups)
        with filter_col2:
            page_size = st.selectbox("每页条数", [12, 20, 30, 50], index=1)
        with filter_col3:
            sort_by = st.selectbox(
                "排序方式",
                ["涨跌幅从高到低", "涨跌幅从低到高", "成交量从高到低", "代码升序"],
                index=0
            )
        keyword = st.text_input("搜索代码/名称", value="", placeholder="输入代码或名称关键字")

        all_group_stocks = wl_manager.get_all_stocks() if selected_group == "全部" else wl_manager.get_stocks_by_group(selected_group)
        keyword_lower = keyword.strip().lower()
        stocks = [
            s for s in all_group_stocks
            if not keyword_lower or keyword_lower in s.symbol.lower() or keyword_lower in s.name.lower()
        ]

        if not stocks:
            st.info("暂无匹配的自选股，请调整筛选条件。")
        else:
            stock_rows = []
            up_count, down_count, flat_count = 0, 0, 0
            for stock in stocks:
                quote = get_latest_quote(stock.symbol)
                pct_change = quote['pct_change'] if quote else None
                close_price = quote['close'] if quote else None
                volume_wan = (quote['volume'] / 10000) if quote else None
                stock_rows.append({
                    'symbol': stock.symbol,
                    'name': stock.name,
                    'group': stock.group,
                    'close': close_price,
                    'pct_change': pct_change,
                    'volume_wan': volume_wan
                })
                if pct_change is not None:
                    if pct_change > 0:
                        up_count += 1
                    elif pct_change < 0:
                        down_count += 1
                    else:
                        flat_count += 1

            st.markdown(
                f"""
                <div class="watchlist-overview">
                    <div class="item"><div class="label">股票总数</div><div class="value">{len(stock_rows)}</div></div>
                    <div class="item"><div class="label">上涨</div><div class="value positive">{up_count}</div></div>
                    <div class="item"><div class="label">下跌</div><div class="value negative">{down_count}</div></div>
                    <div class="item"><div class="label">平盘</div><div class="value">{flat_count}</div></div>
                </div>
                """,
                unsafe_allow_html=True
            )

            st.markdown(
                f"""
                <div class="market-toolbar">
                    <div class="label">当前筛选条件</div>
                    <div class="value">分组：{selected_group} ｜ 排序：{sort_by} ｜ 关键字：{keyword if keyword else '无'}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

            if sort_by == "涨跌幅从高到低":
                stock_rows = sorted(stock_rows, key=lambda r: (r['pct_change'] is None, -(r['pct_change'] if r['pct_change'] is not None else -999)))
            elif sort_by == "涨跌幅从低到高":
                stock_rows = sorted(stock_rows, key=lambda r: (r['pct_change'] is None, (r['pct_change'] if r['pct_change'] is not None else 999)))
            elif sort_by == "成交量从高到低":
                stock_rows = sorted(stock_rows, key=lambda r: (r['volume_wan'] is None, -(r['volume_wan'] if r['volume_wan'] is not None else -999)))
            else:
                stock_rows = sorted(stock_rows, key=lambda r: r['symbol'])

            total_rows = len(stock_rows)
            total_pages = max((total_rows + page_size - 1) // page_size, 1)
            if 'watchlist_page' not in st.session_state:
                st.session_state.watchlist_page = 1
            filter_signature = f"{selected_group}|{keyword_lower}|{sort_by}|{page_size}|{total_rows}"
            if st.session_state.get("watchlist_filter_signature") != filter_signature:
                st.session_state["watchlist_filter_signature"] = filter_signature
                st.session_state.watchlist_page = 1
            st.session_state.watchlist_page = max(1, min(st.session_state.watchlist_page, total_pages))

            page_ctrl_col1, page_ctrl_col2, page_ctrl_col3 = st.columns([1, 2, 1])
            with page_ctrl_col1:
                if st.button("◀ 上一页", disabled=st.session_state.watchlist_page <= 1, use_container_width=True):
                    st.session_state.watchlist_page -= 1
                    st.rerun()
            with page_ctrl_col2:
                st.caption(f"第 {st.session_state.watchlist_page}/{total_pages} 页 · 共 {total_rows} 只")
            with page_ctrl_col3:
                if st.button("下一页 ▶", disabled=st.session_state.watchlist_page >= total_pages, use_container_width=True):
                    st.session_state.watchlist_page += 1
                    st.rerun()

            start_idx = (st.session_state.watchlist_page - 1) * page_size
            end_idx = start_idx + page_size
            page_rows = stock_rows[start_idx:end_idx]

            table_df = pd.DataFrame([
                {
                    '代码': row['symbol'],
                    '名称': row['name'],
                    '最新价': row['close'],
                    '涨跌幅(%)': row['pct_change'],
                    '成交量(万)': row['volume_wan'],
                    '分组': row['group']
                } for row in page_rows
            ])

            fmt_map = {
                '最新价': lambda x: "-" if pd.isna(x) else f"{x:.2f}",
                '涨跌幅(%)': lambda x: "-" if pd.isna(x) else f"{x:+.2f}",
                '成交量(万)': lambda x: "-" if pd.isna(x) else f"{x:.1f}",
            }
            interactive_df = table_df.copy()
            interactive_df['涨跌幅(%)'] = interactive_df['涨跌幅(%)'].apply(
                lambda x: "-" if pd.isna(x) else f"{x:+.2f}"
            )
            interactive_df['最新价'] = interactive_df['最新价'].apply(
                lambda x: "-" if pd.isna(x) else f"{x:.2f}"
            )
            interactive_df['成交量(万)'] = interactive_df['成交量(万)'].apply(
                lambda x: "-" if pd.isna(x) else f"{x:.1f}"
            )

            table_event = st.dataframe(
                interactive_df,
                use_container_width=True,
                hide_index=True,
                height=520,
                on_select="rerun",
                selection_mode="single-row"
            )
            st.markdown("<div class='table-caption'>点击任意行可直接进入该股票行情详情页</div>", unsafe_allow_html=True)

            selected_rows = []
            if isinstance(table_event, dict):
                selected_rows = table_event.get("selection", {}).get("rows", [])
            elif hasattr(table_event, "selection") and hasattr(table_event.selection, "rows"):
                selected_rows = table_event.selection.rows
            if selected_rows:
                selected_idx = selected_rows[0]
                if 0 <= selected_idx < len(page_rows):
                    st.session_state['selected_stock'] = page_rows[selected_idx]['symbol']
                    st.session_state.watchlist_view_mode = 'detail'
                    st.rerun()

            all_symbols = [r['symbol'] for r in stock_rows]
            current_view_symbol = st.session_state.get('selected_stock', all_symbols[0] if all_symbols else None)
            if current_view_symbol not in all_symbols and all_symbols:
                current_view_symbol = all_symbols[0]

            action_col1, action_col2 = st.columns(2)
            with action_col1:
                if current_view_symbol and st.button("删除当前股票", use_container_width=True):
                    success = wl_manager.remove_stock(current_view_symbol)
                    if success:
                        st.success(f"已删除 {current_view_symbol}")
                        st.session_state.pop('selected_stock', None)
                        st.rerun()
                    else:
                        st.error("删除失败")
            with action_col2:
                if st.button("导出本组", use_container_width=True):
                    st.session_state['multi_stock_symbols'] = all_symbols
                    st.success(f"已选择 {len(all_symbols)} 只股票用于回测")

# Tab 2: 策略回测
with tab2:
    render_section_title("策略回测", "🎯", "支持单股/组合回测与参数化策略配置")

    # 回测参数设置（移到主区域）
    with st.expander("⚙️ 回测参数设置", expanded=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.subheader("📊 股票选择（勾选参与回测）")

            # 获取自选股列表
            all_watchlist_stocks = filter_out_benchmark_stocks(wl_manager.get_all_stocks())

            if all_watchlist_stocks:
                # 初始化session_state中的选中状态
                if 'backtest_selected_stocks' not in st.session_state:
                    st.session_state['backtest_selected_stocks'] = {s.symbol for s in all_watchlist_stocks}

                # 全选/取消全选
                col_sel_all, col_count = st.columns([1, 3])
                with col_sel_all:
                    select_all = st.checkbox("全选", value=True, key="select_all_stocks")
                with col_count:
                    st.caption(f"已选 {len(st.session_state['backtest_selected_stocks'])} 只")

                # 复选框列表选择股票
                selected_stocks = set()
                for stock in all_watchlist_stocks:
                    is_selected = st.checkbox(
                        f"{stock.symbol} {stock.name}",
                        value=stock.symbol in st.session_state['backtest_selected_stocks'],
                        key=f"stock_cb_{stock.symbol}"
                    )
                    if is_selected:
                        selected_stocks.add(stock.symbol)

                # 更新session_state
                st.session_state['backtest_selected_stocks'] = selected_stocks

                # 显示选中的股票代码列表
                if selected_stocks:
                    st.success(f"✅ 选中了 {len(selected_stocks)} 只股票: {', '.join(sorted(selected_stocks))}")
                else:
                    st.warning("⚠️ 请至少选择一只股票")
            else:
                st.info("暂无可回测自选股（默认指数已自动排除），请先添加股票")

            start_date = st.date_input("开始日期", value=pd.to_datetime("2023-01-01"))
            end_date = st.date_input("结束日期", value=datetime.now().date())

        with col2:
            st.subheader("🎯 策略选择")
            strategy_name = st.selectbox(
                "选择策略",
                ["均线交叉 (MA Cross)", "MACD", "布林带 (Bollinger Bands)", "RSI"]
            )

            # 策略参数（非多因子策略）
            if strategy_name == "均线交叉 (MA Cross)":
                fast_period = st.slider("短期均线", 5, 60, 20)
                slow_period = st.slider("长期均线", 10, 120, 60)
                strategy_params = {'fast_period': fast_period, 'slow_period': slow_period}
            elif strategy_name == "MACD":
                fast = st.slider("快线周期", 5, 20, 12)
                slow = st.slider("慢线周期", 15, 40, 26)
                signal = st.slider("信号线周期", 5, 15, 9)
                strategy_params = {'fast': fast, 'slow': slow, 'signal': signal}
            elif strategy_name == "布林带 (Bollinger Bands)":
                period = st.slider("周期", 10, 50, 20)
                std_dev = st.slider("标准差倍数", 1.0, 3.0, 2.0, 0.1)
                strategy_params = {'period': period, 'std_dev': std_dev}
            elif strategy_name == "RSI":
                period = st.slider("RSI周期", 5, 30, 14)
                oversold = st.slider("超卖阈值", 10, 40, 30)
                overbought = st.slider("超买阈值", 60, 90, 70)
                strategy_params = {'period': period, 'oversold': oversold, 'overbought': overbought}
            else:
                strategy_params = {}

        with col3:
            st.subheader("💰 资金参数")
            initial_capital = st.number_input("初始资金", value=1000000, step=100000)
            commission_rate = st.number_input(
                "手续费率",
                value=0.0003,
                min_value=0.0001,
                max_value=0.005,
                step=0.0001,
                format="%.4f"
            )

            # 多股票参数（选中多只时显示）
            if 'backtest_selected_stocks' in st.session_state and len(st.session_state['backtest_selected_stocks']) > 1:
                st.divider()
                st.subheader("📈 组合参数")
                max_positions = st.number_input("最大持仓数", value=5, min_value=1, max_value=20)
                rebalance_days = st.number_input("调仓周期(天)", value=5, min_value=1, max_value=30)
                position_method = st.selectbox(
                    "仓位分配方法",
                    ["equal", "risk_parity", "momentum", "score", "kelly"],
                    index=0,
                    format_func=lambda x: {
                        "equal": "等权重",
                        "risk_parity": "风险平价",
                        "momentum": "动量加权",
                        "score": "综合打分",
                        "kelly": "凯利公式"
                    }[x]
                )

                col4, col5 = st.columns(2)
                with col4:
                    max_single = st.slider("单只最大仓位", 0, 20, 20, 1, format="%.0f%%") / 100
                with col5:
                    max_total = st.slider("最大总仓位", 0, 100, 80, 5, format="%.0f%%") / 100

                # 止损参数
                stop_loss = st.number_input(
                    "止损比例（%）",
                    value=0,
                    min_value=0,
                    max_value=50,
                    help="亏损超过此比例时自动止损平仓，如输入10表示亏损10%时止损。0表示不止损"
                ) / 100  # 转换为小数
            else:
                max_positions = 1
                rebalance_days = 5
                position_method = "equal"
                max_single = 0.2
                max_total = 0.8
                stop_loss = 0

    # 运行回测按钮
    if st.button("🚀 运行回测", key="run_backtest", type="primary"):
        selected_stocks = st.session_state.get('backtest_selected_stocks', set())

        if not selected_stocks:
            st.warning("请至少选择一只股票进行回测")
        else:
            run_config = build_run_config(
                selected_stocks=selected_stocks,
                strategy_name=strategy_name,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                commission_rate=commission_rate,
                max_positions=max_positions,
                rebalance_days=rebalance_days,
                position_method=position_method,
                max_single_position=max_single,
                max_total_position=max_total,
                stop_loss=stop_loss,
                strategy_params=strategy_params,
                session_state=st.session_state,
            )
            run_config["symbols"] = filter_out_benchmark_symbols(run_config.get("symbols", []))

            config_errors = validate_run_config(run_config)
            if config_errors:
                for err in config_errors:
                    st.error(err)
            else:
                with st.spinner(
                    f"正在运行{'单股票' if run_config['is_single_stock'] else '多股票'}"
                    f"{'多因子' if run_config['is_multi_factor'] else run_config['strategy_name']}回测..."
                ):
                    stock_data = load_backtest_stock_data(
                        dm.db_path,
                        run_config["symbols"],
                        run_config["start_date_str"],
                        run_config["end_date_str"],
                    )

                    if len(stock_data) == 0:
                        st.error("所有股票都没有获取到数据!")
                    else:
                        # ==================== 多因子回测模式 ====================
                        if run_config["is_multi_factor"]:
                            run_result = run_multi_factor_strategy_backtest(
                                symbols=run_config["symbols"],
                                stock_data=stock_data,
                                start_date=run_config["start_date_str"],
                                end_date=run_config["end_date_str"],
                                initial_capital=run_config["initial_capital"],
                                max_positions=run_config["max_positions"],
                                rebalance_days=run_config["rebalance_days"],
                                factor_weights=run_config["mf_factor_weights"],
                                use_ic_weighting=run_config["mf_use_ic"],
                                ic_update_freq=run_config["mf_ic_update_freq"],
                                commission_rate=run_config["commission_rate"],
                                max_single_position=run_config["max_single_position"],
                                max_total_position=run_config["max_total_position"],
                                stop_loss=run_config["stop_loss"],
                            )

                            if run_result.get("error"):
                                st.warning(run_result["error"]) if "配置" in run_result["error"] else st.error(run_result["error"])
                                if run_result.get("traceback"):
                                    st.code(run_result["traceback"])
                            else:
                                results = run_result["results"]

                                st.session_state['multi_backtest_results'] = results
                                st.session_state['is_multi_factor_backtest'] = True

                                render_multi_factor_results(results, len(stock_data))

                        # ==================== 普通策略回测模式 ====================
                        else:
                            run_result = run_standard_strategy_backtest(
                                stock_data=stock_data,
                                strategy_name=run_config["strategy_name"],
                                strategy_params=run_config["strategy_params"],
                                start_date=run_config["start_date_str"],
                                end_date=run_config["end_date_str"],
                                initial_capital=run_config["initial_capital"],
                                commission_rate=run_config["commission_rate"],
                                max_positions=run_config["max_positions"],
                                rebalance_days=run_config["rebalance_days"],
                                position_method=run_config["position_method"],
                                max_single_position=run_config["max_single_position"],
                                max_total_position=run_config["max_total_position"],
                                stop_loss=run_config["stop_loss"],
                            )

                            for warning_msg in run_result.get("warnings", []):
                                st.warning(warning_msg)

                            if run_result.get("error"):
                                st.error(run_result["error"])
                            else:
                                results = run_result["results"]
                                signals = run_result["signals"]
                                engine = run_result["engine"]

                                st.session_state['multi_backtest_results'] = results
                                st.session_state['is_multi_factor_backtest'] = False

                                render_standard_results(
                                    results=results,
                                    stock_data=stock_data,
                                    signals=signals,
                                    engine=engine,
                                    plot_multi_stock_signals=plot_multi_stock_signals,
                                    plot_signals_heatmap=plot_signals_heatmap,
                                    export_signals_to_csv=export_signals_to_csv,
                                )

# Tab 3: 财务数据管理
with tab3:
    render_data_management_page()

# Tab 4: 因子分析
with tab4:
    render_factor_analysis_page(dm, wl_manager)

# Tab 5: 多因子回测
with tab5:
    render_factor_backtest_page(dm, wl_manager)

# Tab 6: 信号扫描
with tab6:
    render_section_title("信号扫描", "📈", "按策略批量扫描买卖信号并导出结果")

    # 顶部控制面板
    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([1, 1, 1])

    with col_ctrl1:
        st.subheader("🎯 策略选择")
        scan_strategy = st.selectbox(
            "选择策略",
            ["均线交叉 (MA Cross)", "MACD", "布林带 (Bollinger Bands)", "RSI", "多因子 (Multi-Factor)"],
            key="scan_strategy"
        )

        # 策略参数
        if scan_strategy == "均线交叉 (MA Cross)":
            scan_fast_period = st.slider("短期均线", 5, 60, 20, key="scan_fast_period")
            scan_slow_period = st.slider("长期均线", 10, 120, 60, key="scan_slow_period")
            scan_params = {'fast_period': scan_fast_period, 'slow_period': scan_slow_period}
        elif scan_strategy == "MACD":
            scan_fast = st.slider("快线周期", 5, 20, 12, key="scan_fast")
            scan_slow = st.slider("慢线周期", 15, 40, 26, key="scan_slow")
            scan_signal = st.slider("信号线周期", 5, 15, 9, key="scan_signal_period")
            scan_params = {'fast': scan_fast, 'slow': scan_slow, 'signal': scan_signal}
        elif scan_strategy == "布林带 (Bollinger Bands)":
            scan_bb_period = st.slider("周期", 10, 50, 20, key="scan_bb_period")
            scan_std_dev = st.slider("标准差倍数", 1.0, 3.0, 2.0, 0.1, key="scan_std_dev")
            scan_params = {'period': scan_bb_period, 'std_dev': scan_std_dev}
        elif scan_strategy == "RSI":
            scan_rsi_period = st.slider("RSI周期", 5, 30, 14, key="scan_rsi_period")
            scan_oversold = st.slider("超卖阈值", 10, 40, 30, key="scan_oversold")
            scan_overbought = st.slider("超买阈值", 60, 90, 70, key="scan_overbought")
            scan_params = {'period': scan_rsi_period, 'oversold': scan_oversold, 'overbought': scan_overbought}
        else:
            scan_params = {}

    with col_ctrl2:
        st.subheader("📋 扫描范围")
        # 获取自选股列表
        all_watchlist_stocks = wl_manager.get_all_stocks()

        if all_watchlist_stocks:
            # 初始化选中状态
            if 'scan_selected_stocks' not in st.session_state:
                st.session_state['scan_selected_stocks'] = {s.symbol for s in all_watchlist_stocks}

            # 全选/取消全选
            col_sel_all, col_count = st.columns([1, 3])
            with col_sel_all:
                scan_select_all = st.checkbox("全选", value=True, key="scan_select_all")
            with col_count:
                st.caption(f"已选 {len(st.session_state['scan_selected_stocks'])} 只")

            # 复选框列表
            scan_selected = set()
            for stock in all_watchlist_stocks:
                is_selected = st.checkbox(
                    f"{stock.symbol} {stock.name}",
                    value=stock.symbol in st.session_state['scan_selected_stocks'],
                    key=f"scan_cb_{stock.symbol}"
                )
                if is_selected:
                    scan_selected.add(stock.symbol)

            st.session_state['scan_selected_stocks'] = scan_selected
        else:
            st.info("暂无自选股，请先在【自选股管理】中添加")
            scan_selected = set()

        # 时间范围
        scan_start_date = st.date_input("开始日期", value=pd.to_datetime("2024-01-01"), key="scan_start_date")
        scan_end_date = st.date_input("结束日期", value=pd.to_datetime("2024-12-31"), key="scan_end_date")

    with col_ctrl3:
        st.subheader("🔍 信号筛选")
        scan_signal_filter = st.radio(
            "显示信号",
            ["全部信号", "仅买入", "仅卖出", "仅持仓"],
            horizontal=True,
            key="scan_signal_filter"
        )

        # 信号类型映射
        signal_filter_map = {
            "全部信号": "all",
            "仅买入": "buy",
            "仅卖出": "sell",
            "仅持仓": "hold"
        }

        st.divider()

        # 扫描按钮
        scan_button = st.button("🔍 开始扫描", type="primary", use_container_width=True)

    # 显示扫描结果
    if scan_button:
        selected_stocks = st.session_state.get('scan_selected_stocks', set())

        if not selected_stocks:
            st.warning("请至少选择一只股票进行扫描")
        else:
            with st.spinner("正在扫描信号..."):
                # 创建扫描器
                scanner = SignalScanner()

                # 执行扫描
                scan_result = scanner.scan(
                    symbols=list(selected_stocks),
                    strategy_name=scan_strategy,
                    strategy_params=scan_params,
                    start_date=scan_start_date.strftime("%Y-%m-%d"),
                    end_date=scan_end_date.strftime("%Y-%m-%d")
                )

                # 保存到session_state
                st.session_state['scan_result'] = scan_result

    # 显示扫描结果
    if 'scan_result' in st.session_state and st.session_state['scan_result'] is not None:
        scan_result = st.session_state['scan_result']

        # 统计卡片
        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
        with stat_col1:
            st.metric("扫描股票数", scan_result.total_stocks)
        with stat_col2:
            st.metric("买入信号", scan_result.buy_signals, delta="🟢")
        with stat_col3:
            st.metric("卖出信号", scan_result.sell_signals, delta="🔴")
        with stat_col4:
            st.metric("持仓信号", scan_result.hold_signals, delta="⚪")

        st.divider()

        # 获取过滤后的信号
        filtered_df = scan_result.get_filtered_signals(signal_filter_map.get(scan_signal_filter, "all"))
        result_df = scan_result.to_dataframe()

        # 应用筛选
        if scan_signal_filter != "全部信号":
            result_df = result_df[result_df['信号类型'] == signal_filter_map.get(scan_signal_filter, "all")]

        if not result_df.empty:
            # 格式化显示
            st.subheader(f"📋 信号列表 ({len(result_df)} 只)")

            # 颜色标记函数
            def color_signal_type(val):
                if val == 'buy':
                    return 'color: #dc3545; font-weight: bold'  # 红色
                elif val == 'sell':
                    return 'color: #28a745; font-weight: bold'  # 绿色
                return ''

            def color_change(val):
                if isinstance(val, (int, float)):
                    if val > 0:
                        return 'color: #dc3545'  # 红色涨
                    elif val < 0:
                        return 'color: #28a745'  # 绿色跌
                return ''

            # 应用样式
            display_df = result_df.copy()
            styled_df = display_df.style.applymap(color_signal_type, subset=['信号类型'])
            styled_df = styled_df.applymap(color_change, subset=['涨跌幅'])
            styled_df = styled_df.format({
                '最新价': '{:.2f}',
                '涨跌幅': '{:+.2f}%',
                '信号强度': '{:.1f}'
            }, na_rep='-')

            st.dataframe(styled_df, use_container_width=True, hide_index=True)

            # 导出按钮
            if st.button("📥 导出信号到CSV"):
                try:
                    output_path = f"scan_signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    result_df.to_csv(output_path, index=False, encoding='utf-8-sig')
                    st.success(f"✅ 信号已导出到: {output_path}")
                except Exception as e:
                    st.error(f"导出失败: {e}")

            # 详细信号展示
            st.divider()
            st.subheader("📈 信号详情")

            # 按信号类型分组展示
            buy_signals_list = [s for s in filtered_df if s.signal_type == 'buy'] if isinstance(filtered_df, list) else []
            sell_signals_list = [s for s in filtered_df if s.signal_type == 'sell'] if isinstance(filtered_df, list) else []

            # 买入信号详情
            if scan_signal_filter in ["全部信号", "仅买入"] and scan_result.buy_signals > 0:
                st.markdown("**🟢 买入信号:**")
                for sig in scan_result.signals:
                    if sig.signal_type == 'buy':
                        with st.expander(f"{sig.name} ({sig.symbol}) - ★{sig.strength:.1f}"):
                            col_sig1, col_sig2 = st.columns([1, 2])
                            with col_sig1:
                                st.write(f"**价格:** {sig.price:.2f}")
                                st.write(f"**涨跌幅:** {sig.change_pct:+.2f}%")
                                st.write(f"**信号日期:** {sig.date}")
                            with col_sig2:
                                st.write(f"**策略:** {sig.strategy_name}")
                                st.write(f"**原因:** {sig.reason}")
                                if sig.indicators:
                                    st.write(f"**指标:** {sig.indicators}")

            # 卖出信号详情
            if scan_signal_filter in ["全部信号", "仅卖出"] and scan_result.sell_signals > 0:
                st.markdown("**🔴 卖出信号:**")
                for sig in scan_result.signals:
                    if sig.signal_type == 'sell':
                        with st.expander(f"{sig.name} ({sig.symbol}) - ★{sig.strength:.1f}"):
                            col_sig1, col_sig2 = st.columns([1, 2])
                            with col_sig1:
                                st.write(f"**价格:** {sig.price:.2f}")
                                st.write(f"**涨跌幅:** {sig.change_pct:+.2f}%")
                                st.write(f"**信号日期:** {sig.date}")
                            with col_sig2:
                                st.write(f"**策略:** {sig.strategy_name}")
                                st.write(f"**原因:** {sig.reason}")
                                if sig.indicators:
                                    st.write(f"**指标:** {sig.indicators}")
        else:
            st.info("没有符合条件的信号")

# Tab 7: 绩效分析
with tab7:
    render_section_title("绩效分析", "📉", "汇总回测表现并沉淀关键风险收益指标")
    st.info("请选择要分析的回测结果")

# 页脚
st.markdown("---")
st.markdown("<center>量化交易系统 v1.0 | 仅供学习研究使用</center>", unsafe_allow_html=True)

if __name__ == "__main__":
    pass

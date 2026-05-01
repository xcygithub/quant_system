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

from data.data_manager import DataManager
from portfolio.watchlist import WatchlistManager
from portfolio.signal_scanner import SignalScanner, ScanResult, ScanSignal
from web.factor_backtest_page import render_factor_backtest_page, FACTOR_CATEGORIES, DEFAULT_FACTORS
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

# 自定义样式
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stock-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        border-left: 4px solid #1f77b4;
    }
    .stock-card:hover {
        background-color: #e9ecef;
        cursor: pointer;
    }
    .positive {
        color: #dc3545 !important;  /* A股红色表示涨 */
    }
    .negative {
        color: #28a745 !important;  /* A股绿色表示跌 */
    }
    .metric-value {
        font-size: 1.5rem;
        font-weight: bold;
    }
    .metric-label {
        font-size: 0.875rem;
        color: #6c757d;
    }
</style>
""", unsafe_allow_html=True)

# 初始化数据管理器
@st.cache_resource
def get_data_manager():
    manager = DataManager()
    print(f"[CONFIG] 当前数据库路径: {manager.db_path}")
    return manager

dm = get_data_manager()

# 初始化自选股管理器
@st.cache_resource
def get_watchlist_manager():
    return WatchlistManager()

wl_manager = get_watchlist_manager()

# 主页面
st.markdown('<h1 class="main-header">📈 量化交易系统</h1>', unsafe_allow_html=True)

# 创建标签页
# 7个标签页：自选股管理、策略回测、多因子回测、信号扫描、绩效分析、因子分析、财务数据管理
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "⭐ 自选股管理",
    "🎯 策略回测",
    "📊 多因子回测",
    "📈 信号扫描",
    "📉 绩效分析",
    "🔬 因子分析",
    "📥 财务数据管理"
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

    # 周期标题
    period_names = {'D': '日K', 'W': '周K', 'M': '月K', 'Y': '年K'}

    # 更新布局
    fig.update_layout(
        title=dict(
            text=f'<b>{symbol}</b> {period_names.get(period, "K线")}走势',
            x=0.5,
            font=dict(size=18)
        ),
        height=600,
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
        plot_bgcolor='#FAFAFA',
        paper_bgcolor='white',
        margin=dict(t=80, l=60, r=40, b=60)
    )

    # 隐藏周末空白（仅日K需要）
    if period == 'D':
        fig.update_xaxes(
            rangebreaks=[dict(bounds=['sat', 'mon'])]
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
    st.header("⭐ 自选股管理")
    
    # 创建两列布局：左侧自选股列表，右侧行情展示
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.subheader("📋 自选股列表")
        
        # 添加自选股
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
        
        # 分组筛选
        groups = wl_manager.get_groups()
        selected_group = st.selectbox("筛选分组", ["全部"] + groups)
        
        # 获取股票列表
        if selected_group == "全部":
            stocks = wl_manager.get_all_stocks()
        else:
            stocks = wl_manager.get_stocks_by_group(selected_group)
        
        if stocks:
            # 显示股票卡片列表
            for stock in stocks:
                # 获取最新行情
                quote = get_latest_quote(stock.symbol)
                
                if quote:
                    price_color = "positive" if quote['pct_change'] >= 0 else "negative"
                    change_sign = "+" if quote['pct_change'] >= 0 else ""
                    
                    # 创建可点击的股票卡片
                    card_html = f"""
                    <div class="stock-card" onclick="">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <strong>{stock.symbol}</strong> 
                                <span style="color: #6c757d; font-size: 0.875rem;">{stock.name}</span>
                                <span style="background: #e9ecef; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px;">{stock.group}</span>
                            </div>
                            <div style="text-align: right;">
                                <div class="metric-value">{quote['close']:.2f}</div>
                                <div class="{price_color}">{change_sign}{quote['pct_change']:.2f}%</div>
                            </div>
                        </div>
                    </div>
                    """
                    st.markdown(card_html, unsafe_allow_html=True)
                    
                    # 使用按钮实现点击效果
                    if st.button(f"查看 {stock.symbol}", key=f"view_{stock.symbol}"):
                        # 只更新当前选中股票最近5天的数据（不包括今天）
                        # 先查数据库，如果有数据就不从baostock获取
                        with st.spinner("正在更新行情数据..."):
                            dm.update_recent_data([stock.symbol], days=5)
                        st.session_state['selected_stock'] = stock.symbol
                        st.rerun()
                else:
                    st.info(f"{stock.symbol} - {stock.name} (暂无行情数据)")
            
            # 操作按钮
            st.divider()
            
            # 删除股票
            selected_for_delete = st.selectbox("选择要删除的股票", [""] + [s.symbol for s in stocks], key="delete_select")
            if selected_for_delete and st.button("🗑️ 删除选中股票"):
                success = wl_manager.remove_stock(selected_for_delete)
                if success:
                    st.success(f"已删除 {selected_for_delete}")
                    if st.session_state.get('selected_stock') == selected_for_delete:
                        del st.session_state['selected_stock']
                    st.rerun()
            
            # 导出为多股票回测列表
            if st.button("📥 导出全部为多股票回测列表"):
                symbol_list = [s.symbol for s in stocks]
                st.session_state['multi_stock_symbols'] = symbol_list
                st.success(f"已选择 {len(symbol_list)} 只股票用于回测")
        else:
            st.info("暂无自选股，请先添加")
    
    with col_right:
        # 右侧显示选中股票的详细行情
        selected_stock = st.session_state.get('selected_stock')
        
        if selected_stock:
            st.subheader(f"📊 {selected_stock} 行情详情")
            
            # 获取3年日线数据
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365*3)  # 3年
            
            with st.spinner(f"正在加载 {selected_stock} 数据..."):
                df = dm.get_daily_kline(
                    selected_stock, 
                    start_date.strftime("%Y-%m-%d"), 
                    end_date.strftime("%Y-%m-%d")
                )
            
            if not df.empty:
                # 显示最新行情指标
                latest = df.iloc[-1]
                prev = df.iloc[-2] if len(df) > 1 else latest
                
                change = latest['close'] - prev['close']
                change_pct = (change / prev['close'] * 100) if prev['close'] != 0 else 0
                color_class = "positive" if change >= 0 else "negative"
                
                # 显示关键指标
                metrics_col1, metrics_col2, metrics_col3, metrics_col4, metrics_col5 = st.columns(5)
                
                with metrics_col1:
                    st.markdown(f"<div class='metric-label'>最新价</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='metric-value {color_class}'>{latest['close']:.2f}</div>", unsafe_allow_html=True)
                
                with metrics_col2:
                    st.markdown(f"<div class='metric-label'>涨跌额</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='metric-value {color_class}'>{change:+.2f}</div>", unsafe_allow_html=True)
                
                with metrics_col3:
                    st.markdown(f"<div class='metric-label'>涨跌幅</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='metric-value {color_class}'>{change_pct:+.2f}%</div>", unsafe_allow_html=True)
                
                with metrics_col4:
                    st.markdown(f"<div class='metric-label'>成交量</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='metric-value'>{latest['volume']/10000:.0f}万</div>", unsafe_allow_html=True)
                
                with metrics_col5:
                    st.markdown(f"<div class='metric-label'>成交额</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='metric-value'>{latest['amount']/100000000:.2f}亿</div>", unsafe_allow_html=True)
                
                st.divider()

                # K线周期选择
                kline_period = st.radio(
                    "K线周期",
                    ["日K", "周K", "月K", "年K"],
                    horizontal=True,
                    index=0,
                    key="kline_period_selector"
                )

                # 根据选择的周期处理数据
                period_map = {"日K": "D", "周K": "W", "月K": "M", "年K": "Y"}
                period_code = period_map[kline_period]

                # 如果不是日K，需要重采样
                if period_code != "D":
                    df_display = resample_kline(df, period_code)
                else:
                    df_display = df.copy()

                # 显示K线图
                fig = plot_kline(df_display, selected_stock, period=period_code)
                st.plotly_chart(fig, use_container_width=True)
                
                # 显示数据表格
                with st.expander("📋 查看数据表格"):
                    st.dataframe(df.sort_values('date', ascending=False).head(50), use_container_width=True)
            else:
                st.error(f"无法获取 {selected_stock} 的数据")
        else:
            # 未选中股票时，显示所有自选股的最新行情概览
            st.subheader("📈 自选股行情概览")
            
            if stocks:
                quotes_data = []
                for stock in stocks:
                    quote = get_latest_quote(stock.symbol)
                    if quote:
                        quotes_data.append({
                            '股票代码': stock.symbol,
                            '股票名称': stock.name,
                            '最新价': quote['close'],
                            '涨跌额': quote['close'] - quote['open'],
                            '涨跌幅': quote['pct_change'],
                            '成交量(万)': quote['volume'] / 10000,
                            '分组': stock.group
                        })
                
                if quotes_data:
                    quotes_df = pd.DataFrame(quotes_data)

                    # 使用pandas的format功能保留两位小数（Streamlit的st.dataframe需要这样格式化）
                    float_format = lambda x: f'{x:.2f}'
                    styled_df = quotes_df.style.format({
                        '最新价': float_format,
                        '涨跌额': float_format,
                        '涨跌幅': float_format,
                        '成交量(万)': float_format
                    }, na_rep='-')

                    # 使用样式突出涨跌
                    def highlight_change(val):
                        if isinstance(val, (int, float)):
                            if val > 0:
                                return 'color: #dc3545'  # 红色表示涨
                            elif val < 0:
                                return 'color: #28a745'  # 绿色表示跌
                        return ''

                    styled_df = styled_df.applymap(highlight_change, subset=['涨跌额', '涨跌幅'])
                    st.dataframe(styled_df, use_container_width=True, hide_index=True)
                else:
                    st.info("暂无行情数据")
            else:
                st.info("请先添加自选股")

# Tab 2: 策略回测
with tab2:
    st.header("🎯 策略回测")

    # 回测参数设置（移到主区域）
    with st.expander("⚙️ 回测参数设置", expanded=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.subheader("📊 股票选择（勾选参与回测）")

            # 获取自选股列表
            all_watchlist_stocks = wl_manager.get_all_stocks()

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
                st.info("暂无自选股，请先在【自选股管理】中添加")

            start_date = st.date_input("开始日期", value=pd.to_datetime("2023-01-01"))
            end_date = st.date_input("结束日期", value=pd.to_datetime("2024-12-31"))

        with col2:
            st.subheader("🎯 策略选择")
            strategy_name = st.selectbox(
                "选择策略",
                ["均线交叉 (MA Cross)", "MACD", "布林带 (Bollinger Bands)", "RSI", "多因子 (Multi-Factor)"]
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

            # 多因子配置面板（当选择多因子时显示）
            if strategy_name == "多因子 (Multi-Factor)":
                st.divider()
                st.markdown("**📊 因子配置**")

                # 初始化session_state
                if 'mf_backtest_factors' not in st.session_state:
                    st.session_state.mf_backtest_factors = {}

                # 因子选择
                selected_factors = {}
                for category, factors in FACTOR_CATEGORIES.items():
                    with st.expander(f"☑️ {category}", expanded=True):
                        default_selected = [f for f in DEFAULT_FACTORS.get(category, []) if f in factors]
                        selected = st.multiselect(
                            "选择因子",
                            list(factors.keys()),
                            default=default_selected,
                            format_func=lambda x: factors[x],
                            key=f"mf_factor_{category}"
                        )
                        for f in selected:
                            selected_factors[f] = category

                # 权重设置模式
                weight_mode = st.radio(
                    "权重模式",
                    ["🤖 IC智能加权", "✏️ 手动设置"],
                    index=0,
                    horizontal=True,
                    key="mf_weight_mode"
                )

                mf_factor_weights = {}
                if weight_mode == "✏️ 手动设置":
                    st.markdown("**因子权重**")
                    cols = st.columns(2)
                    factor_list = list(selected_factors.keys())
                    for i, factor in enumerate(factor_list):
                        with cols[i % 2]:
                            category = selected_factors[factor]
                            factor_display = FACTOR_CATEGORIES[category].get(factor, factor)
                            w = st.slider(
                                factor_display,
                                0.0, 1.0, 0.2, 0.05,
                                key=f"mf_weight_{factor}"
                            )
                            mf_factor_weights[factor] = w

                    # 归一化
                    if mf_factor_weights and sum(mf_factor_weights.values()) > 0:
                        total = sum(mf_factor_weights.values())
                        mf_factor_weights = {k: v/total for k, v in mf_factor_weights.items()}
                        st.caption(f"权重已归一化 (总和={sum(mf_factor_weights.values()):.2%})")
                else:
                    # IC加权模式参数
                    mf_ic_update_freq = st.slider(
                        "IC更新频率（天）", 20, 120, 60, 10,
                        key="mf_ic_update_freq"
                    )
                    mf_ic_lookback = st.slider(
                        "IC历史窗口（天）", 60, 252, 120, 20,
                        key="mf_ic_lookback"
                    )
                    # 生成等权基础权重
                    mf_factor_weights = {f: 1.0/len(selected_factors) if selected_factors else 0 for f in selected_factors}

                # 保存因子配置到session_state
                st.session_state.mf_backtest_factors = selected_factors
                st.session_state.mf_factor_weights = mf_factor_weights
                st.session_state.mf_use_ic = (weight_mode == "🤖 IC智能加权")

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

# Tab 3: 多因子回测
with tab3:
    render_factor_backtest_page(dm, wl_manager)

# Tab 4: 信号扫描
with tab4:
    st.header("📈 信号扫描")

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

# Tab 5: 绩效分析
with tab5:
    st.header("📉 绩效分析")
    st.info("请选择要分析的回测结果")

# Tab 6: 因子分析
with tab6:
    render_factor_analysis_page(dm, wl_manager)

# Tab 7: 财务数据管理
with tab7:
    render_data_management_page()

# 页脚
st.markdown("---")
st.markdown("<center>量化交易系统 v1.0 | 仅供学习研究使用</center>", unsafe_allow_html=True)

if __name__ == "__main__":
    pass

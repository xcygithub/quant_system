"""
量化交易系统 Web 界面
基于 Streamlit 的交互式分析界面
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from quant_system.data.data_manager import DataManager
from quant_system.data.factor_data import FactorData
from quant_system.backtest.engine import VectorizedBacktest
from quant_system.backtest.performance import PerformanceAnalyzer
from quant_system.strategy.moving_average import MovingAverageCrossStrategy, MACDStrategy, BollingerBandsStrategy
from quant_system.strategy.multi_factor import MultiFactorStrategy, RSIStrategy
from quant_system.portfolio.watchlist import WatchlistManager
from quant_system.portfolio.multi_stock_backtest import MultiStockBacktest

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
    return DataManager()

dm = get_data_manager()

# 初始化自选股管理器
@st.cache_resource
def get_watchlist_manager():
    return WatchlistManager()

wl_manager = get_watchlist_manager()

# 主页面
st.markdown('<h1 class="main-header">📈 量化交易系统</h1>', unsafe_allow_html=True)

# 创建标签页
# 注意：tab2(自选股)会包含行情展示功能，所以原tab1(行情数据)可以简化或合并
tab1, tab2, tab3, tab4 = st.tabs(["⭐ 自选股管理", "🎯 策略回测", "📈 绩效分析", "🔬 因子分析"])

# 辅助函数：获取最近交易日行情
def get_latest_quote(symbol):
    """获取股票最近一个交易日的行情数据"""
    try:
        # 获取最近30天的数据
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        df = dm.get_daily_kline(symbol, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))

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

# Tab 1: 自选股管理（包含行情展示）
with tab1:
    st.header("⭐ 自选股管理")
    
    # 创建两列布局：左侧自选股列表，右侧行情展示
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.subheader("📋 自选股列表")
        
        # 添加自选股
        with st.expander("➕ 添加自选股", expanded=False):
            new_symbol = st.text_input("股票代码", value="", placeholder="如: 000001.SZ")
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
                    
                    # 使用样式突出涨跌
                    def highlight_change(val):
                        if isinstance(val, (int, float)):
                            if val > 0:
                                return 'color: #dc3545'  # 红色表示涨
                            elif val < 0:
                                return 'color: #28a745'  # 绿色表示跌
                        return ''
                    
                    styled_df = quotes_df.style.applymap(highlight_change, subset=['涨跌额', '涨跌幅'])
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
            st.subheader("📊 股票选择")
            symbol_input = st.text_input("股票代码", value="000001.SZ", placeholder="如: 000001.SZ")
            start_date = st.date_input("开始日期", value=pd.to_datetime("2023-01-01"))
            end_date = st.date_input("结束日期", value=pd.to_datetime("2024-12-31"))
        
        with col2:
            st.subheader("🎯 策略选择")
            strategy_name = st.selectbox(
                "选择策略",
                ["均线交叉 (MA Cross)", "MACD", "布林带 (Bollinger Bands)", "RSI", "多因子 (Multi-Factor)"]
            )
            
            # 策略参数
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
    
    # 多股票/单股票切换
    backtest_mode = st.radio(
        "回测模式",
        ["单股票回测", "多股票回测"],
        horizontal=True,
        index=0
    )
    
    # 多股票选项
    if backtest_mode == "多股票回测":
        st.info("💡 多股票回测将使用自选股列表中的股票进行组合投资回测")
        
        # 检查是否有选中的自选股
        if 'multi_stock_symbols' in st.session_state and st.session_state['multi_stock_symbols']:
            symbols = st.session_state['multi_stock_symbols']
            st.success(f"✅ 已加载 {len(symbols)} 只自选股: {', '.join(symbols)}")
        else:
            st.warning("⚠️ 请先在【自选股管理】标签页中选择股票并导出")
        
        # 多股票回测参数
        col1, col2, col3 = st.columns(3)
        with col1:
            max_positions = st.number_input("最大持仓数", value=5, min_value=1, max_value=20)
        with col2:
            rebalance_days = st.number_input("调仓周期(天)", value=5, min_value=1, max_value=30)
        with col3:
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
    
    if st.button("🚀 运行回测", key="run_backtest", type="primary"):
        if backtest_mode == "多股票回测":
            # 多股票回测逻辑...
            if 'multi_stock_symbols' not in st.session_state or not st.session_state['multi_stock_symbols']:
                st.warning("请先在【自选股管理】标签页中选择股票")
            else:
                with st.spinner("正在运行多股票回测..."):
                    symbols = st.session_state['multi_stock_symbols']
                    
                    # 获取数据并生成信号
                    stock_data = {}
                    signals = {}
                    
                    for sym in symbols:
                        df = dm.get_daily_kline(sym, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
                        if not df.empty:
                            stock_data[sym] = df
                            
                            # 生成信号
                            try:
                                factor_data = FactorData(df)
                                df_with_factors = factor_data.calculate_all_factors()
                                
                                if strategy_name == "均线交叉 (MA Cross)":
                                    strat = MovingAverageCrossStrategy(strategy_params)
                                elif strategy_name == "MACD":
                                    strat = MACDStrategy(strategy_params)
                                elif strategy_name == "布林带 (Bollinger Bands)":
                                    strat = BollingerBandsStrategy(strategy_params)
                                elif strategy_name == "RSI":
                                    strat = RSIStrategy(strategy_params)
                                else:
                                    strat = MultiFactorStrategy(strategy_params)
                                
                                signal_series = strat.get_signal_series(df_with_factors)
                                # 关键：设置信号索引为日期
                                if 'date' in df.columns:
                                    signal_series.index = pd.to_datetime(df['date'])
                                signals[sym] = signal_series
                            except Exception as e:
                                st.warning(f"{sym} 信号计算失败: {e}")
                    
                    if len(stock_data) == 0:
                        st.error("所有股票都没有获取到数据!")
                    else:
                        # 运行多股票回测
                        engine = MultiStockBacktest(
                            initial_capital=initial_capital,
                            commission_rate=commission_rate,
                            max_positions=max_positions,
                            rebalance_days=rebalance_days,
                            position_method=position_method,
                            max_single_position=max_single,
                            max_total_position=max_total
                        )
                        
                        engine.set_data(stock_data, signals)
                        results = engine.run(
                            start_date.strftime("%Y-%m-%d"),
                            end_date.strftime("%Y-%m-%d")
                        )
                        
                        st.session_state['multi_backtest_results'] = results
                        
                        st.success(f"✅ 多股票回测完成! 共回测 {len(stock_data)} 只股票")
                        
                        # 显示结果
                        if results:
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("总收益率", f"{results['total_return']:.2%}")
                            with col2:
                                st.metric("年化收益率", f"{results['annual_return']:.2%}")
                            with col3:
                                st.metric("夏普比率", f"{results['sharpe_ratio']:.2f}")
                            with col4:
                                st.metric("最大回撤", f"{results['max_drawdown']:.2%}")
                            
                            # 显示权益曲线
                            equity_df = results.get('equity_curve')
                            if equity_df is not None and not equity_df.empty:
                                fig = go.Figure()
                                fig.add_trace(go.Scatter(
                                    x=equity_df['date'],
                                    y=equity_df['total_value'],
                                    name='组合净值',
                                    line=dict(color='blue')
                                ))
                                fig.update_layout(
                                    title='多股票组合权益曲线',
                                    xaxis_title='日期',
                                    yaxis_title='净值',
                                    height=400
                                )
                                st.plotly_chart(fig, use_container_width=True)
                            
                            # 显示交易记录
                            trades_df = engine.get_trades_df()
                            if not trades_df.empty:
                                st.subheader("交易记录")
                                st.dataframe(trades_df, use_container_width=True, hide_index=True)
        else:
            # 单股票回测
            with st.spinner("正在运行回测..."):
                df = dm.get_daily_kline(symbol_input, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
                
                if df.empty:
                    st.error(f"无法获取 {symbol_input} 的数据")
                else:
                    # 计算因子
                    factor_data = FactorData(df)
                    df_with_factors = factor_data.calculate_all_factors()
                    
                    # 创建策略
                    if strategy_name == "均线交叉 (MA Cross)":
                        strategy = MovingAverageCrossStrategy(strategy_params)
                    elif strategy_name == "MACD":
                        strategy = MACDStrategy(strategy_params)
                    elif strategy_name == "布林带 (Bollinger Bands)":
                        strategy = BollingerBandsStrategy(strategy_params)
                    elif strategy_name == "RSI":
                        strategy = RSIStrategy(strategy_params)
                    else:
                        strategy = MultiFactorStrategy(strategy_params)
                    
                    # 运行回测
                    engine = VectorizedBacktest(df_with_factors, strategy)
                    results = engine.run(
                        initial_capital=initial_capital,
                        commission_rate=commission_rate
                    )
                    
                    # 显示结果
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("总收益率", f"{results['total_return']:.2%}")
                    with col2:
                        st.metric("年化收益率", f"{results['annual_return']:.2%}")
                    with col3:
                        st.metric("夏普比率", f"{results['sharpe_ratio']:.2f}")
                    with col4:
                        st.metric("最大回撤", f"{results['max_drawdown']:.2%}")
                    
                    # 绘制权益曲线
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=results['equity_curve']['date'],
                        y=results['equity_curve']['total_value'],
                        name='账户净值'
                    ))
                    fig.update_layout(title='权益曲线', xaxis_title='日期', yaxis_title='净值')
                    st.plotly_chart(fig, use_container_width=True)

# Tab 3: 绩效分析
with tab3:
    st.header("📈 绩效分析")
    st.info("请选择要分析的回测结果")

# Tab 4: 因子分析
with tab4:
    st.header("🔬 因子分析")
    st.info("因子分析功能开发中...")

# 页脚
st.markdown("---")
st.markdown("<center>量化交易系统 v1.0 | 仅供学习研究使用</center>", unsafe_allow_html=True)

if __name__ == "__main__":
    pass

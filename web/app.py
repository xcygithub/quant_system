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

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from quant_system.data.data_manager import DataManager
from quant_system.data.factor_data import FactorData
from quant_system.backtest.engine import VectorizedBacktest
from quant_system.backtest.performance import PerformanceAnalyzer
from quant_system.strategy.moving_average import MovingAverageCrossStrategy, MACDStrategy, BollingerBandsStrategy
from quant_system.strategy.multi_factor import MultiFactorStrategy, RSIStrategy

# 页面配置
st.set_page_config(
    page_title="量化交易系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
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
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .positive {
        color: #28a745;
    }
    .negative {
        color: #dc3545;
    }
</style>
""", unsafe_allow_html=True)

# 初始化数据管理器
@st.cache_resource
def get_data_manager():
    return DataManager()

dm = get_data_manager()

# 侧边栏
st.sidebar.title("⚙️ 参数设置")

# 股票选择
st.sidebar.subheader("📊 股票选择")
symbol = st.sidebar.text_input("股票代码", value="000001")
start_date = st.sidebar.date_input("开始日期", value=pd.to_datetime("2023-01-01"))
end_date = st.sidebar.date_input("结束日期", value=pd.to_datetime("2024-12-31"))

# 策略选择
st.sidebar.subheader("🎯 策略选择")
strategy_name = st.sidebar.selectbox(
    "选择策略",
    ["均线交叉 (MA Cross)", "MACD", "布林带 (Bollinger Bands)", "RSI", "多因子 (Multi-Factor)"]
)

# 策略参数
st.sidebar.subheader("🔧 策略参数")
if strategy_name == "均线交叉 (MA Cross)":
    fast_period = st.sidebar.slider("短期均线", 5, 60, 20)
    slow_period = st.sidebar.slider("长期均线", 10, 120, 60)
    strategy_params = {'fast_period': fast_period, 'slow_period': slow_period}
elif strategy_name == "MACD":
    fast = st.sidebar.slider("快线周期", 5, 20, 12)
    slow = st.sidebar.slider("慢线周期", 15, 40, 26)
    signal = st.sidebar.slider("信号线周期", 5, 15, 9)
    strategy_params = {'fast': fast, 'slow': slow, 'signal': signal}
elif strategy_name == "布林带 (Bollinger Bands)":
    period = st.sidebar.slider("周期", 10, 50, 20)
    std_dev = st.sidebar.slider("标准差倍数", 1.0, 3.0, 2.0, 0.1)
    strategy_params = {'period': period, 'std_dev': std_dev}
elif strategy_name == "RSI":
    period = st.sidebar.slider("RSI周期", 5, 30, 14)
    oversold = st.sidebar.slider("超卖阈值", 10, 40, 30)
    overbought = st.sidebar.slider("超买阈值", 60, 90, 70)
    strategy_params = {'period': period, 'oversold': oversold, 'overbought': overbought}
else:
    strategy_params = {}

# 数据源选择
st.sidebar.subheader("📡 数据源")
data_source_option = st.sidebar.selectbox(
    "选择数据源",
    ["自动 (优先真实数据)", "本地CSV文件", "仅模拟数据"],
    index=0
)
use_csv = (data_source_option == "本地CSV文件")
use_simulated_only = (data_source_option == "仅模拟数据")

# 显示CSV文件说明
if use_csv:
    st.sidebar.info("请在 stock_data 目录下放置CSV文件\n格式: 601919.csv")
    st.sidebar.text("CSV列: date,open,high,low,close,volume")

# 回测参数
st.sidebar.subheader("💰 回测参数")
initial_capital = st.sidebar.number_input("初始资金", value=1000000, step=100000)
commission_rate = st.sidebar.number_input(
    "手续费率", 
    value=0.0003, 
    min_value=0.0001, 
    max_value=0.005, 
    step=0.0001,
    format="%.4f",
    help="单边手续费率，如 0.0003 表示万分之三"
)

# 主页面
st.markdown('<h1 class="main-header">📈 量化交易系统</h1>', unsafe_allow_html=True)

# 创建标签页
tab1, tab2, tab3, tab4 = st.tabs(["📊 行情数据", "🎯 策略回测", "📈 绩效分析", "🔬 因子分析"])

# Tab 1: 行情数据
with tab1:
    st.header("行情数据")
    
    if st.button("获取数据", key="get_data"):
        with st.spinner("正在获取数据..."):
            try:
                start_date_str = start_date.strftime("%Y-%m-%d")
                end_date_str = end_date.strftime("%Y-%m-%d")
                st.info(f"正在获取 {symbol} 从 {start_date_str} 到 {end_date_str} 的数据...")
                
                # 根据用户选择使用不同的数据源
                if use_csv:
                    from quant_system.data.data_sources import CSVDataSource
                    csv_source = CSVDataSource()
                    df = csv_source.get_daily_kline(symbol, start_date_str, end_date_str)
                    st.info("使用本地CSV数据源")
                elif use_simulated_only:
                    from quant_system.data.data_sources import SimulatedDataSource
                    sim_source = SimulatedDataSource()
                    df = sim_source.get_daily_kline(symbol, start_date_str, end_date_str)
                    st.info("使用模拟数据源")
                else:
                    df = dm.get_daily_kline(symbol, start_date_str, end_date_str)
                
                if not df.empty:
                    st.session_state['data'] = df
                    
                    # 检查是否为模拟数据
                    is_simulated = 'data_source' in df.columns and df['data_source'].iloc[0] == 'simulated'
                    if is_simulated:
                        st.warning(f"⚠️ 使用模拟数据（网络连接失败）- 共 {len(df)} 条")
                    else:
                        st.success(f"✅ 成功获取 {len(df)} 条数据")
                    
                    # 显示数据表格
                    st.subheader("数据预览")
                    st.dataframe(df.head(20), use_container_width=True)
                    
                    # K线图
                    fig = go.Figure(data=[go.Candlestick(
                        x=df['date'],
                        open=df['open'],
                        high=df['high'],
                        low=df['low'],
                        close=df['close'],
                        name='K线'
                    )])
                    
                    fig.update_layout(
                        title=f"{symbol} K线图",
                        yaxis_title="价格",
                        xaxis_title="日期",
                        height=500
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 成交量图
                    fig_vol = go.Figure(data=[go.Bar(
                        x=df['date'],
                        y=df['volume'],
                        name='成交量',
                        marker_color='blue'
                    )])
                    
                    fig_vol.update_layout(
                        title="成交量",
                        yaxis_title="成交量",
                        height=300
                    )
                    
                    st.plotly_chart(fig_vol, use_container_width=True)
                else:
                    st.error("❌ 获取数据失败")
                    st.info("请检查：\n1. 股票代码是否正确（如：000001、601919）\n2. 网络连接是否正常\n3. akshare 是否正常工作")
            except Exception as e:
                st.error(f"获取数据时发生错误: {str(e)}")
                import traceback
                st.code(traceback.format_exc())

# Tab 2: 策略回测
with tab2:
    st.header("策略回测")
    
    if st.button("运行回测", key="run_backtest"):
        if 'data' not in st.session_state:
            st.warning("请先获取数据")
        else:
            with st.spinner("正在运行回测..."):
                df = st.session_state['data'].copy()
                
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
                engine = VectorizedBacktest(
                    initial_capital=initial_capital,
                    commission_rate=commission_rate
                )
                
                signal_series = strategy.get_signal_series(df)
                results = engine.run(df, signal_series)
                
                st.session_state['backtest_results'] = results
                st.session_state['signals'] = signal_series
                
                st.success("回测完成！")
                
                # 显示权益曲线
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                   vertical_spacing=0.1,
                                   subplot_titles=('权益曲线', '信号'))
                
                fig.add_trace(
                    go.Scatter(x=df['date'], y=results['equity_curve']['strategy_equity'],
                              name='策略', line=dict(color='blue')),
                    row=1, col=1
                )
                
                fig.add_trace(
                    go.Scatter(x=df['date'], y=results['equity_curve']['market_equity'],
                              name='基准', line=dict(color='gray')),
                    row=1, col=1
                )
                
                fig.add_trace(
                    go.Scatter(x=df['date'], y=signal_series,
                              name='信号', mode='lines',
                              line=dict(color='red')),
                    row=2, col=1
                )
                
                fig.update_layout(height=600, showlegend=True)
                st.plotly_chart(fig, use_container_width=True)

# Tab 3: 绩效分析
with tab3:
    st.header("绩效分析")
    
    if 'backtest_results' in st.session_state:
        results = st.session_state['backtest_results']
        
        # 关键指标
        col1, col2, col3, col4 = st.columns(4)
        
        total_return = results['total_return']
        annual_return = results['annual_return']
        sharpe = results['sharpe_ratio']
        max_dd = results['max_drawdown']
        
        with col1:
            st.metric("总收益率", f"{total_return:.2%}", 
                     delta=f"{total_return:.2%}",
                     delta_color="normal")
        
        with col2:
            st.metric("年化收益率", f"{annual_return:.2%}")
        
        with col3:
            st.metric("夏普比率", f"{sharpe:.2f}")
        
        with col4:
            st.metric("最大回撤", f"{max_dd:.2%}")
        
        # 详细指标
        st.subheader("详细指标")
        
        # 安全获取指标值
        total_return = results.get('total_return', 0)
        annual_return = results.get('annual_return', 0)
        volatility = results.get('volatility', 0)
        sharpe_ratio = results.get('sharpe_ratio', 0)
        max_drawdown = results.get('max_drawdown', 0)
        win_rate = results.get('win_rate', 0)
        
        metrics_data = {
            '指标': ['总收益率', '年化收益率', '年化波动率', '夏普比率', 
                    '最大回撤', '胜率'],
            '数值': [
                f"{total_return:.2%}",
                f"{annual_return:.2%}",
                f"{volatility:.2%}",
                f"{sharpe_ratio:.2f}",
                f"{max_drawdown:.2%}",
                f"{win_rate:.2%}"
            ]
        }
        
        st.table(pd.DataFrame(metrics_data))
        
        # 收益分布
        st.subheader("收益分布")
        returns = results['returns'].dropna()
        
        fig = go.Figure(data=[go.Histogram(x=returns, nbinsx=50)])
        fig.update_layout(
            title="日收益率分布",
            xaxis_title="收益率",
            yaxis_title="频数",
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # 交易明细表格
        if 'trades' in results and len(results['trades']) > 0:
            st.subheader("交易明细")
            
            trades = results['trades']
            
            # 构建交易明细DataFrame
            trades_data = []
            for trade in trades:
                # 计算持有时间（自然日和交易日）
                entry_dt = pd.to_datetime(trade['entry_date'])
                
                # 检查是否未平仓
                is_open_position = (trade.get('status') == 'open' or trade['exit_date'] == '持有中')
                
                if is_open_position:
                    # 未平仓: 持有天数计算到回测最后一天
                    holding_calendar_days = trade['holding_days']
                    holding_time_str = f"{holding_calendar_days}天(持有中)"
                    exit_date_display = "持有中"
                    exit_price_display = f"{trade['exit_price']:.2f}"
                    profit_label = "浮动盈亏"
                else:
                    # 已平仓: 正常计算
                    exit_dt = pd.to_datetime(trade['exit_date'])
                    holding_calendar_days = (exit_dt - entry_dt).days
                    holding_trading_days = int(holding_calendar_days * 5 / 7)
                    holding_time_str = f"{holding_calendar_days}天(约{holding_trading_days}交易日)"
                    exit_date_display = trade['exit_date']
                    exit_price_display = f"{trade['exit_price']:.2f}"
                    profit_label = "收益金额"
                
                trades_data.append({
                    '交易编号': trade['trade_id'],
                    '状态': '持有中' if is_open_position else '已平仓',
                    '买入日期': trade['entry_date'],
                    '买入价格': f"{trade['entry_price']:.2f}",
                    '买入数量': int(trade['entry_quantity']),
                    '买入金额': f"{trade['entry_value']:.2f}",
                    '卖出日期': exit_date_display,
                    '卖出价格': exit_price_display,
                    '卖出数量': int(trade['exit_quantity']),
                    '卖出金额': f"{trade['exit_value']:.2f}",
                    '持有天数': trade['holding_days'],
                    '持有时间': holding_time_str,
                    '收益率': f"{trade['return_rate']:.2%}",
                    '净收益率': f"{trade['net_return_rate']:.2%}",
                    profit_label: f"{trade['profit']:.2f}",
                    '手续费': f"{trade['commission']:.2f}"
                })
            
            trades_df = pd.DataFrame(trades_data)
            
            # 使用st.dataframe显示,支持排序和筛选
            st.dataframe(
                trades_df,
                use_container_width=True,
                height=400
            )
            
            # 交易统计
            st.subheader("交易统计")
            
            col1, col2, col3, col4 = st.columns(4)
            
            total_trades = len(trades)
            winning_trades = len([t for t in trades if t['net_return_rate'] > 0])
            losing_trades = total_trades - winning_trades
            win_rate = winning_trades / total_trades if total_trades > 0 else 0
            
            avg_return = np.mean([t['net_return_rate'] for t in trades])
            max_return = max([t['net_return_rate'] for t in trades]) if trades else 0
            min_return = min([t['net_return_rate'] for t in trades]) if trades else 0
            avg_holding_days = np.mean([t['holding_days'] for t in trades]) if trades else 0
            
            with col1:
                st.metric("总交易次数", total_trades)
            
            with col2:
                st.metric("盈利次数", winning_trades)
            
            with col3:
                st.metric("亏损次数", losing_trades)
            
            with col4:
                st.metric("胜率", f"{win_rate:.2%}")
            
            col5, col6, col7, col8 = st.columns(4)
            
            with col5:
                st.metric("平均收益率", f"{avg_return:.2%}")
            
            with col6:
                st.metric("最大单笔收益", f"{max_return:.2%}")
            
            with col7:
                st.metric("最大单笔亏损", f"{min_return:.2%}")
            
            with col8:
                st.metric("平均持有天数", f"{avg_holding_days:.1f}")
    else:
        st.info("请先运行回测")

# Tab 4: 因子分析
with tab4:
    st.header("因子分析")
    
    if 'data' in st.session_state:
        df = st.session_state['data'].copy()
        
        # 计算因子
        with st.spinner("正在计算因子..."):
            factor_data = FactorData(df)
            df_with_factors = factor_data.calculate_all_factors()
        
        # 选择要显示的因子
        available_factors = [col for col in df_with_factors.columns 
                           if col not in ['date', 'open', 'high', 'low', 'close', 'volume', 'amount']]
        
        selected_factors = st.multiselect(
            "选择要显示的因子",
            available_factors,
            default=['sma_20', 'rsi_14', 'macd']
        )
        
        if selected_factors:
            # 绘制因子图
            fig = make_subplots(
                rows=len(selected_factors) + 1,
                cols=1,
                shared_xaxes=True,
                vertical_spacing=0.05,
                subplot_titles=['价格'] + selected_factors
            )
            
            # 价格
            fig.add_trace(
                go.Scatter(x=df_with_factors['date'], y=df_with_factors['close'],
                          name='收盘价', line=dict(color='black')),
                row=1, col=1
            )
            
            # 各因子
            for i, factor in enumerate(selected_factors, 2):
                fig.add_trace(
                    go.Scatter(x=df_with_factors['date'], 
                              y=df_with_factors[factor],
                              name=factor, mode='lines'),
                    row=i, col=1
                )
            
            fig.update_layout(height=200 * (len(selected_factors) + 2), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        
        # 因子相关性
        st.subheader("因子相关性")
        
        if len(selected_factors) > 1:
            corr_matrix = df_with_factors[selected_factors].corr()
            
            fig = go.Figure(data=go.Heatmap(
                z=corr_matrix.values,
                x=corr_matrix.columns,
                y=corr_matrix.columns,
                colorscale='RdBu',
                zmin=-1,
                zmax=1
            ))
            
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("请先获取数据")

# 页脚
st.markdown("---")
st.markdown("<center>量化交易系统 v1.0 | 仅供学习研究使用</center>", unsafe_allow_html=True)

if __name__ == "__main__":
    pass

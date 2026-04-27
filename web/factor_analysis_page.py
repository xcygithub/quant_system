"""
因子分析页面
提供基本面因子的计算、查询和展示功能
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from quant_system.strategy.fundamental_factors import FundamentalFactors
from quant_system.portfolio.watchlist import WatchlistManager
from quant_system.data.data_manager import DataManager
from quant_system.web.factor_presenter import FactorPresenter


# =============================================================================
# 页面渲染函数
# =============================================================================

def render_factor_analysis_page(dm: DataManager, wl_manager: WatchlistManager):
    """
    渲染因子分析页面

    Args:
        dm: DataManager 实例
        wl_manager: WatchlistManager 实例
    """
    st.header("🔬 因子分析")

    # 初始化 session state
    _init_factor_session_state()

    # 渲染布局：左侧计算区 + 右侧展示区
    col_left, col_right = st.columns([1, 2])

    with col_left:
        _render_calc_section(dm, wl_manager)

    with col_right:
        _render_display_section(dm, wl_manager)


def _init_factor_session_state():
    """初始化因子分析页面的 session state"""
    if 'factor_selected_symbol' not in st.session_state:
        st.session_state.factor_selected_symbol = None
    if 'factor_calc_results' not in st.session_state:
        st.session_state.factor_calc_results = {}
    if 'factor_last_calc_time' not in st.session_state:
        st.session_state.factor_last_calc_time = None


# =============================================================================
# 左侧：计算区
# =============================================================================

def _render_calc_section(dm: DataManager, wl_manager: WatchlistManager):
    """渲染因子计算区域"""
    st.subheader("📊 因子计算")

    # 获取自选股列表
    watchlist = wl_manager.get_all_stocks()
    watchlist_df = pd.DataFrame(watchlist) if watchlist else pd.DataFrame()

    # 计算按钮
    col1, col2 = st.columns(2)

    with col1:
        calc_watchlist_disabled = watchlist_df.empty
        if st.button("🚀 一键计算自选股因子",
                     disabled=calc_watchlist_disabled,
                     use_container_width=True):
            if not watchlist_df.empty:
                with st.spinner("正在计算自选股因子..."):
                    _calculate_watchlist_factors(watchlist_df, wl_manager)
                st.success(f"完成！已计算 {len(watchlist_df)} 只股票")

    with col2:
        if st.button("📥 导出因子数据",
                     use_container_width=True,
                     disabled=not st.session_state.factor_calc_results):
            _export_factors_csv()
            st.info("因子数据已导出")

    # 计算进度显示
    if st.session_state.factor_last_calc_time:
        st.caption(f"最后计算时间: {st.session_state.factor_last_calc_time}")

    # 计算结果统计
    if st.session_state.factor_calc_results:
        results = st.session_state.factor_calc_results
        total_stocks = len(results)
        valid_stocks = sum(1 for r in results.values() if r)

        st.markdown("---")
        st.markdown(f"""
        **计算结果统计:**
        - 股票数量: {total_stocks}
        - 有效数据: {valid_stocks}
        - 缺失数据: {total_stocks - valid_stocks}
        """)

        # 显示已计算的股票列表
        with st.expander("查看已计算股票"):
            calc_stocks = list(results.keys())
            # 每行显示4只股票
            for i in range(0, len(calc_stocks), 4):
                row_stocks = calc_stocks[i:i+4]
                st.text("  ".join(row_stocks))


def _calculate_watchlist_factors(watchlist_df: pd.DataFrame,
                                  wl_manager: WatchlistManager):
    """计算自选股的所有因子"""
    symbols = watchlist_df['symbol'].tolist()
    ff = FundamentalFactors()
    results = {}

    # 进度条
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, symbol in enumerate(symbols):
        try:
            factors = ff.calculate_all_factors(symbol)
            # 只保存非零因子
            valid_factors = {k: v for k, v in factors.items() if v != 0}
            results[symbol] = valid_factors

            # 同时保存到数据库
            if valid_factors:
                rows = []
                for fname, fvalue in valid_factors.items():
                    rows.append({
                        'symbol': symbol,
                        'factor_name': fname,
                        'factor_value': fvalue
                    })
                df = pd.DataFrame(rows)
                trade_date = datetime.now().strftime('%Y-%m-%d')
                ff.save_factor_values(df, trade_date)

        except Exception as e:
            results[symbol] = {}

        progress = (i + 1) / len(symbols)
        progress_bar.progress(progress)
        status_text.text(f"计算中: {symbol} ({i+1}/{len(symbols)})")

    progress_bar.empty()
    status_text.empty()

    # 保存结果到 session state
    st.session_state.factor_calc_results = results
    st.session_state.factor_last_calc_time = datetime.now().strftime("%H:%M:%S")

    ff.close()


def _export_factors_csv():
    """导出因子数据为 CSV"""
    if not st.session_state.factor_calc_results:
        return

    results = st.session_state.factor_calc_results

    # 构建 DataFrame
    rows = []
    for symbol, factors in results.items():
        if not factors:
            continue
        row = {'股票代码': symbol}
        row.update(factors)
        rows.append(row)

    if not rows:
        st.warning("没有可导出的因子数据")
        return

    df = pd.DataFrame(rows)

    # 转换为 CSV
    csv = df.to_csv(index=False).encode('utf-8-sig')

    st.download_button(
        label="下载 CSV",
        data=csv,
        file_name=f"factors_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )


# =============================================================================
# 右侧：展示区
# =============================================================================

def _render_display_section(dm: DataManager, wl_manager: WatchlistManager):
    """渲染因子展示区域"""
    st.subheader("📈 因子查询")

    # 视图模式切换
    view_mode = st.radio(
        "视图模式",
        ["单股查询", "多股排名"],
        horizontal=True,
        label_visibility="collapsed"
    )

    if view_mode == "单股查询":
        _render_single_stock_view(dm, wl_manager)
    else:
        _render_multi_stock_ranking_view(dm, wl_manager)


def _render_single_stock_view(dm: DataManager, wl_manager: WatchlistManager):
    """单股因子查询视图"""
    # 股票选择
    watchlist = wl_manager.get_all_stocks()
    watchlist_df = pd.DataFrame(watchlist) if watchlist else pd.DataFrame()

    if watchlist_df.empty:
        st.info("请先在「自选股管理」中添加股票")
        return

    # 创建股票选项（代码 + 名称）
    stock_options = {row['symbol']: f"{row['symbol']} - {row.get('name', row['symbol'])}"
                     for _, row in watchlist_df.iterrows()}

    selected_symbol = st.selectbox(
        "选择股票",
        options=list(stock_options.keys()),
        format_func=lambda x: stock_options[x],
        index=0
    )

    if selected_symbol:
        st.session_state.factor_selected_symbol = selected_symbol

    # 计算日期
    trade_date = datetime.now().strftime('%Y-%m-%d')

    # 因子选择
    fp = FactorPresenter()

    # 获取因子类别
    factor_categories = fp.get_factor_list_by_category()

    # 创建因子选择UI
    tabs = st.tabs(list(factor_categories.keys()))

    for tab, (category, factors) in zip(tabs, factor_categories.items()):
        with tab:
            if not factors:
                st.text("无")
                continue

            # 按行显示因子卡片
            cols = st.columns(3)
            for i, (fname, fname_cn) in enumerate(factors):
                with cols[i % 3]:
                    # 计算因子值
                    try:
                        ff = FundamentalFactors()
                        factors_dict = ff.calculate_all_factors(selected_symbol, trade_date)
                        value = factors_dict.get(fname, 0)
                        ff.close()

                        formatted = fp.format_factor_value(fname, value)

                        # 获取因子元数据
                        metadata = fp._get_factor_metadata().get(fname, {})
                        direction = metadata.get('direction', 'neutral')

                        # 颜色标识
                        if value == 0:
                            color = "#cccccc"
                            value_display = "无数据"
                        elif direction == 'positive':
                            color = "#ff6b6b" if value > 0 else "#cccccc"
                            value_display = formatted
                        elif direction == 'negative':
                            color = "#51cf66" if value > 0 else "#cccccc"
                            value_display = formatted
                        else:
                            color = "#339af0"
                            value_display = formatted

                        st.markdown(f"""
                        <div style="
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            padding: 15px;
                            border-radius: 10px;
                            margin: 5px 0;
                        ">
                            <div style="color: white; font-size: 12px;">{fname_cn}</div>
                            <div style="color: {color}; font-size: 24px; font-weight: bold;">
                                {value_display}
                            </div>
                            <div style="color: #aaa; font-size: 10px;">
                                {'正向' if direction == 'positive' else '负向' if direction == 'negative' else '中性'}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                    except Exception as e:
                        st.markdown(f"""
                        <div style="
                            background: #f8f9fa;
                            padding: 15px;
                            border-radius: 10px;
                            margin: 5px 0;
                        ">
                            <div style="color: #666; font-size: 12px;">{fname_cn}</div>
                            <div style="color: #ccc; font-size: 18px;">计算失败</div>
                        </div>
                        """, unsafe_allow_html=True)

    fp.close()


def _render_multi_stock_ranking_view(dm: DataManager, wl_manager: WatchlistManager):
    """多股因子排名视图"""
    # 股票多选
    watchlist = wl_manager.get_all_stocks()
    watchlist_df = pd.DataFrame(watchlist) if watchlist else pd.DataFrame()

    if watchlist_df.empty:
        st.info("请先在「自选股管理」中添加股票")
        return

    selected_stocks = st.multiselect(
        "选择股票",
        options=watchlist_df['symbol'].tolist(),
        default=watchlist_df['symbol'].tolist()[:5],
        format_func=lambda x: f"{x} - {watchlist_df[watchlist_df['symbol']==x].iloc[0].get('name', x) if len(watchlist_df[watchlist_df['symbol']==x]) > 0 else x}"
    )

    if not selected_stocks:
        st.info("请选择至少一只股票")
        return

    # 因子选择
    fp = FactorPresenter()
    factor_list = fp.get_factor_list_by_category()

    # 展平因子列表
    all_factors = []
    for category, factors in factor_list.items():
        all_factors.extend(factors)

    if not all_factors:
        st.warning("没有可用的因子")
        return

    selected_factor = st.selectbox(
        "选择因子",
        options=[f[0] for f in all_factors],
        format_func=lambda x: dict(all_factors).get(x, x)
    )

    # 计算日期
    trade_date = datetime.now().strftime('%Y-%m-%d')

    # 计算因子排名
    if st.button("🔍 查询排名", use_container_width=True):
        ranking_df = fp.get_multi_stock_single_factor(
            selected_stocks,
            selected_factor,
            trade_date
        )

        if ranking_df.empty:
            st.warning("没有查询到有效数据")
        else:
            # 获取因子信息
            metadata = fp._get_factor_metadata().get(selected_factor, {})
            direction = metadata.get('direction', 'positive')
            factor_name = fp.FACTOR_NAMES_CN.get(selected_factor, selected_factor)

            st.markdown(f"**{factor_name}** 排名 ({'低优' if direction == 'negative' else '高优'})")

            # 显示柱状图
            fig = go.Figure()

            colors = ['#ff6b6b' if direction == 'positive' else '#51cf66'] * len(ranking_df)
            fig.add_trace(go.Bar(
                x=ranking_df['股票代码'],
                y=ranking_df['因子值'],
                marker_color=colors,
                text=[fp.format_factor_value(selected_factor, v) for v in ranking_df['因子值']],
                textposition='outside'
            ))

            fig.update_layout(
                title=dict(
                    text=f"{factor_name} 排名",
                    x=0.5
                ),
                yaxis_title="因子值",
                xaxis_title="股票",
                height=400,
                showlegend=False
            )

            st.plotly_chart(fig, use_container_width=True)

            # 显示详细表格
            ranking_df_display = ranking_df.copy()
            ranking_df_display['因子值'] = [
                fp.format_factor_value(selected_factor, v)
                for v in ranking_df_display['因子值']
            ]
            st.dataframe(ranking_df_display, use_container_width=True)

            # 导出按钮
            csv = ranking_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 导出CSV",
                data=csv,
                file_name=f"factor_ranking_{selected_factor}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

    fp.close()


# =============================================================================
# 辅助函数
# =============================================================================

def _get_stock_name_from_symbol(symbol: str, wl_manager: WatchlistManager) -> str:
    """从自选股管理器获取股票名称"""
    watchlist = wl_manager.get_all_stocks()
    for stock in watchlist:
        if stock.get('symbol') == symbol:
            return stock.get('name', symbol)
    return symbol

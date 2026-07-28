"""
因子分析页面
提供基本面因子的计算、查询和展示功能
"""
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from strategy.fundamental_factors import FundamentalFactors
from portfolio.watchlist import WatchlistManager, filter_out_benchmark_stocks, filter_out_benchmark_symbols
from data.data_manager import DataManager
from data.factor_manager import FactorManager
from web.factor_presenter import FactorPresenter
from web.services.backtest_service import load_backtest_stock_data


# =============================================================================
# 页面渲染函数
# =============================================================================

def _render_page_title():
    """渲染页面标题"""
    st.markdown(
        """
        <div class="section-title">
            <div class="main">🔬 因子分析</div>
            <div class="desc">支持单股因子洞察与多股横向排名，帮助快速识别优质标的</div>
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

def render_factor_analysis_page(dm: DataManager, wl_manager: WatchlistManager):
    """
    渲染因子分析页面

    Args:
        dm: DataManager 实例
        wl_manager: WatchlistManager 实例
    """
    _render_page_title()

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
    if 'factor_query_date_option' not in st.session_state:
        st.session_state.factor_query_date_option = "最新"
    if 'factor_last_query_date' not in st.session_state:
        st.session_state.factor_last_query_date = None
    if 'factor_last_report_date' not in st.session_state:
        st.session_state.factor_last_report_date = None
    if 'factor_prepare_last_run' not in st.session_state:
        st.session_state.factor_prepare_last_run = None
    if 'factor_prepare_last_status' not in st.session_state:
        st.session_state.factor_prepare_last_status = None
    if 'factor_prepare_last_message' not in st.session_state:
        st.session_state.factor_prepare_last_message = None
    if 'factor_delete_confirm_pending' not in st.session_state:
        st.session_state.factor_delete_confirm_pending = False


# =============================================================================
# 左侧：计算区
# =============================================================================

def _render_calc_section(dm: DataManager, wl_manager: WatchlistManager):
    """渲染因子准备区域"""
    _render_subsection_title("因子数据准备", "🧰", "为多因子回测批量准备因子值并写入缓存")

    # 获取自选股列表
    watchlist = filter_out_benchmark_stocks(wl_manager.get_all_stocks())
    watchlist_df = pd.DataFrame(watchlist) if watchlist else pd.DataFrame()
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("回测开始日期", value=pd.to_datetime("2023-01-01"), key="factor_prepare_start_date")
    with col2:
        end_date = st.date_input("回测结束日期", value=datetime.now().date(), key="factor_prepare_end_date")

    action_col1, action_col2 = st.columns(2)
    with action_col1:
        can_prepare = not watchlist_df.empty
        if st.button("🛠️ 准备因子数据", use_container_width=True, disabled=not can_prepare):
            if start_date > end_date:
                st.error("开始日期不能晚于结束日期")
                return
            missing_symbols, required_report_date = _check_financial_coverage_before_prepare(
                dm=dm,
                symbols=watchlist_df["symbol"].tolist(),
                asof_date=start_date.strftime("%Y-%m-%d"),
            )
            if missing_symbols:
                preview = "、".join(missing_symbols[:8])
                tail = "" if len(missing_symbols) <= 8 else f" 等 {len(missing_symbols)} 只"
                st.error(
                    f"财务数据覆盖不足：回测起始日需要报告期 <= {required_report_date}，"
                    f"以下股票缺少必要财务数据：{preview}{tail}。请先到「财务数据管理」更新后再准备因子。"
                )
                return
            with st.spinner("正在准备因子数据..."):
                prepared_rows, message = _prepare_factor_data_for_backtest(
                    dm=dm,
                    symbols=watchlist_df["symbol"].tolist(),
                    start_date=start_date.strftime("%Y-%m-%d"),
                    end_date=end_date.strftime("%Y-%m-%d"),
                )
            st.session_state.factor_prepare_last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.session_state.factor_prepare_last_status = "success" if prepared_rows > 0 else "failed"
            st.session_state.factor_prepare_last_message = message
            if prepared_rows > 0:
                st.success(f"因子数据准备完成：写入 {prepared_rows} 条记录。")
            else:
                st.error(message)
        if not can_prepare:
            st.caption("当前无自选股，无法准备因子数据。")

    with action_col2:
        if st.button("🗑️ 删除所有因子数据", use_container_width=True, type="secondary"):
            st.session_state.factor_delete_confirm_pending = True

        if st.session_state.factor_delete_confirm_pending:
            st.warning("确认要删除所有因子数据吗？此操作不可撤销。")
            confirm_col, cancel_col = st.columns(2)
            with confirm_col:
                if st.button("✅ 确认删除", use_container_width=True, key="confirm_delete_factor_values_btn"):
                    deleted_rows = _delete_all_factor_values(dm)
                    st.session_state.factor_prepare_last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state.factor_prepare_last_status = "success"
                    st.session_state.factor_prepare_last_message = f"已删除 factor_values 共 {deleted_rows} 条记录"
                    st.session_state.factor_calc_results = {}
                    st.session_state.factor_delete_confirm_pending = False
                    st.success(st.session_state.factor_prepare_last_message)
            with cancel_col:
                if st.button("❎ 取消", use_container_width=True, key="cancel_delete_factor_values_btn"):
                    st.session_state.factor_delete_confirm_pending = False

    if st.session_state.factor_prepare_last_run:
        st.caption(f"最近准备时间: {st.session_state.factor_prepare_last_run}")
    if st.session_state.factor_prepare_last_message:
        status = st.session_state.factor_prepare_last_status
        label = "状态：成功" if status == "success" else "状态：失败"
        st.caption(f"{label} | {st.session_state.factor_prepare_last_message}")


def _prepare_factor_data_for_backtest(
    dm: DataManager,
    symbols: List[str],
    start_date: str,
    end_date: str,
) -> tuple[int, str]:
    """按回测区间准备因子数据并写入 factor_values。"""
    stock_data = load_backtest_stock_data(dm.db_path, symbols, start_date, end_date)
    if not stock_data:
        return 0, "未获取到可用行情数据，请先更新行情库。"

    ff = FundamentalFactors(dm.db_path)
    factor_mgr = FactorManager(dm.db_path)
    fp = FactorPresenter()
    rows = []

    try:
        factor_categories = fp.get_factor_list_by_category()
        factor_names = []
        for factors in factor_categories.values():
            for factor_name, _ in factors:
                factor_names.append(factor_name)
        factor_names = sorted(set(factor_names))
        if not factor_names:
            return 0, "未找到可用因子元数据。"

        progress_bar = st.progress(0)
        status_text = st.empty()
        total_symbols = len(stock_data)

        for idx, (symbol, df) in enumerate(stock_data.items(), start=1):
            date_series = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d") if "date" in df.columns else df.index.astype(str)
            for trade_date in date_series:
                values = ff.calculate_all_factors(symbol, trade_date)
                report_date = ff.get_report_date(trade_date, symbol)
                report_pub_date = ff.get_report_publish_date(symbol, report_date)
                for factor_name in factor_names:
                    if factor_name not in values:
                        continue
                    value = values.get(factor_name)
                    if pd.isna(value):
                        continue
                    rows.append(
                        {
                            "symbol": symbol,
                            "trade_date": trade_date,
                            "factor_name": factor_name,
                            "factor_value": float(value),
                            "value_source": "prepare_task",
                            "is_imputed": 0,
                            "quality_flag": "ok",
                            "asof_trade_date": trade_date,
                            "source_report_date": report_date,
                            "source_pub_date": report_pub_date,
                        }
                    )
            progress = int((idx / max(1, total_symbols)) * 100)
            progress_bar.progress(progress / 100)
            status_text.text(f"准备中: {symbol} ({idx}/{total_symbols})")

        progress_bar.empty()
        status_text.empty()
        if not rows:
            return 0, "准备完成但未产生可写入记录。"
        saved = factor_mgr.save_factor_values(pd.DataFrame(rows))
        return saved, f"覆盖股票 {len(stock_data)} 只，区间 {start_date} ~ {end_date}"
    finally:
        fp.close()
        ff.close()


def _infer_required_report_date(asof_date: str) -> str:
    """
    根据回测起始日推断最低应可用报告期。

    规则与因子侧一致：
    - 1~4月：上年Q3
    - 5~8月：当年Q1
    - 9~10月：当年Q2
    - 11~12月：当年Q3
    """
    dt = pd.to_datetime(asof_date)
    y = dt.year
    m = dt.month
    if m <= 4:
        return f"{y - 1}-09-30"
    if m <= 8:
        return f"{y}-03-31"
    if m <= 10:
        return f"{y}-06-30"
    return f"{y}-09-30"


def _check_financial_coverage_before_prepare(
    dm: DataManager,
    symbols: List[str],
    asof_date: str,
) -> tuple[List[str], str]:
    """
    准备因子前检查财务覆盖：
    每只股票在 required_report_date 之前，至少应有利润表与资产负债表记录。
    """
    required_report_date = _infer_required_report_date(asof_date)
    missing_symbols: List[str] = []

    conn = sqlite3.connect(dm.db_path)
    try:
        for symbol in symbols:
            profit_row = conn.execute(
                """
                SELECT MAX(report_date) FROM profit_data
                WHERE symbol = ? AND report_date <= ?
                """,
                (symbol, required_report_date),
            ).fetchone()
            balance_row = conn.execute(
                """
                SELECT MAX(report_date) FROM balance_data
                WHERE symbol = ? AND report_date <= ?
                """,
                (symbol, required_report_date),
            ).fetchone()
            if not (profit_row and profit_row[0]) or not (balance_row and balance_row[0]):
                missing_symbols.append(symbol)
    finally:
        conn.close()

    return missing_symbols, required_report_date


def _delete_all_factor_values(dm: DataManager) -> int:
    """删除 factor_values 全表数据。"""
    conn = sqlite3.connect(dm.db_path)
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT COUNT(1) FROM factor_values").fetchone()
        total = int(row[0]) if row else 0
        cursor.execute("DELETE FROM factor_values")
        conn.commit()
        return total
    finally:
        conn.close()


def _calculate_watchlist_factors(watchlist_df: pd.DataFrame,
                                  wl_manager: WatchlistManager,
                                  date_option: str = "最新"):
    """计算自选股的所有因子"""
    symbols = watchlist_df['symbol'].tolist()
    ff = FundamentalFactors()
    fp = FactorPresenter()
    query_date = fp.resolve_trade_date(date_option)
    report_date = ff.get_report_date(query_date)
    results = {}

    # 进度条
    progress_bar = st.progress(0)
    status_text = st.empty()

    def on_progress(current: int, total: int):
        progress_bar.progress(current / total)
        current_symbol = symbols[current - 1] if 0 < current <= len(symbols) else ""
        status_text.text(f"计算中: {current_symbol} ({current}/{total})")

    results = fp.calculate_watchlist_factors(
        symbols=symbols,
        trade_date=query_date,
        progress_callback=on_progress
    )

    rows = []
    for symbol, valid_factors in results.items():
        if not valid_factors:
            continue
        for fname, fvalue in valid_factors.items():
            rows.append({
                'symbol': symbol,
                'factor_name': fname,
                'factor_value': fvalue
            })

    if rows:
        # 统一走 FactorManager 写入口，保持写库语义一致
        factor_mgr = FactorManager(ff.fdm.db_path)
        save_df = pd.DataFrame(rows)
        save_df["trade_date"] = query_date
        save_df["value_source"] = "analysis_ui"
        save_df["is_imputed"] = 0
        save_df["quality_flag"] = "ok"
        save_df["asof_trade_date"] = query_date
        report_map = {s: ff.get_report_date(query_date, s) for s in symbols}
        pub_map = {s: ff.get_report_publish_date(s, report_map[s]) for s in symbols if s in report_map}
        save_df["source_report_date"] = save_df["symbol"].map(report_map).fillna(report_date)
        save_df["source_pub_date"] = save_df["symbol"].map(pub_map).fillna("")
        factor_mgr.save_factor_values(save_df)

    progress_bar.empty()
    status_text.empty()

    # 保存结果到 session state
    st.session_state.factor_calc_results = results
    st.session_state.factor_last_calc_time = datetime.now().strftime("%H:%M:%S")
    st.session_state.factor_last_query_date = query_date
    st.session_state.factor_last_report_date = report_date

    fp.close()
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
        row = {
            '股票代码': symbol,
            '查询日期': st.session_state.factor_last_query_date,
            '财报截止日期': st.session_state.factor_last_report_date
        }
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
    _render_subsection_title("因子查询", "📈", "按单股或多股维度查看因子值与排名")

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
    watchlist = filter_out_benchmark_stocks(wl_manager.get_all_stocks())
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

    # 因子选择
    fp = FactorPresenter()
    date_options = _get_factor_date_options()
    default_option = st.session_state.factor_query_date_option
    default_index = date_options.index(default_option) if default_option in date_options else 0
    selected_date_option = st.selectbox(
        "查询日期",
        options=date_options,
        index=default_index,
        help="“最新”会自动映射到当前可用的最近财报截止日"
    )
    st.session_state.factor_query_date_option = selected_date_option
    factor_payload = fp.get_factors_on_date(selected_symbol, selected_date_option)
    factors_dict = factor_payload['factors']
    query_date = factor_payload['query_date']
    report_date = factor_payload['report_date']
    st.caption(f"查询日期: {query_date} | 实际财报截止日期: {report_date}")

    # 获取因子类别
    factor_categories = fp.get_factor_list_by_category()

    # 兜底：当元数据表为空或读取失败时，使用内置因子定义，避免 st.tabs([]) 报错
    if not factor_categories:
        fallback_categories = {}
        for factor_name, meta in FundamentalFactors.FACTOR_METADATA.items():
            category_en = meta.get('category', '')
            category_cn = fp.FACTOR_CATEGORIES.get(category_en, '其他')
            fallback_categories.setdefault(category_cn, []).append((
                factor_name,
                fp.FACTOR_NAMES_CN.get(factor_name, factor_name)
            ))
        factor_categories = fallback_categories

    if not factor_categories:
        st.warning("暂无可展示的因子分类，请先检查因子元数据初始化。")
        return

    # 创建因子选择UI
    tabs = st.tabs(list(factor_categories.keys()))

    metadata_all = fp._get_factor_metadata()
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
                        value = factors_dict.get(fname, 0)

                        formatted = fp.format_factor_value(fname, value)

                        # 获取因子元数据
                        metadata = metadata_all.get(fname, {})
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
    watchlist = filter_out_benchmark_stocks(wl_manager.get_all_stocks())
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
    selected_stocks = filter_out_benchmark_symbols(selected_stocks)

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

    date_options = _get_factor_date_options()
    default_option = st.session_state.factor_query_date_option
    default_index = date_options.index(default_option) if default_option in date_options else 0
    selected_date_option = st.selectbox(
        "查询日期",
        options=date_options,
        index=default_index,
        help="多股排名会统一使用同一个财报截止日期"
    )
    st.session_state.factor_query_date_option = selected_date_option
    query_date = fp.resolve_trade_date(selected_date_option)
    report_date = fp.ff.get_report_date(query_date)
    st.caption(f"查询日期: {query_date} | 实际财报截止日期: {report_date}")

    # 计算因子排名
    if st.button("🔍 查询排名", use_container_width=True):
        ranking_df = fp.get_multi_stock_single_factor(
            selected_stocks,
            selected_factor,
            query_date
        )

        if ranking_df.empty:
            st.warning("没有查询到有效数据")
        else:
            # 股票代码 -> 代码+中文名
            symbol_to_name = {
                row['symbol']: row.get('name', row['symbol'])
                for _, row in watchlist_df.iterrows()
            }

            # 获取因子信息
            metadata = fp._get_factor_metadata().get(selected_factor, {})
            direction = metadata.get('direction', 'positive')
            factor_name = fp.FACTOR_NAMES_CN.get(selected_factor, selected_factor)

            st.markdown(f"**{factor_name}** 排名 ({'低优' if direction == 'negative' else '高优'})")

            # 显示详细表格
            ranking_df_display = ranking_df.copy()
            ranking_df_display['股票'] = ranking_df_display['股票代码'].apply(
                lambda s: f"{s} - {symbol_to_name.get(s, s)}"
            )
            ranking_df_display['查询日期'] = query_date
            ranking_df_display['财报截止日期'] = report_date
            ranking_df_display['因子值'] = [
                fp.format_factor_value(selected_factor, v)
                for v in ranking_df_display['因子值']
            ]
            st.dataframe(
                ranking_df_display[['排名', '股票', '因子值', '查询日期', '财报截止日期']],
                use_container_width=True,
                hide_index=True
            )

            # 导出按钮
            ranking_export_df = ranking_df.copy()
            ranking_export_df['股票'] = ranking_export_df['股票代码'].apply(
                lambda s: f"{s} - {symbol_to_name.get(s, s)}"
            )
            ranking_export_df['查询日期'] = query_date
            ranking_export_df['财报截止日期'] = report_date
            ranking_export_df = ranking_export_df[['排名', '股票代码', '股票', '因子值', '查询日期', '财报截止日期']]
            csv = ranking_export_df.to_csv(index=False).encode('utf-8-sig')
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
    watchlist = filter_out_benchmark_stocks(wl_manager.get_all_stocks())
    for stock in watchlist:
        if stock.get('symbol') == symbol:
            return stock.get('name', symbol)
    return symbol


def _get_factor_date_options(quarter_count: int = 12) -> List[str]:
    """生成因子分析页面的日期选项。"""
    options = ["最新"]
    today = pd.Timestamp.today()
    quarter_ends = pd.date_range(end=today, periods=quarter_count, freq='Q')
    quarter_labels = {
        "03-31": "一季报",
        "06-30": "中报",
        "09-30": "三季报",
        "12-31": "年报",
    }
    for quarter_end in sorted(quarter_ends, reverse=True):
        date_str = quarter_end.strftime('%Y-%m-%d')
        label = quarter_labels.get(quarter_end.strftime('%m-%d'), "财报")
        options.append(f"{date_str} ({label})")
    return options

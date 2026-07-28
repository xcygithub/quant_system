"""
财务数据管理页面
独立页面管理所有财务数据源
"""
import streamlit as st
import pandas as pd
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from data.data_manager import DataManager
from data.financial_data_source import FinancialDataSource
from data.financial_data_manager import FinancialDataManager
from data.financial_data_saver import FinancialDataSaver
from portfolio.watchlist import WatchlistManager, filter_out_benchmark_stocks, filter_out_benchmark_symbols


# =============================================================================
# 页面配置
# =============================================================================

def configure_page():
    """独立运行该页面时使用的页面配置。"""
    st.set_page_config(
        page_title="财务数据管理",
        page_icon="📥",
        layout="wide"
    )


# =============================================================================
# 辅助函数
# =============================================================================

def get_data_status() -> Dict[str, dict]:
    """
    获取各数据表的状态信息

    Returns:
        {表名: {记录数, 最新日期, 说明}}
    """
    dm = DataManager()

    status = {}

    # 1. 估值数据
    try:
        conn = sqlite3.connect(dm.db_path)
        cursor = conn.cursor()

        # valuation_data
        cursor.execute("SELECT COUNT(*), MAX(trade_date) FROM valuation_data")
        row = cursor.fetchone()
        status['valuation_data'] = {
            'count': row[0] or 0,
            'latest_date': row[1] or '无',
            'desc': '实时估值（PE/PB/PS/PCF）'
        }

        # profit_data (使用 report_date)
        cursor.execute("SELECT COUNT(*), MAX(report_date) FROM profit_data")
        row = cursor.fetchone()
        status['profit_data'] = {
            'count': row[0] or 0,
            'latest_date': row[1] or '无',
            'desc': '利润表'
        }

        # balance_data (使用 report_date)
        cursor.execute("SELECT COUNT(*), MAX(report_date) FROM balance_data")
        row = cursor.fetchone()
        status['balance_data'] = {
            'count': row[0] or 0,
            'latest_date': row[1] or '无',
            'desc': '资产负债表'
        }

        # cash_flow_data (使用 report_date)
        cursor.execute("SELECT COUNT(*), MAX(report_date) FROM cash_flow_data")
        row = cursor.fetchone()
        status['cash_flow_data'] = {
            'count': row[0] or 0,
            'latest_date': row[1] or '无',
            'desc': '现金流量表'
        }

        # dupont_data (使用 report_date)
        cursor.execute("SELECT COUNT(*), MAX(report_date) FROM dupont_data")
        row = cursor.fetchone()
        status['dupont_data'] = {
            'count': row[0] or 0,
            'latest_date': row[1] or '无',
            'desc': '杜邦分析'
        }

        # growth_data (使用 report_date)
        cursor.execute("SELECT COUNT(*), MAX(report_date) FROM growth_data")
        row = cursor.fetchone()
        status['growth_data'] = {
            'count': row[0] or 0,
            'latest_date': row[1] or '无',
            'desc': '成长能力'
        }

        # operation_data (使用 report_date)
        cursor.execute("SELECT COUNT(*), MAX(report_date) FROM operation_data")
        row = cursor.fetchone()
        status['operation_data'] = {
            'count': row[0] or 0,
            'latest_date': row[1] or '无',
            'desc': '营运能力'
        }

        # debtpaying_data (使用 report_date)
        cursor.execute("SELECT COUNT(*), MAX(report_date) FROM debtpaying_data")
        row = cursor.fetchone()
        status['debtpaying_data'] = {
            'count': row[0] or 0,
            'latest_date': row[1] or '无',
            'desc': '偿债能力'
        }

        # daily_kline
        cursor.execute("SELECT COUNT(*), MAX(date) FROM daily_kline")
        row = cursor.fetchone()
        status['daily_kline'] = {
            'count': row[0] or 0,
            'latest_date': row[1] or '无',
            'desc': '日线行情'
        }

        # financial_data_raw（接口原始字段）
        try:
            cursor.execute("SELECT COUNT(*), MAX(update_time) FROM financial_data_raw")
            row = cursor.fetchone()
            status['financial_data_raw'] = {
                'count': row[0] or 0,
                'latest_date': row[1] or '无',
                'desc': '财务原始数据(JSON)'
            }
        except Exception:
            status['financial_data_raw'] = {
                'count': 0,
                'latest_date': '无',
                'desc': '财务原始数据(JSON)'
            }

        conn.close()
    except Exception as e:
        st.error(f"获取数据状态失败: {e}")

    return status


def get_stock_count() -> int:
    """获取自选股数量"""
    try:
        wl = WatchlistManager()
        return len(wl.get_all_stocks())
    except:
        return 0


# =============================================================================
# 页面渲染
# =============================================================================

def _render_page_title():
    """渲染页面标题"""
    st.markdown(
        """
        <div class="section-title">
            <div class="main">📥 财务数据管理</div>
            <div class="desc">统一管理财务报表、估值与行情数据，保障研究与回测数据质量</div>
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

def render_data_management_page():
    """渲染财务数据管理页面"""

    _render_page_title()

    # 获取数据状态
    status = get_data_status()
    watchlist_count = get_stock_count()

    # -------------------------------------------------------------------------
    # 1. 数据源状态总览
    # -------------------------------------------------------------------------
    _render_subsection_title("数据源状态总览", "📊", "掌握各表记录量与最新日期，快速判断可用性")

    # 显示指标卡片
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_records = sum(s['count'] for s in status.values())
        st.metric("总记录数", f"{total_records:,}")

    with col2:
        stock_count = status.get('valuation_data', {}).get('count', 0)
        st.metric("股票数", f"{stock_count:,}")

    with col3:
        latest_kline = status.get('daily_kline', {}).get('latest_date', '无')
        st.metric("行情最新", latest_kline)

    with col4:
        latest_financial = status.get('profit_data', {}).get('latest_date', '无')
        st.metric("财务最新", latest_financial)

    # 数据表状态表格
    st.divider()

    status_df = pd.DataFrame([
        {
            "数据类型": info['desc'],
            "表名": table,
            "记录数": f"{info['count']:,}",
            "最新日期": info['latest_date']
        }
        for table, info in status.items()
    ])

    if not status_df.empty:
        st.dataframe(
            status_df,
            use_container_width=True,
            hide_index=True
        )

    st.divider()

    # -------------------------------------------------------------------------
    # 2. 获取方式选择
    # -------------------------------------------------------------------------
    _render_subsection_title("获取财务数据", "🔄", "支持全市场、自选股或单只股票增量更新")

    fetch_mode = st.radio(
        "获取范围",
        options=["全市场", "自选股", "单只股票"],
        horizontal=True,
        help="全市场：获取A股所有股票的财务数据（耗时较长）\n自选股：只获取自选股列表中的股票\n单只股票：手动输入股票代码"
    )

    # 数据类型选择（红框六类财务数据 + 资产负债表）
    data_type_options = {
        "利润表": "profit",
        "资产负债表": "balance",
        "现金流量表": "cash",
        "杜邦分析": "dupont",
        "成长能力": "growth",
        "营运能力": "operation",
        "偿债能力": "debtpaying",
    }

    selected_labels = st.multiselect(
        "数据类型",
        options=list(data_type_options.keys()),
        default=["利润表", "资产负债表", "现金流量表", "杜邦分析", "成长能力", "营运能力", "偿债能力"],
        help="选择要获取的财务数据类型（7种：利润表、资产负债表、现金流量表、杜邦分析、成长能力、营运能力、偿债能力）"
    )

    # 转换为简写格式（batch_update 使用的格式）
    data_types = [data_type_options[label] for label in selected_labels]

    # 时间范围（仅支持 start_year）
    start_year = st.number_input(
        "起始年份",
        min_value=2010,
        max_value=datetime.now().year,
        value=datetime.now().year - 4,
        help="财务数据的历史范围（默认近4年，覆盖年初回测对上年Q3的依赖）"
    )

    # 获取按钮
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])

    with col_btn1:
        fetch_button = st.button("🚀 开始获取", type="primary", use_container_width=True)

    with col_btn2:
        fetch_valuation = st.button("📈 获取实时估值", use_container_width=True, help="快速更新全市场PE/PB/PS等估值数据")

    valuation_fetch_mode = st.radio(
        "估值获取模式",
        options=["历史区间（从起始年份）", "最新快照（仅最近交易日）"],
        index=0,
        horizontal=True,
        help="历史区间会拉取时间范围内的每日估值；最新快照仅保留每只股票最近一个交易日"
    )
    valuation_incremental = st.checkbox(
        "仅增量更新估值（从库内最后日期之后开始）",
        value=True,
        help="开启后将按股票读取 valuation_data 的最大交易日，只补拉新数据，显著减少耗时"
    )

    # -------------------------------------------------------------------------
    # 3. 执行获取
    # -------------------------------------------------------------------------
    if fetch_button:
        if not data_types:
            st.warning("请至少选择一种数据类型")
        else:
            symbols = []
            mode_desc = ""

            if fetch_mode == "全市场":
                mode_desc = "全市场 A 股"
                with st.spinner("正在获取股票列表..."):
                    fdn = FinancialDataManager()
                    all_stocks = fdn.get_all_stocks()
                    symbols = all_stocks if all_stocks else []
                if not symbols:
                    st.error("获取股票列表失败，请检查网络连接")
            elif fetch_mode == "自选股":
                mode_desc = f"自选股 ({watchlist_count} 只)"
                wl = WatchlistManager()
                symbols = [s.symbol for s in filter_out_benchmark_stocks(wl.get_all_stocks())]
            else:
                symbol_input = st.text_input("请输入股票代码", placeholder="000001.SZ")
                if symbol_input:
                    symbols = filter_out_benchmark_symbols([symbol_input.upper()])
                    mode_desc = f"单只股票 {symbol_input}"

            if symbols:
                st.info(f"准备获取 {mode_desc} 的 {len(data_types)} 种财务数据，从 {start_year} 年至今...")

                # 初始化进度条
                progress_bar = st.progress(0)
                progress_text = st.empty()

                def progress_callback(current: int, total: int, symbol: str):
                    pct = current / total if total > 0 else 0
                    progress_bar.progress(pct)
                    progress_text.text(f"进度: {current}/{total} - {symbol}")

                # 执行获取
                fdn = FinancialDataManager()

                try:
                    with st.spinner("正在从 Baostock 获取数据（请耐心等待）..."):
                        result = fdn.batch_update(
                            symbols=symbols,
                            data_types=data_types,
                            start_year=start_year,
                            progress_callback=progress_callback
                        )

                    progress_bar.empty()
                    progress_text.empty()

                    # 显示结果（batch_update 返回 Dict[str, int]，key 是数据类型，value 是记录数）
                    total_records = sum(result.values())
                    st.success(f"获取完成！共保存 {total_records} 条财务数据记录")

                    # 显示各类型明细
                    with st.expander("查看各数据类型记录数"):
                        for dtype, count in result.items():
                            st.write(f"  - {dtype}: {count} 条")

                    # 刷新状态
                    st.rerun()

                except Exception as e:
                    progress_bar.empty()
                    progress_text.empty()
                    st.error(f"获取失败: {e}")

    # 获取实时估值
    if fetch_valuation:
        # 根据 fetch_mode 确定获取范围
        valuation_symbols = []
        mode_desc = ""
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = f"{int(start_year)}-01-01"
        latest_only = (valuation_fetch_mode == "最新快照（仅最近交易日）")

        dm_for_valuation = DataManager()
        conn_for_valuation = sqlite3.connect(dm_for_valuation.db_path)

        if fetch_mode == "全市场":
            mode_desc = "全市场"
            fds = FinancialDataSource()
            valuation_symbols = fds.get_all_stocks()
            fds.logout()
        elif fetch_mode == "自选股":
            wl = WatchlistManager()
            stocks = filter_out_benchmark_stocks(wl.get_all_stocks())
            valuation_symbols = [s.symbol for s in stocks]
            mode_desc = f"自选股 ({len(valuation_symbols)} 只)"
        else:
            # 单只股票模式需要在输入框中获取股票代码
            st.warning("请在下方输入股票代码（如 000001.SZ），然后点击获取实时估值")
            valuation_symbols = []  # 清空，等待用户输入

        if valuation_symbols:
            scope_desc = "最新快照" if latest_only else f"历史区间 {start_date} ~ {end_date}"
            update_mode_desc = "增量" if valuation_incremental else "全量"
            st.info(f"准备获取 {mode_desc} 的估值数据（{scope_desc}，{update_mode_desc}），共 {len(valuation_symbols)} 只股票...")

            with st.spinner(f"正在获取 {mode_desc} 估值数据..."):
                try:
                    fds = FinancialDataSource()

                    if fetch_mode == "全市场" and latest_only:
                        df = fds.get_all_stocks_valuation()
                    else:
                        # 历史模式或非全市场模式：遍历获取
                        all_data = []
                        progress_bar = st.progress(0)
                        progress_text = st.empty()

                        for i, symbol in enumerate(valuation_symbols):
                            pct = (i + 1) / len(valuation_symbols)
                            progress_bar.progress(pct)
                            progress_text.text(f"进度: {i+1}/{len(valuation_symbols)} - {symbol}")

                            query_start_date = start_date
                            if valuation_incremental and not latest_only:
                                try:
                                    cursor = conn_for_valuation.cursor()
                                    cursor.execute(
                                        "SELECT MAX(trade_date) FROM valuation_data WHERE symbol = ?",
                                        (symbol,)
                                    )
                                    row = cursor.fetchone()
                                    if row and row[0]:
                                        last_date = datetime.strptime(str(row[0]), "%Y-%m-%d")
                                        next_date = last_date + timedelta(days=1)
                                        query_start_date = next_date.strftime("%Y-%m-%d")
                                except Exception:
                                    query_start_date = start_date

                            # 增量场景下如果已是最新则跳过
                            if not latest_only and query_start_date > end_date:
                                continue

                            df_stock = fds.get_history_valuation(symbol, query_start_date, end_date)
                            if not df_stock.empty:
                                if latest_only:
                                    df_stock = df_stock.sort_values('trade_date', ascending=False).head(1)
                                all_data.append(df_stock)

                        progress_bar.empty()
                        progress_text.empty()

                        if all_data:
                            df = pd.concat(all_data, ignore_index=True)
                        else:
                            df = pd.DataFrame()

                    if not df.empty:
                        saver = FinancialDataSaver()
                        saved = saver.save_valuation_data(df)
                        st.success(f"✅ 成功获取并保存 {saved} 只股票的估值数据")

                        # 显示部分数据
                        with st.expander("查看最新估值数据（前10只）"):
                            display_df = df.head(10)[['symbol', 'trade_date', 'pe_ttm', 'pb', 'ps', 'pcf', 'close']]
                            st.dataframe(display_df, use_container_width=True)
                    else:
                        st.warning("未获取到估值数据")

                    fds.logout()
                    st.rerun()

                except Exception as e:
                    st.error(f"获取估值数据失败: {e}")
        elif fetch_mode == "单只股票":
            st.info("请先输入股票代码再获取估值")

        conn_for_valuation.close()

    st.divider()

    # -------------------------------------------------------------------------
    # 4. 批量操作
    # -------------------------------------------------------------------------
    _render_subsection_title("批量操作", "🛠️", "查看结构、清理历史与刷新状态")

    col_batch1, col_batch2, col_batch3 = st.columns(3)

    if 'confirm_clear_financial' not in st.session_state:
        st.session_state.confirm_clear_financial = False

    with col_batch1:
        if st.button("📋 查看数据库表结构", use_container_width=True):
            with st.expander("数据库表结构", expanded=True):
                dm = DataManager()
                conn = sqlite3.connect(dm.db_path)
                cursor = conn.cursor()

                # 获取所有表
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                tables = cursor.fetchall()

                for table in tables:
                    table_name = table[0]
                    st.markdown(f"**{table_name}**")

                    # 获取表结构
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns = cursor.fetchall()
                    col_df = pd.DataFrame(columns, columns=['cid', 'name', 'type', 'notnull', 'dflt_value', 'pk'])
                    st.dataframe(col_df[['name', 'type', 'pk']], use_container_width=True, hide_index=True)

                conn.close()

    with col_batch2:
        if st.button("🗑️ 清除财务数据", use_container_width=True):
            st.session_state.confirm_clear_financial = True

    if st.session_state.confirm_clear_financial:
        st.warning("⚠️ 此操作将清除财务与估值相关数据，确认吗？")
        col_confirm1, col_confirm2 = st.columns(2)
        with col_confirm1:
            if st.button("确认清除", type="primary", key="confirm_clear_financial_btn"):
                try:
                    dm = DataManager()
                    conn = sqlite3.connect(dm.db_path)
                    cursor = conn.cursor()

                    tables_to_clear = [
                        'profit_data', 'balance_data', 'cash_flow_data',
                        'dupont_data', 'growth_data', 'operation_data',
                        'debtpaying_data', 'valuation_data',
                        'history_valuation_data', 'financial_data_raw'
                    ]

                    for table in tables_to_clear:
                        try:
                            cursor.execute(f"DELETE FROM {table}")
                            st.success(f"已清除 {table}")
                        except Exception:
                            st.warning(f"跳过 {table}（表不存在）")

                    conn.commit()
                    conn.close()
                    st.session_state.confirm_clear_financial = False
                    st.rerun()
                except Exception as e:
                    st.error(f"清除失败: {e}")
        with col_confirm2:
            if st.button("取消", key="cancel_clear_financial_btn"):
                st.session_state.confirm_clear_financial = False
                st.rerun()

    with col_batch3:
        if st.button("🔄 刷新状态", use_container_width=True):
            st.rerun()

    st.divider()

    # -------------------------------------------------------------------------
    # 5. 财报披露日历提示
    # -------------------------------------------------------------------------
    _render_subsection_title("财报披露日历", "📅", "根据披露窗口合理安排财务数据更新频率")

    current_month = datetime.now().month
    current_day = datetime.now().day

    tips = []

    if current_month < 5 or (current_month == 5 and current_day < 15):
        tips.append("📌 **年报 + 一季报** 披露期（1月-4月30日）")
        tips.append("   预计5月15日后可获取完整数据")
    elif current_month < 9 or (current_month == 9 and current_day < 15):
        tips.append("📌 **中报** 披露期（7月-8月31日）")
        tips.append("   预计9月15日后可获取完整数据")
    elif current_month < 11 or (current_month == 11 and current_day < 15):
        tips.append("📌 **三季报** 披露期（10月1日-10月31日）")
        tips.append("   预计11月15日后可获取完整数据")
    else:
        tips.append("✅ 当前为财报真空期，所有最新财报已可获取")

    for tip in tips:
        st.markdown(tip)

    # -------------------------------------------------------------------------
    # 6. 使用说明
    # -------------------------------------------------------------------------
    with st.expander("📖 使用说明"):
        st.markdown("""
        **数据来源**: Baostock (https://www.baostock.com)

        **获取频率建议**:
        - 估值数据（PE/PB/PS）: 每日获取
        - 财务数据（利润表/资产负债表等）: 每季度获取

        **财报披露时间**:
        - 年报: 次年4月30日前
        - 一季报: 次年4月30日前
        - 中报: 次年8月31日前
        - 三季报: 次年10月31日前

        **注意事项**:
        1. 全市场获取耗时较长（约15-30分钟），建议分批获取
        2. Baostock API 有访问限制，请勿频繁请求
        3. 获取过程中请勿关闭页面
        """)


# =============================================================================
# 入口
# =============================================================================

if __name__ == "__main__":
    configure_page()
    render_data_management_page()

"""回测结果展示服务：封装 Tab2 的展示逻辑。"""

from datetime import datetime
from typing import Any, Callable, Dict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _style_trade_details_dataframe(trade_details_df: pd.DataFrame) -> Any:
    """交易明细仅格式化浮点列为两位小数，整型列保持原样。"""
    display_df = trade_details_df.drop(columns=["股票代码", "股票名称"], errors="ignore")
    float_cols = display_df.select_dtypes(include=["float", "floating"]).columns.tolist()
    if not float_cols:
        return display_df
    return display_df.style.format("{:.2f}", subset=float_cols)


def render_multi_factor_results(results: Dict[str, Any], stock_count: int) -> None:
    """展示多因子回测结果。"""
    st.success(f"✅ 多因子回测完成! 共回测 {stock_count} 只股票")

    if not results:
        return

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总收益率", f"{results.get('total_return', 0):.2%}")
    with col2:
        st.metric("年化收益率", f"{results.get('annual_return', 0):.2%}")
    with col3:
        st.metric("夏普比率", f"{results.get('sharpe_ratio', 0):.2f}")
    with col4:
        st.metric("最大回撤", f"{results.get('max_drawdown', 0):.2%}")

    equity_df = results.get("equity_curve")
    if equity_df is not None and not equity_df.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=equity_df["date"],
            y=equity_df["total_value"],
            name="组合权益",
            line=dict(color="#1f77b4", width=2),
        ))
        if "benchmark" in equity_df.columns:
            fig.add_trace(go.Scatter(
                x=equity_df["date"],
                y=equity_df["benchmark"],
                name="基准",
                line=dict(color="#888888", width=1, dash="dash"),
            ))
        fig.update_layout(
            title="多因子组合权益曲线",
            xaxis_title="日期",
            yaxis_title="净值",
            height=400,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)

    factor_report = results.get("factor_report", {})
    if not factor_report:
        return

    st.divider()
    st.subheader("📊 因子分析报告")
    ic_weights = factor_report.get("ic_weights", {})
    base_weights = factor_report.get("factor_weights", {})
    if not (ic_weights and base_weights):
        return

    col_w1, col_w2 = st.columns(2)
    with col_w1:
        st.markdown("**因子权重对比**")
        weight_data = []
        for factor in base_weights:
            weight_data.append({
                "因子": factor,
                "基础权重": f"{base_weights[factor]:.1%}",
                "IC权重": f"{ic_weights.get(factor, 0):.1%}",
                "变化": f"{ic_weights.get(factor, 0) - base_weights[factor]:+.1%}",
            })
        if weight_data:
            st.dataframe(pd.DataFrame(weight_data), use_container_width=True)

    with col_w2:
        st.markdown("**IC 有效性判定**")
        ic_validity = factor_report.get("ic_validity_report", {})
        validity_colors = {
            "strong": "🟢",
            "normal": "🟡",
            "weak": "🟠",
            "invalid": "🔴",
        }
        validity_data = []
        for factor, stats in ic_validity.items():
            validity_data.append({
                "因子": factor,
                "IC均值": f"{stats.get('ic_mean', 0):.3f}",
                "IR": f"{stats.get('ir', 0):.2f}",
                "判定": f"{validity_colors.get(stats.get('validity', 'invalid'), '⚪')} {stats.get('validity', 'unknown')}",
            })
        if validity_data:
            st.dataframe(pd.DataFrame(validity_data), use_container_width=True)


def render_standard_results(
    results: Dict[str, Any],
    stock_data: Dict[str, Any],
    signals: Dict[str, Any],
    engine: Any,
    plot_multi_stock_signals: Callable[[Dict[str, Any], Dict[str, Any], list], Any],
    plot_signals_heatmap: Callable[[Dict[str, Any], list, list], Any],
    export_signals_to_csv: Callable[[Dict[str, Any], list, str], str],
) -> None:
    """展示普通策略回测结果。"""
    st.success(f"✅ 回测完成! 共回测 {len(stock_data)} 只股票")

    if not results:
        return

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总收益率", f"{results['total_return']:.2%}")
    with col2:
        st.metric("年化收益率", f"{results['annual_return']:.2%}")
    with col3:
        st.metric("夏普比率", f"{results['sharpe_ratio']:.2f}")
    with col4:
        st.metric("最大回撤", f"{results['max_drawdown']:.2%}")

    equity_df = results.get("equity_curve")
    if equity_df is not None and not equity_df.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=equity_df["date"],
            y=equity_df["total_value"],
            name="组合净值",
            line=dict(color="blue"),
        ))
        fig.update_layout(
            title="多股票组合权益曲线",
            xaxis_title="日期",
            yaxis_title="净值",
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

    signal_chart_type = st.radio(
        "📈 信号图展示方式",
        ["子图分股票展示", "热力图展示", "不显示信号图"],
        horizontal=True,
        key="signal_chart_type",
    )

    if signal_chart_type != "不显示信号图":
        if signal_chart_type == "子图分股票展示":
            fig_signals = plot_multi_stock_signals(stock_data, signals, list(stock_data.keys()))
            if fig_signals:
                st.plotly_chart(fig_signals, use_container_width=True)
        else:
            all_dates = equity_df["date"].tolist() if equity_df is not None and not equity_df.empty else []
            fig_heatmap = plot_signals_heatmap(signals, list(stock_data.keys()), all_dates)
            if fig_heatmap:
                st.plotly_chart(fig_heatmap, use_container_width=True)

    if st.button("📥 导出信号数据到CSV"):
        try:
            output_path = f"multi_stock_signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            export_signals_to_csv(signals, list(stock_data.keys()), output_path)
            st.success(f"✅ 信号数据已导出到: {output_path}")
        except Exception as exc:
            st.error(f"导出失败: {exc}")

    trade_details_df = engine.get_trade_details_df()
    if trade_details_df.empty:
        st.info("本次回测无交易记录")
        return

    st.subheader("📋 每次操作收益率明细")
    closed_trades = [td for td in engine.trade_details if td.status == "closed"]
    open_trades = [td for td in engine.trade_details if td.status == "open"]

    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    with stat_col1:
        st.metric("总交易次数", len(engine.trade_details))
    with stat_col2:
        st.metric("已完成交易", len(closed_trades))
    with stat_col3:
        st.metric("持有中", len(open_trades))
    with stat_col4:
        if closed_trades:
            win_count = len([t for t in closed_trades if t.net_return_rate > 0])
            win_rate = win_count / len(closed_trades)
            st.metric("胜率", f"{win_rate:.2%}")
        else:
            st.metric("胜率", "—")

    display_df = trade_details_df.drop(columns=["交易ID"], errors="ignore")
    st.dataframe(
        _style_trade_details_dataframe(display_df),
        use_container_width=True,
        hide_index=True,
    )
    if not open_trades:
        return

    st.markdown("**📌 持仓明细（持有中）:**")
    for td in open_trades:
        return_rate_pct = td.return_rate * 100
        st.markdown(
            f"- {td.symbol}: 买入日期 {str(td.entry_date)[:10]}, "
            f"价格 {td.entry_price:.2f}元, 数量 {td.entry_quantity}股, "
            f"当前价 {td.exit_price:.2f}元, "
            f"持有 {td.holding_days}天, "
            f"浮动盈亏 {td.profit:+,.2f}元 ({return_rate_pct:+.2f}%)"
        )

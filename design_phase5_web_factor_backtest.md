# Phase 5 设计文档：Web 界面 - 因子配置与回测面板

## 一、设计目标

为量化交易系统 Web 界面新增"多因子回测"标签页，提供完整的因子配置、回测运行、结果分析功能。

### 1.1 功能需求

1. **因子配置**
   - 选择要使用的因子（支持基本面因子、情绪因子、技术因子）
   - 设置因子基础权重（支持手动调整或 IC 加权）
   - 保存/加载因子配置方案

2. **回测参数配置**
   - 股票池选择（自选股/自定义股票列表）
   - 回测期间（开始/结束日期）
   - 初始资金、最大持仓数、调仓周期
   - 仓位分配方法、止损比例

3. **回测执行**
   - 一键运行多因子回测
   - 实时显示回测进度
   - 回测中断功能

4. **结果展示**
   - 收益指标（总收益、年化收益、夏普比率、最大回撤）
   - 因子分析（暴露度、归因、IC 有效性）
   - 可视化图表（权益曲线、因子暴露度、归因分析）
   - 交易明细表格

5. **配置管理**
   - 保存回测配置到数据库
   - 历史回测记录查询
   - 对比不同配置的回测结果

---

## 二、页面布局设计

### 2.1 整体布局

```
┌──────────────────────────────────────────────────────────────────────────┐
│  📊 多因子回测                                                              │
├────────────────────────────┬─────────────────────────────────────────────┤
│  侧边栏配置区                │  主内容区                                       │
│  ┌──────────────────────┐  │  ┌─────────────────────────────────────────┐ │
│  │ 📋 因子配置           │  │  │                                         │ │
│  │   - 因子选择          │  │  │  [回测结果标签页]                         │ │
│  │   - 权重设置          │  │  │  - 收益指标卡片                           │ │
│  │   - IC 加权开关       │  │  │  - 权益曲线图                             │ │
│  │   - 配置方案保存/加载  │  │  │  - 因子分析图表                           │ │
│  ├──────────────────────┤  │  │  - 交易明细表格                           │ │
│  │ ⚙️ 回测参数           │  │  │                                         │ │
│  │   - 股票池来源        │  │  │                                         │ │
│  │   - 回测期间          │  │  │                                         │ │
│  │   - 资金/持仓参数     │  │  │                                         │ │
│  │   - 风控参数          │  │  │                                         │ │
│  ├──────────────────────┤  │  │                                         │ │
│  │ 🚀 执行               │  │  │                                         │ │
│  │   [开始回测] [中断]   │  │  │                                         │ │
│  │   进度条              │  │  └─────────────────────────────────────────┘ │
│  └──────────────────────┘  │                                              │
└────────────────────────────┴─────────────────────────────────────────────┘
```

### 2.2 侧边栏结构

```python
# 侧边栏布局
with st.sidebar:
    st.markdown("## 📊 多因子回测")
    
    # ========== 因子配置区域 ==========
    st.markdown("### 📋 因子配置")
    
    # 因子选择
    factor_categories = {
        "基本面因子": ["roe", "roa", "gross_margin", "net_margin", "eps", "revenue_growth", "profit_growth"],
        "估值因子": ["pe", "pb", "ps", "pcf", "pcf_operating"],
        "技术因子": ["momentum_20", "momentum_60", "volatility_20", "volume_ratio"],
        "财务结构": ["debt_ratio", "current_ratio", "quick_ratio"],
        "情绪因子": ["turnover_rate", "price_volume_trend"]
    }
    
    # 因子分类多选
    selected_factors = {}
    for category, factors in factor_categories.items():
        with st.expander(f"☑️ {category}", expanded=True):
            selected = st.multiselect(
                "选择因子",
                factors,
                default=factors[:2] if len(factors) >= 2 else factors,
                key=f"factor_{category}"
            )
            for f in selected:
                selected_factors[f] = category
    
    # 权重设置模式
    weight_mode = st.radio(
        "权重设置模式",
        ["🤖 IC智能加权", "✏️ 手动设置权重"],
        help="IC智能加权：根据因子历史IC表现自动调整权重"
    )
    
    if weight_mode == "✏️ 手动设置权重":
        # 手动滑块调整
        st.markdown("**因子权重**")
        factor_weights = {}
        total_weight = 0
        for factor in selected_factors.keys():
            w = st.slider(factor, 0.0, 1.0, 0.2, 0.05, key=f"weight_{factor}")
            factor_weights[factor] = w
            total_weight += w
        
        # 归一化按钮
        if st.button("🔄 归一化权重"):
            if total_weight > 0:
                factor_weights = {k: v/total_weight for k, v in factor_weights.items()}
                st.success("权重已归一化")
        
        # 显示当前权重总和
        st.caption(f"当前权重总和: {sum(factor_weights.values()):.2%}")
    else:
        # IC 加权模式
        st.markdown("**IC 加权参数**")
        ic_update_freq = st.slider("IC更新频率（天）", 20, 120, 60, 10)
        ic_lookback = st.slider("IC历史窗口（天）", 60, 252, 120, 20)
        st.caption("IC智能加权将根据因子历史表现动态调整权重")
    
    # ========== 分隔线 ==========
    st.markdown("---")
    
    # ========== 回测参数区域 ==========
    st.markdown("### ⚙️ 回测参数")
    
    # 股票池来源
    stock_source = st.selectbox(
        "股票池来源",
        ["📈 自选股", "📋 自定义列表", "🏢 行业板块"],
        help="选择回测使用的股票池"
    )
    
    if stock_source == "📈 自选股":
        # 显示自选股数量
        wl_count = len(wl_manager.get_all_stocks())
        st.caption(f"将使用 {wl_count} 只自选股")
    elif stock_source == "📋 自定义列表":
        stock_list = st.text_area(
            "股票代码（逗号分隔）",
            "000001.SZ, 600000.SH, 600519.SH",
            height=80,
            help="输入股票代码，用逗号分隔"
        )
        symbols = [s.strip() for s in stock_list.split(",") if s.strip()]
    else:
        # 行业板块选择
        industry = st.selectbox(
            "选择行业",
            ["银行", "证券", "保险", "房地产", "医药", "白酒", "新能源"]
        )
    
    # 回测期间
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("开始日期", datetime(2023, 1, 1))
    with col2:
        end_date = st.date_input("结束日期", datetime(2024, 3, 19))
    
    # 资金参数
    initial_capital = st.number_input(
        "初始资金（元）",
        min_value=100000,
        max_value=100000000,
        value=1000000,
        step=100000,
        format="%d"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        max_positions = st.number_input("最大持仓数", 1, 20, 5)
    with col2:
        rebalance_days = st.number_input("调仓周期（天）", 1, 60, 5)
    
    position_method = st.selectbox(
        "仓位分配方法",
        ["equal", "factor_weighted", "risk_parity"],
        format_func=lambda x: {"equal": "等权分配", "factor_weighted": "因子加权", "risk_parity": "风险平价"}[x]
    )
    
    # 风控参数
    st.markdown("**🛡️ 风控参数**")
    stop_loss = st.slider("止损比例（%）", 0, 30, 10, 1) / 100
    max_single_position = st.slider("单一持仓上限（%）", 10, 50, 20, 5) / 100
    
    # ========== 分隔线 ==========
    st.markdown("---")
    
    # ========== 执行按钮 ==========
    st.markdown("### 🚀 执行回测")
    
    col1, col2 = st.columns(2)
    with col1:
        run_button = st.button("▶️ 开始回测", type="primary", use_container_width=True)
    with col2:
        stop_button = st.button("⏹️ 中断", use_container_width=True)
    
    # 进度显示
    progress_bar = st.progress(0)
    status_text = st.empty()
```

### 2.3 主内容区布局

```python
# 主内容区
if 'backtest_results' not in st.session_state:
    st.session_state.backtest_results = None

# 结果标签页
result_tabs = st.tabs([
    "📈 收益概览",
    "📊 因子分析",
    "📋 交易明细",
    "💾 配置管理"
])

# ========== 标签页 1: 收益概览 ==========
with result_tabs[0]:
    if st.session_state.backtest_results:
        results = st.session_state.backtest_results
        
        # 收益指标卡片行
        col1, col2, col3, col4, col5 = st.columns(5)
        
        metrics = [
            ("总收益率", f"{results['total_return']:.2%}", "📈"),
            ("年化收益率", f"{results['annual_return']:.2%}", "📊"),
            ("夏普比率", f"{results['sharpe_ratio']:.2f}", "⚖️"),
            ("最大回撤", f"{results['max_drawdown']:.2%}", "📉"),
            ("波动率", f"{results['volatility']:.2%}", "🌊")
        ]
        
        for col, (label, value, icon) in zip([col1, col2, col3, col4, col5], metrics):
            with col:
                st.metric(label, value, delta=icon)
        
        # 权益曲线图
        st.markdown("### 权益曲线")
        
        # 创建子图：组合收益 vs 基准
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            row_heights=[0.7, 0.3],
            subplot_titles=("组合权益 vs 基准", "超额收益")
        )
        
        # 组合权益曲线
        equity_dates = results['equity_curve']['date']
        equity_values = results['equity_curve']['total_value']
        benchmark_values = results['equity_curve']['benchmark']
        
        fig.add_trace(
            go.Scatter(
                x=equity_dates,
                y=equity_values,
                mode='lines',
                name='组合权益',
                line=dict(color='#1f77b4', width=2)
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=equity_dates,
                y=benchmark_values,
                mode='lines',
                name='基准',
                line=dict(color='#888888', width=1, dash='dash')
            ),
            row=1, col=1
        )
        
        # 超额收益
        excess_returns = [e - b for e, b in zip(equity_values, benchmark_values)]
        colors = ['#dc3545' if e > 0 else '#28a745' for e in excess_returns]
        
        fig.add_trace(
            go.Bar(
                x=equity_dates,
                y=excess_returns,
                name='超额收益',
                marker_color=colors,
                showlegend=False
            ),
            row=2, col=1
        )
        
        fig.update_layout(
            height=500,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # 月度收益统计
        st.markdown("### 月度收益统计")
        monthly_returns = results.get('monthly_returns')
        if monthly_returns is not None:
            st.dataframe(
                monthly_returns.style.background_gradient(
                    subset=['收益率'],
                    cmap='RdYlGn'
                ),
                use_container_width=True
            )
    else:
        # 无结果时显示引导界面
        st.info("👈 请在左侧配置参数后点击「开始回测」")
        
        # 显示近期因子 IC 表现
        st.markdown("### 最近 IC 表现")
        st.caption("基于最近 60 个交易日统计")
        
        # 示例表格
        sample_ic_data = pd.DataFrame({
            '因子': ['roe', 'pe', 'momentum_20', 'revenue_growth', 'debt_ratio'],
            'IC均值': [0.052, -0.008, 0.031, 0.018, -0.012],
            'IC标准差': [0.076, 0.082, 0.074, 0.068, 0.065],
            'IR': [0.68, -0.10, 0.42, 0.26, -0.18],
            '判定': ['强有效', '无效', '有效', '弱有效', '无效']
        })
        st.dataframe(sample_ic_data, use_container_width=True)

# ========== 标签页 2: 因子分析 ==========
with result_tabs[1]:
    if st.session_state.backtest_results:
        results = st.session_state.backtest_results
        factor_report = results.get('factor_report', {})
        
        # 因子配置概览
        st.markdown("### 因子配置概览")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 基础权重 vs IC权重对比表
            factor_weights = factor_report.get('factor_weights', {})
            ic_weights = factor_report.get('ic_weights', {})
            
            weight_comparison = []
            for factor in factor_weights:
                weight_comparison.append({
                    '因子': factor,
                    '基础权重': f"{factor_weights[factor]:.1%}",
                    'IC权重': f"{ic_weights.get(factor, 0):.1%}",
                    '变化': f"{ic_weights.get(factor, 0) - factor_weights[factor]:+.1%}"
                })
            
            st.dataframe(pd.DataFrame(weight_comparison), use_container_width=True)
        
        with col2:
            # IC 有效性判定
            st.markdown("**IC 有效性判定**")
            ic_validity = factor_report.get('ic_validity_report', {})
            
            validity_colors = {'strong': '🟢', 'normal': '🟡', 'weak': '🟠', 'invalid': '🔴'}
            
            validity_data = []
            for factor, stats in ic_validity.items():
                validity_data.append({
                    '因子': factor,
                    'IC均值': f"{stats['ic_mean']:.3f}",
                    'IR': f"{stats['ir']:.2f}",
                    '判定': f"{validity_colors.get(stats['validity'], '⚪')} {stats['validity']}"
                })
            
            st.dataframe(pd.DataFrame(validity_data), use_container_width=True)
        
        # 因子暴露度时序图
        st.markdown("### 因子暴露度时序")
        
        exposure_data = factor_report.get('exposure_timeseries')
        if exposure_data:
            fig = go.Figure()
            
            for factor in exposure_data.columns:
                fig.add_trace(go.Scatter(
                    x=exposure_data.index,
                    y=exposure_data[factor],
                    mode='lines',
                    name=factor,
                    stackgroup='one' if len(exposure_data.columns) <= 3 else None
                ))
            
            fig.update_layout(
                height=400,
                xaxis_title="日期",
                yaxis_title="暴露度"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # 因子收益归因
        st.markdown("### 因子收益归因")
        
        attribution = factor_report.get('attribution', {})
        if attribution:
            # 横向柱状图
            factors = list(attribution.keys())
            contributions = [attribution[f]['contribution'] for f in factors]
            returns = [attribution[f]['factor_return'] for f in factors]
            
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
        
        # 分层回测对比
        st.markdown("### 分层回测对比")
        
        quantile_returns = factor_report.get('quantile_returns')
        if quantile_returns is not None:
            st.dataframe(
                quantile_returns.style.background_gradient(
                    subset=['收益率', '夏普比率'],
                    cmap='RdYlGn'
                ),
                use_container_width=True
            )
    else:
        st.info("请先运行回测查看因子分析结果")

# ========== 标签页 3: 交易明细 ==========
with result_tabs[2]:
    if st.session_state.backtest_results:
        results = st.session_state.backtest_results
        trade_details = results.get('trade_details')
        
        if trade_details is not None:
            # 筛选器
            col1, col2, col3 = st.columns(3)
            with col1:
                symbol_filter = st.multiselect(
                    "股票筛选",
                    trade_details['symbol'].unique(),
                    default=[]
                )
            with col2:
                trade_type = st.selectbox(
                    "交易类型",
                    ["全部", "买入", "卖出"]
                )
            with col3:
                date_range = st.date_input(
                    "日期范围",
                    value=(datetime(2023, 1, 1), datetime(2024, 3, 19))
                )
            
            # 应用筛选
            filtered = trade_details.copy()
            if symbol_filter:
                filtered = filtered[filtered['symbol'].isin(symbol_filter)]
            if trade_type == "买入":
                filtered = filtered[filtered['direction'] == 'buy']
            elif trade_type == "卖出":
                filtered = filtered[filtered['direction'] == 'sell']
            
            # 显示交易明细
            st.dataframe(
                filtered.style.applymap(
                    lambda x: 'color: #dc3545' if isinstance(x, (int, float)) and x > 0 else (
                        'color: #28a745' if isinstance(x, (int, float)) and x < 0 else ''),
                    subset=['收益率', '收益金额']
                ),
                use_container_width=True
            )
            
            # 统计摘要
            st.markdown("**交易统计**")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_trades = len(filtered)
                st.metric("总交易次数", total_trades)
            with col2:
                buy_trades = len(filtered[filtered['direction'] == 'buy'])
                st.metric("买入次数", buy_trades)
            with col3:
                sell_trades = len(filtered[filtered['direction'] == 'sell'])
                st.metric("卖出次数", sell_trades)
            with col4:
                avg_holding_days = filtered['holding_days'].mean() if 'holding_days' in filtered else 0
                st.metric("平均持有天数", f"{avg_holding_days:.1f}")
        else:
            st.info("无交易明细数据")
    else:
        st.info("请先运行回测查看交易明细")

# ========== 标签页 4: 配置管理 ==========
with result_tabs[3]:
    st.markdown("### 💾 配置管理")
    
    # 保存当前配置
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**📤 保存当前配置**")
        config_name = st.text_input("配置名称", placeholder="我的因子配置_v1")
        
        if st.button("💾 保存", use_container_width=True):
            if config_name:
                save_config(config_name, factor_config, backtest_params)
                st.success(f"配置「{config_name}」已保存")
            else:
                st.warning("请输入配置名称")
    
    with col2:
        st.markdown("**📥 加载已有配置**")
        saved_configs = load_saved_configs()
        
        if saved_configs:
            config_to_load = st.selectbox(
                "选择配置",
                saved_configs,
                format_func=lambda x: x['name']
            )
            
            if st.button("📥 加载", use_container_width=True):
                load_config(config_to_load['id'])
                st.success(f"已加载配置「{config_to_load['name']}」")
        else:
            st.info("暂无保存的配置")
    
    # 历史回测记录
    st.markdown("### 📜 历史回测记录")
    
    history = load_backtest_history()
    if history:
        st.dataframe(
            history[['run_name', 'start_date', 'end_date', 'total_return', 'sharpe_ratio', 'created_at']],
            use_container_width=True
        )
    else:
        st.info("暂无历史回测记录")
```

---

## 三、核心交互逻辑

### 3.1 回测执行流程

```python
def run_backtest():
    """执行回测的主函数"""
    
    # 1. 参数准备
    params = {
        'symbols': get_selected_symbols(stock_source),
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'initial_capital': initial_capital,
        'max_positions': max_positions,
        'rebalance_days': rebalance_days,
        'position_method': position_method,
        'stop_loss': stop_loss,
        'factor_weights': get_factor_weights(weight_mode, selected_factors),
        'use_ic_weighting': (weight_mode == "🤖 IC智能加权"),
        'ic_update_freq': ic_update_freq if weight_mode == "🤖 IC智能加权" else None,
    }
    
    # 2. 进度回调函数
    def progress_callback(percent, message):
        progress_bar.progress(percent / 100)
        status_text.text(f"{message}...")
    
    # 3. 执行回测
    try:
        with st.spinner("正在运行回测，请稍候..."):
            results = run_multi_factor_backtest(
                **params,
                progress_callback=progress_callback
            )
        
        # 4. 保存结果
        st.session_state.backtest_results = results
        
        # 5. 保存到历史记录
        save_backtest_record(params, results)
        
        st.success("回测完成！")
        
    except Exception as e:
        st.error(f"回测出错: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
```

### 3.2 状态管理

```python
# Streamlit Session State 结构
st.session_state.multi_factor_backtest = {
    'config': {
        'factor_weights': {...},
        'ic_weighted': True,
        'ic_update_freq': 60,
    },
    'backtest_params': {
        'symbols': [...],
        'start_date': '2023-01-01',
        'end_date': '2024-03-19',
        'initial_capital': 1000000,
        # ...
    },
    'results': {
        'total_return': 0.2346,
        'annual_return': 0.1832,
        # ...
        'factor_report': {...}
    },
    'history': [...]
}
```

---

## 四、组件清单

### 4.1 侧边栏组件

| 组件 | 类型 | 说明 |
|------|------|------|
| 因子分类选择器 | expander + multiselect | 分5类展示因子，支持多选 |
| 权重模式切换 | radio | IC智能加权 / 手动设置 |
| 因子权重滑块 | slider | 0-100%，每个因子一个 |
| IC加权参数 | slider | 更新频率、历史窗口 |
| 股票池来源 | selectbox | 自选股/自定义/行业 |
| 回测期间 | date_input | 开始/结束日期 |
| 资金参数 | number_input | 初始资金 |
| 持仓参数 | number_input | 最大持仓数、调仓周期 |
| 仓位方法 | selectbox | 等权/因子加权/风险平价 |
| 风控参数 | slider | 止损比例、单一持仓上限 |
| 执行按钮 | button | 开始回测、中断 |

### 4.2 主内容区组件

| 组件 | 类型 | 说明 |
|------|------|------|
| 收益指标卡片 | columns + metric | 5个核心指标 |
| 权益曲线图 | plotly_chart | 组合 vs 基准 + 超额收益 |
| 月度收益表 | dataframe | 带颜色梯度 |
| 因子配置表 | dataframe | 基础权重 vs IC权重 |
| IC判定表 | dataframe | 有效性判定 |
| 暴露度时序图 | plotly_chart | 堆叠面积图 |
| 归因柱状图 | plotly_chart | 收益贡献 + 因子收益率 |
| 分层收益表 | dataframe | 带颜色梯度 |
| 交易明细表 | dataframe | 可筛选、可排序 |
| 配置保存/加载 | columns | 表单 + 选择框 |
| 历史记录表 | dataframe | 回测历史 |

---

## 五、API 接口设计

### 5.1 后端接口

```python
# 新增 API 路由（在 app.py 中）

# 1. 获取因子列表
@st.cache_data(ttl=3600)
def get_available_factors():
    """
    Returns:
        Dict[str, List[str]]: {category: [factors]}
    """

# 2. 获取 IC 统计
def get_factor_ic_stats(factor_names: List[str], lookback_days: int = 60):
    """
    Returns:
        Dict[str, Dict]: {factor: {ic_mean, ic_std, ir, ...}}
    """

# 3. 保存回测配置
def save_backtest_config(name: str, config: Dict):
    """保存配置到数据库"""

# 4. 加载回测配置
def load_backtest_config(config_id: int):
    """从数据库加载配置"""

# 5. 运行多因子回测
def run_backtest_api(params: Dict, progress_callback=None):
    """
    执行回测，返回结果
    """

# 6. 获取历史回测记录
def get_backtest_history(limit: int = 50):
    """获取历史回测记录"""
```

### 5.2 数据结构

```python
# 回测配置结构
BacktestConfig = {
    'name': '我的配置',
    'factor_weights': {
        'roe': 0.25,
        'pe': 0.15,
        'momentum_20': 0.20,
        'revenue_growth': 0.15,
        'debt_ratio': 0.10,
        'volume_ratio': 0.15
    },
    'ic_weighted': True,
    'ic_update_freq': 60,
    'ic_lookback': 120,
    'stock_source': 'watchlist',  # or 'custom', 'industry'
    'stock_list': [],  # if custom
    'industry': None,  # if industry
    'start_date': '2023-01-01',
    'end_date': '2024-03-19',
    'initial_capital': 1000000,
    'max_positions': 5,
    'rebalance_days': 5,
    'position_method': 'equal',
    'stop_loss': 0.10,
    'max_single_position': 0.20
}

# 回测结果结构
BacktestResult = {
    # 基础指标
    'total_return': 0.2346,
    'annual_return': 0.1832,
    'sharpe_ratio': 1.45,
    'max_drawdown': -0.1234,
    'volatility': 0.1823,
    'total_trades': 50,
    
    # 权益曲线
    'equity_curve': pd.DataFrame({
        'date': [...],
        'total_value': [...],
        'benchmark': [...]
    }),
    
    # 月度收益
    'monthly_returns': pd.DataFrame({
        'month': [...],
        'portfolio_return': [...],
        'benchmark_return': [...]
    }),
    
    # 交易明细
    'trade_details': pd.DataFrame({
        'trade_id': [...],
        'date': [...],
        'symbol': [...],
        'direction': [...],  # 'buy' or 'sell'
        'price': [...],
        'quantity': [...],
        'amount': [...],
        'commission': [...],
        'holding_days': [...],
        'return_rate': [...],
        'profit': [...]
    }),
    
    # 因子报告
    'factor_report': {
        'factor_weights': {...},  # 基础权重
        'ic_weights': {...},       # IC调整后权重
        'ic_validity_report': {...},
        'exposure_timeseries': pd.DataFrame,
        'attribution': {...},
        'quantile_returns': pd.DataFrame
    }
}
```

---

## 六、实施步骤

| 优先级 | 任务 | 文件 | 依赖 |
|--------|------|------|------|
| **P0** | 创建 `web/factor_backtest_pages.py` 因子回测页面 | web/ | Phase 4 后端 |
| **P0** | 在 `web/app.py` 集成新标签页 | web/app.py | - |
| **P0** | 实现回测执行函数和进度回调 | web/app.py | MultiFactorBacktest |
| **P1** | 实现结果展示图表（权益曲线、暴露度等） | web/app.py | plotly |
| **P1** | 实现配置保存/加载功能 | web/app.py | DataManager |
| **P2** | 实现历史回测记录查询 | web/app.py | DataManager |
| **P2** | 样式优化和响应式布局 | web/app.py | - |

---

## 七、页面切换逻辑

```python
# app.py 中的 tab 结构调整

# 原5个标签页 → 新6个标签页
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "⭐ 自选股管理",
    "🎯 策略回测",      # 保留原有单股票/多股票回测
    "📊 多因子回测",    # 新增：Phase 5
    "📈 信号扫描",
    "📉 绩效分析",
    "🔬 因子分析"
])

# 多因子回测标签页 - 完全独立的新页面
with tab3:
    factor_backtest_page()
```

---

## 八、与其他页面的关系

```
┌─────────────────────────────────────────────────────────────────┐
│                        量化交易系统 Web 界面                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ⭐ 自选股管理                                                   │
│      │                                                          │
│      ├── 添加/删除自选股                                         │
│      ├── 查看行情                                               │
│      └── 导出股票列表 ──────────────┐                           │
│                                    │                           │
│  🎯 策略回测 ◄─────────────────────┘                           │
│      │                     ▲                                   │
│      ├── 单股票回测         │                                   │
│      └── 多股票回测         │                                   │
│                             │                                   │
│  📊 多因子回测 ──────────────┼─────────────────────────────►   │
│      │                     │      （使用自选股或自定义列表）      │
│      ├── 因子配置           │                                   │
│      ├── IC智能加权         │                                   │
│      ├── 运行回测           │                                   │
│      ├── 收益分析           │                                   │
│      ├── 因子暴露度分析     │                                   │
│      └── 交易明细           │                                   │
│                             │                                   │
│  📈 信号扫描                 │                                   │
│      │                     │                                   │
│      └── 批量扫描信号 ──────┘                                   │
│                                                                 │
│  📉 绩效分析                 │                                   │
│      │                     │                                   │
│      └── 查看持仓绩效 ──────┘                                   │
│                                                                 │
│  🔬 因子分析                                                   │
│      │                                                          │
│      ├── IC时间序列                                             │
│      ├── 分层回测                                              │
│      └── 相关性矩阵                                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 九、预期效果

### 9.1 用户体验

1. **配置简单**：默认因子配置开箱即用
2. **反馈及时**：回测进度实时显示
3. **分析深入**：多维度因子归因分析
4. **可复现**：配置保存和历史记录

### 9.2 性能目标

- 回测启动时间 < 2秒（数据已缓存情况下）
- 100只股票、1年数据回测 < 30秒
- 页面响应 < 100ms

### 9.3 数据准确性

- 收益计算与 MultiFactorBacktest 完全一致
- IC 统计与 ICAnalyzer 计算结果一致
- 交易记录与回测引擎交易日志一致
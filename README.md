# 量化交易系统 (Quant Trading System)

一个基于 Python 的完整量化交易系统，包含数据获取、因子计算、策略回测、风险管理和可视化分析等功能。

## 🚀 功能特性

### 📊 数据模块
- **实时行情数据**：通过 akshare 获取 A 股实时数据
- **历史数据管理**：自动缓存和更新历史数据
- **多周期支持**：日线、分钟线数据
- **财务数据**：集成财务报表数据

### 🔬 因子计算
- **技术指标**：MACD、KDJ、RSI、布林带、均线系统等
- **自定义因子**：动量、均值回归、波动率等
- **因子分析**：IC分析、分位数分析、自相关性

### 🎯 策略模块
- **均线交叉策略**：双均线金叉死叉交易
- **MACD策略**：基于MACD柱状图信号
- **布林带策略**：价格触及轨道交易
- **RSI策略**：超买超卖交易
- **多因子策略**：综合多个因子选股

### 🧪 回测引擎
- **事件驱动回测**：支持限价单、止损单
- **向量化回测**：高速回测，适合参数优化
- **滑点和手续费**：真实模拟交易成本

### 📈 绩效分析
- **收益指标**：总收益、年化收益、月收益
- **风险指标**：波动率、VaR、CVaR、偏度、峰度
- **风险调整收益**：夏普比率、索提诺比率、卡玛比率、信息比率
- **回撤分析**：最大回撤、回撤持续时间、恢复时间
- **交易统计**：胜率、盈亏比、连续盈亏

### 🛡️ 风险管理
- **仓位管理**：固定金额、固定比例、波动率调整、凯利公式、风险平价
- **止损止盈**：支持多种止损策略
- **风险监控**：回撤限制、日亏损限制、集中度控制

### 🖥️ Web界面
- **交互式分析**：基于 Streamlit 的 Web 界面
- **实时图表**：K线图、权益曲线、因子图表
- **策略对比**：多策略绩效对比
- **参数优化**：可视化参数调优

## 📁 项目结构

```
quant_system/
├── data/                   # 数据模块
│   ├── __init__.py
│   ├── data_manager.py     # 数据管理器
│   ├── market_data.py      # 市场数据
│   └── factor_data.py      # 因子计算
│
├── backtest/               # 回测模块
│   ├── __init__.py
│   ├── engine.py           # 回测引擎
│   └── performance.py      # 绩效分析
│
├── strategy/               # 策略模块
│   ├── __init__.py
│   ├── base.py             # 策略基类
│   ├── moving_average.py   # 均线策略
│   └── multi_factor.py     # 多因子策略
│
├── risk/                   # 风险管理
│   ├── __init__.py
│   ├── manager.py          # 风险管理器
│   └── stop_loss.py        # 止损管理
│
├── web/                    # Web界面
│   └── app.py              # Streamlit应用
│
├── main.py                 # 主入口
├── requirements.txt        # 依赖列表
└── README.md              # 项目说明
```

## 🛠️ 安装部署

### 1. 安装依赖

```bash
cd quant_system
pip install -r requirements.txt
```

### 2. 运行主程序

```bash
# 运行演示
python main.py

# 启动Web界面
streamlit run web/app.py
```

## 📖 使用示例

### 快速开始

```python
from quant_system.main import QuantSystem

# 初始化系统
system = QuantSystem({
    'initial_capital': 1000000,
    'commission_rate': 0.0003
})

# 运行回测
results = system.run_backtest(
    strategy='ma_cross',
    symbol='000001',
    start_date='2023-01-01',
    end_date='2024-12-31',
    strategy_params={'fast_period': 20, 'slow_period': 60}
)

# 生成报告
system.generate_report('backtest_report.txt')
```

### 策略对比

```python
# 对比多个策略
comparison = system.compare_strategies(
    strategies=['ma_cross', 'macd', 'rsi'],
    symbol='000001',
    start_date='2023-01-01',
    end_date='2024-12-31'
)
print(comparison)
```

### 参数优化

```python
# 优化策略参数
optimization = system.optimize_parameters(
    strategy='ma_cross',
    symbol='000001',
    start_date='2023-01-01',
    end_date='2024-12-31',
    param_grid={
        'fast_period': [5, 10, 20],
        'slow_period': [30, 60, 120]
    }
)
print(f"最优参数: {optimization['best_params']}")
```

### 自定义策略

```python
from quant_system.strategy.base import Strategy, Signal, SignalType

class MyStrategy(Strategy):
    def __init__(self, params=None):
        super().__init__("MyStrategy", params)
    
    def generate_signals(self, data):
        signals = []
        # 实现你的策略逻辑
        # ...
        return signals
    
    def get_signal_series(self, data):
        # 返回信号序列用于向量化回测
        return signal_series
```

## 📊 绩效指标说明

### 收益指标
- **总收益率**：策略整个回测期的总收益
- **年化收益率**：将总收益年化后的收益率
- **日/月收益率**：不同时间维度的收益统计

### 风险指标
- **年化波动率**：收益率的标准差，衡量风险大小
- **下行波动率**：只计算负收益的标准差
- **VaR (Value at Risk)**：在95%置信度下的最大可能损失
- **CVaR (Conditional VaR)**：超过VaR时的平均损失

### 风险调整收益
- **夏普比率**：(年化收益-无风险利率)/年化波动率
- **索提诺比率**：使用下行波动率代替总波动率
- **卡玛比率**：年化收益/最大回撤
- **信息比率**：超额收益/跟踪误差

### 回撤指标
- **最大回撤**：从高点到低点的最大跌幅
- **回撤持续时间**：回撤持续的交易日数
- **恢复时间**：从回撤中恢复所需时间

## ⚠️ 风险提示

1. **本系统仅供学习研究使用，不构成投资建议**
2. 回测结果不代表未来收益
3. 量化交易存在风险，请谨慎使用
4. 实盘交易前请充分测试策略

## 🔧 技术栈

- **Python 3.8+**
- **数据处理**：pandas, numpy
- **数据获取**：akshare
- **技术指标**：pandas-ta
- **可视化**：matplotlib, plotly, streamlit
- **数据库**：SQLite

## 📈 未来计划

- [ ] 机器学习因子挖掘
- [ ] 更多策略模板
- [ ] 实盘交易接口
- [ ] 多因子模型优化
- [ ] 组合优化器
- [ ] 实时数据推送

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**免责声明**：本系统仅供学习研究使用，投资有风险，入市需谨慎。

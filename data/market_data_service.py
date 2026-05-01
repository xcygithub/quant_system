"""
市场数据服务（已移除 Akshare）

负责股票列表、分钟线、指数等市场行情数据获取，统一走 Baostock。
"""

from datetime import datetime, timedelta

import pandas as pd


class MarketDataService:
    """市场数据服务。"""

    @staticmethod
    def _load_baostock():
        """延迟加载 baostock。"""
        try:
            import baostock as bs  # type: ignore
            return bs
        except ImportError:
            return None

    @staticmethod
    def _to_baostock_code(symbol: str) -> str:
        """将证券代码转换为 baostock 格式。"""
        if symbol.endswith(".SH"):
            return f"sh.{symbol[:-3]}"
        if symbol.endswith(".SZ"):
            return f"sz.{symbol[:-3]}"
        if symbol.endswith(".BJ"):
            return f"bj.{symbol[:-3]}"
        return f"sh.{symbol}" if symbol.startswith(("6", "9")) else f"sz.{symbol}"

    def get_stock_list(self, market: str = "all") -> pd.DataFrame:
        """获取股票列表。"""
        bs = self._load_baostock()
        if bs is None:
            print("获取股票列表失败: 未安装 baostock")
            return pd.DataFrame()
        try:
            lg = bs.login()
            if lg.error_code != "0":
                print(f"获取股票列表失败: baostock登录失败 {lg.error_msg}")
                return pd.DataFrame()

            rs = bs.query_all_stock(day=datetime.now().strftime("%Y-%m-%d"))
            rows = []
            while rs.next():
                row = rs.get_row_data()
                code = row[0]
                name = row[1]
                if code.startswith("sh."):
                    market_code = "SH"
                elif code.startswith("sz."):
                    market_code = "SZ"
                else:
                    market_code = "BJ"
                rows.append({
                    "symbol": code.split(".")[1] + f".{market_code}",
                    "name": name,
                    "market": market_code,
                })
            bs.logout()

            df = pd.DataFrame(rows)
            if df.empty:
                return df
            if market == "sh":
                return df[df["market"] == "SH"].reset_index(drop=True)
            if market == "sz":
                return df[df["market"] == "SZ"].reset_index(drop=True)
            return df.reset_index(drop=True)
        except Exception as exc:
            print(f"获取股票列表失败: {exc}")
            try:
                bs.logout()
            except Exception:
                pass
            return pd.DataFrame()

    def get_minute_kline(self, symbol: str, period: str = "1") -> pd.DataFrame:
        """获取分钟线数据。"""
        bs = self._load_baostock()
        if bs is None:
            print(f"获取{symbol}分钟数据失败: 未安装 baostock")
            return pd.DataFrame()
        try:
            lg = bs.login()
            if lg.error_code != "0":
                print(f"获取{symbol}分钟数据失败: baostock登录失败 {lg.error_msg}")
                return pd.DataFrame()

            code = self._to_baostock_code(symbol)
            rs = bs.query_history_k_data_plus(
                code,
                "date,time,code,open,high,low,close,volume,amount",
                start_date=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                end_date=datetime.now().strftime("%Y-%m-%d"),
                frequency=period,
                adjustflag="2",
            )
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            bs.logout()
            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows, columns=["date", "time", "code", "open", "high", "low", "close", "volume", "amount"])
            for col in ["open", "high", "low", "close", "volume", "amount"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["datetime"] = pd.to_datetime(df["date"] + " " + df["time"].astype(str).str[:6], format="%Y-%m-%d %H%M%S", errors="coerce")
            df["symbol"] = symbol
            return df[["datetime", "open", "high", "low", "close", "volume", "amount", "symbol"]].dropna(subset=["datetime"])
        except Exception as exc:
            print(f"获取{symbol}分钟数据失败: {exc}")
            try:
                bs.logout()
            except Exception:
                pass
            return pd.DataFrame()

    def get_index_list(self) -> pd.DataFrame:
        """获取指数列表（内置主流指数）。"""
        return pd.DataFrame([
            {"symbol": "000001.SH", "name": "上证指数", "market": "SH"},
            {"symbol": "000300.SH", "name": "沪深300", "market": "SH"},
            {"symbol": "000905.SH", "name": "中证500", "market": "SH"},
            {"symbol": "399001.SZ", "name": "深证成指", "market": "SZ"},
            {"symbol": "399006.SZ", "name": "创业板指", "market": "SZ"},
        ])

    def get_index_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取指数K线数据。"""
        bs = self._load_baostock()
        if bs is None:
            print(f"获取指数{symbol}数据失败: 未安装 baostock")
            return pd.DataFrame()
        try:
            lg = bs.login()
            if lg.error_code != "0":
                print(f"获取指数{symbol}数据失败: baostock登录失败 {lg.error_msg}")
                return pd.DataFrame()

            code = self._to_baostock_code(symbol)
            rs = bs.query_history_k_data_plus(
                code,
                "date,code,open,high,low,close,volume,amount,pctChg",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="2",
            )
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            bs.logout()
            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows, columns=["date", "code", "open", "high", "low", "close", "volume", "amount", "pct_change"])
            for col in ["open", "high", "low", "close", "volume", "amount", "pct_change"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["symbol"] = symbol
            return df
        except Exception as exc:
            print(f"获取指数{symbol}数据失败: {exc}")
            try:
                bs.logout()
            except Exception:
                pass
            return pd.DataFrame()

    def update_all_data(self) -> None:
        """全量更新入口（市场基础信息 + 指数）。"""
        print("开始更新数据...")
        print("更新股票列表...")
        _ = self.get_stock_list()

        print("更新指数数据...")
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        for idx in ["000001.SH", "000300.SH", "000905.SH", "399001.SZ", "399006.SZ"]:
            self.get_index_kline(idx, start_date, end_date)

        print("数据更新完成")

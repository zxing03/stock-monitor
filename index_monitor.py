import streamlit as st
import akshare as ak
import pandas as pd

# -------------------------- 页面配置 --------------------------
st.set_page_config(page_title="指数监控", layout="wide")
st.title("📊 沪深300 实时监控系统")

# -------------------------- 侧边栏 --------------------------
st.sidebar.header("参数设置")
boll_period = st.sidebar.number_input("BOLL周期", value=20)
boll_std = st.sidebar.number_input("BOLL标准差", value=2.0)

# -------------------------- 数据获取（缓存） --------------------------
@st.cache_data(ttl=3600)
def get_data(period, std):
    try:
        # 获取K线
        df = ak.stock_zh_index_daily(symbol="sh000300").tail(200)
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])

        # 布林带
        df["mid"] = df["close"].rolling(window=period).mean()
        df["std"] = df["close"].rolling(window=period).std()
        df["upper"] = df["mid"] + std * df["std"]
        df["lower"] = df["mid"] - std * df["std"]

        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        df["rsi"] = 100 - (100 / (1 + rs))

        # MACD
        df["ema12"] = df["close"].ewm(span=12, adjust=False).mean()
        df["ema26"] = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = df["ema12"] - df["ema26"]
        df["signal"] = df["macd"].ewm(span=9, adjust=False).mean()

        # PE
        try:
            pe_df = ak.stock_zh_index_pe_lg(symbol="000300.XSHG")
            pe = round(pe_df["pe"].iloc[-1], 2)
        except:
            pe = "获取失败"

        return df.dropna(), pe

    except Exception as e:
        return None, str(e)

# -------------------------- 运行 --------------------------
data_result = get_data(boll_period, boll_std)

if data_result[0] is None:
    st.error(f"数据获取失败：{data_result[1]}")
else:
    df, pe_val = data_result
    latest = df.iloc[-1]

    # 数据卡片（⚠️ 这里去掉了 key，不会报错）
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("最新价格", f"{latest['close']:.2f}")
    col2.metric("PE-TTM", pe_val)
    col3.metric("BOLL位置", f"{((latest['close']-latest['mid'])/(latest['upper']-latest['mid'])):.2f}")
    col4.metric("RSI", f"{latest['rsi']:.2f}")

    # 图表
    st.subheader("📈 价格 + 布林带")
    st.line_chart(df.tail(100).set_index("date")[["close", "mid", "upper", "lower"]])

    st.subheader("📊 MACD")
    st.line_chart(df.tail(100).set_index("date")[["macd", "signal"]])

    st.success("✅ 数据加载完成，运行正常！")

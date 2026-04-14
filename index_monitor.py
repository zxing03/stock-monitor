import streamlit as st
import akshare as ak
import pandas as pd
import pandas_ta as ta
import datetime

# --- 1. 网页配置 ---
st.set_page_config(page_title="指数监控系统", layout="wide")
st.title("📊 指数实时监控系统")
st.caption("项目目标：零成本、全自定义、全设备访问")

# --- 2. 侧边栏设置 ---
st.sidebar.header("⚙️ 参数设置")
target_index = st.sidebar.selectbox("监控标的", ["沪深300 (sh000300)"])
st.sidebar.markdown("---")
st.sidebar.subheader("布林线 (BOLL) 参数")
boll_period = st.sidebar.number_input("计算周期 (n)", value=20)
boll_std = st.sidebar.number_input("标准差倍数", value=2.0)


# --- 3. 获取与计算数据 ---
@st.cache_data(ttl=3600)
def get_full_analysis():
    # 获取300天数据确保指标计算稳定
    df = ak.stock_zh_index_daily(symbol="sh000300")
    df = df.tail(300)
    df['date'] = pd.to_datetime(df['date'])
    df = df.dropna()

    # 使用 pandas_ta 库一次性添加多个指标
    df.ta.bbands(length=boll_period, std=boll_std, append=True)
    df.ta.macd(append=True)
    df.ta.rsi(length=14, append=True)

    # 获取 PE 数据
    try:
        pe_df = ak.stock_zh_index_value_indicator(symbol="sh000300")
        current_pe = pe_df['pe'].iloc[-1]
    except:
        current_pe = "数据同步中"

    return df, current_pe


# --- 4. 主逻辑与异常处理 ---
try:
    with st.spinner('正在同步最新行情数据...'):
        df, pe_val = get_full_analysis()
        latest = df.iloc[-1]

    # 动态匹配生成的列名
    upper_col = [c for c in df.columns if c.startswith('BBU')][0]
    mid_col = [c for c in df.columns if c.startswith('BBM')][0]
    lower_col = [c for c in df.columns if c.startswith('BBL')][0]
    rsi_col = [c for c in df.columns if c.startswith('RSI')][0]

    # 展示核心指标卡片
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("最新价格", f"{latest['close']:.2f}")
    c2.metric("实时 PE", pe_val)

    # 计算位置百分比
    pos = (latest['close'] - latest[mid_col]) / (latest[upper_col] - latest[mid_col])
    c3.metric("BOLL 相对位置", f"{pos:.2f}")
    c4.metric("RSI 强弱度", f"{latest[rsi_col]:.2f}")

    # 绘制图表
    st.subheader("📈 行情走势与布林带")
    st.line_chart(df.tail(100).set_index('date')[['close', mid_col, upper_col, lower_col]])

    st.subheader("📊 MACD 指标趋势")
    # 查找 MACD 相关列
    m_cols = [c for c in df.columns if 'MACD' in c]
    st.area_chart(df.tail(100).set_index('date')[m_cols])

    st.success("网页运行正常，数据已更新。")

# 就是这一块不能少！
except Exception as e:
    st.error(f"发现异常：{e}")
    st.info("提示：请检查网络连接或尝试点击网页右上角的 'Rerun'。")
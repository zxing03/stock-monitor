import akshare as ak
import pandas as pd
import requests
import time
import warnings
import os
from datetime import datetime, timedelta

# 屏蔽不必要的警告
warnings.filterwarnings("ignore")

# --- 1. 核心配置 ---
SC_KEY = os.environ.get("SC_KEY", "")
RSI_UPPER = 80
RSI_LOWER = 20
RETRY_TIMES = 2
REQUEST_INTERVAL = 0.5

# 监控清单
MONITOR_LIST = [
    ["新华中小市值", None, "519089"],
    ["科创芯片ETF", "588800", "016886"],
    ["人工智能ETF", "159819", "012894"],
    ["纳指精选", None, "012351"],
    ["纳指100", None, "006479"],
    ["标普500ETF", "513500", "006075"],
    ["恒生科技ETF", "513760", "013402"],
    ["黄金ETF", "518800", "000219"],
    ["纳指100ETF联接", "513870", "161130"],
    ["金融科技ETF", "159851", "013487"],
    ["全球成长精选", None, "012348"],
    ["德邦稳盈混合", None, "010278"],
    ["中证500低波", None, "003986"],
    ["白银期货LOF", "161226", "001871"],
    ["平安医疗健康", None, "010343"],
    ["香港银行投资", None, "006435"],
    ["港股通互联网", None, "013117"],
    ["酒指数", None, "160632"],
    ["红利低波", None, "007751"],
    ["大宗商品ETF", "510170", "257060"],
    ["有色金属ETF", "512400", "004432"]
]

# --- 纯手写指标计算（完全不用pandas_ta）---
def calculate_rsi(df, period=6):
    """纯Python计算RSI指标"""
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_bbands(df, period=20, std=2):
    """纯Python计算布林带指标"""
    mid = df['close'].rolling(window=period).mean()
    std_dev = df['close'].rolling(window=period).std()
    upper = mid + std * std_dev
    lower = mid - std * std_dev
    return mid, upper, lower

# --- 接口重试装饰器 ---
def retry_decorator(max_retries=RETRY_TIMES, delay=1):
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries >= max_retries:
                        print(f"⚠️ 接口调用失败：{str(e)}")
                        return None
                    time.sleep(delay)
            return None
        return wrapper
    return decorator

def send_wechat(title, content):
    if not SC_KEY or SC_KEY.strip() == "":
        print("ℹ️ SC_KEY未配置，跳过推送")
        return
    try:
        requests.post(
            f"https://sctapi.ftqq.com/{SC_KEY}.send",
            data={"title": title, "desp": content},
            timeout=10
        )
        print("✅ 微信推送成功")
    except Exception as e:
        print(f"❌ 推送失败：{str(e)}")

@retry_decorator(max_retries=RETRY_TIMES, delay=1)
def get_data(cn_code, of_code):
    if not cn_code and not of_code:
        return None
    
    try:
        if cn_code and cn_code != "-":
            symbol = f"sh{cn_code}" if cn_code.startswith(('5', '6')) else f"sz{cn_code}"
            df = ak.stock_zh_index_daily_em(symbol=symbol).tail(100)
            df = df.rename(columns={'close': 'close', 'date': 'date'})
        else:
            df = ak.fund_open_fund_info_em(symbol=of_code, indicator="单位净值走势")
            df = df[['净值日期', '单位净值']].rename(columns={'净值日期': 'date', '单位净值': 'close'}).tail(100)

        if df.empty or 'close' not in df.columns:
            return None
        
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df = df.dropna(subset=['close'])
        
        if len(df) < 30:
            return None

        return df
    except Exception as e:
        raise e

def run_analysis():
    print(f"\n正在扫描: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    all_alerts = []

    for idx, (name, cn_code, of_code) in enumerate(MONITOR_LIST):
        if idx > 0:
            time.sleep(REQUEST_INTERVAL)
        
        print(f"🔍 分析: {name}")
        df = get_data(cn_code, of_code)
        
        if df is None or len(df) < 30:
            print(f"ℹ️ {name} 数据不足，跳过")
            continue

        # 纯手写计算指标
        df['rsi'] = calculate_rsi(df, period=6)
        df['mid'], df['upper'], df['lower'] = calculate_bbands(df, period=20)
        
        latest = df.iloc[-1]
        price = latest['close']
        rsi_val = latest['rsi']
        bbl = latest['lower']
        bbu = latest['upper']

        # 安全校验
        if pd.isna(rsi_val) or pd.isna(bbl) or pd.isna(bbu):
            print(f"ℹ️ {name} 指标计算失败")
            continue

        # 触发判断
        res = []
        if price <= bbl: res.append(f"触及BOLL下轨({price:.3f})")
        if price >= bbu: res.append(f"触及BOLL上轨({price:.3f})")
        if rsi_val <= RSI_LOWER: res.append(f"RSI超跌({rsi_val:.2f})")
        if rsi_val >= RSI_UPPER: res.append(f"RSI超买({rsi_val:.2f})")

        if res:
            all_alerts.append(f"**{name}**: " + " / ".join(res))

    if all_alerts:
        content = "### 🔔 交易预警\n\n" + "\n\n".join(all_alerts) + \
                  f"\n\n---\n时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        send_wechat("⚠️ 基金监控提醒", content)
        print("\n🚩 已发送预警")
    else:
        print("\n✅ 无预警")
    print("="*50)

if __name__ == "__main__":
    run_analysis()

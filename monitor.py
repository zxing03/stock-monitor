import akshare as ak
import pandas as pd
import pandas_ta as ta
import requests
import time
import warnings
import os
from datetime import datetime, timedelta
from functools import wraps

# 屏蔽不必要的警告
warnings.filterwarnings("ignore")

# --- 1. 核心配置 ---
SC_KEY = os.environ.get("SC_KEY", "")  # 修复原有SC_KEY获取方式
RSI_UPPER = 80
RSI_LOWER = 20
RETRY_TIMES = 2  # 接口重试次数（安全气囊1）
REQUEST_INTERVAL = 0.5  # 接口请求间隔（安全气囊3）
ALERT_COOLDOWN = 30  # 同标的告警冷却时间（分钟，安全气囊3）

# 监控清单：基于你的表格提取（已排除货币和债券基金）
# 格式: [名称, 场内代码, 场外代码]
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

# 告警冷却缓存（安全气囊3：防止短时间重复告警）
alert_cache = {}

# --- 安全气囊1：接口重试装饰器 ---
def retry_decorator(max_retries=RETRY_TIMES, delay=1):
    """接口调用重试装饰器，失败时自动重试"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries >= max_retries:
                        print(f"⚠️ 接口调用失败（已重试{max_retries}次）：{func.__name__}, 错误: {str(e)}")
                        return None
                    time.sleep(delay)
            return None
        return wrapper
    return decorator

def send_wechat(title, content):
    """发送微信通知（增加异常捕获和空值校验）"""
    if not SC_KEY or SC_KEY.strip() == "":
        print("ℹ️ SC_KEY未配置，跳过微信推送")
        return
    url = f"https://sctapi.ftqq.com/{SC_KEY}.send"
    try:
        response = requests.post(url, data={"title": title, "desp": content}, timeout=10)
        response.raise_for_status()  # 触发HTTP错误
        print("✅ 微信通知发送成功")
    except Exception as e:
        print(f"❌ 微信通知发送失败：{str(e)}")

@retry_decorator(max_retries=RETRY_TIMES, delay=1)
def get_data(cn_code, of_code):
    """
    优先获取场内实时性更好的数据（集成安全气囊1：重试；安全气囊2：数据校验）
    """
    # 安全气囊2：参数前置校验
    if not cn_code and not of_code:
        print("ℹ️ 场内/场外代码均为空，跳过数据获取")
        return None
    
    try:
        if cn_code and cn_code != "-":
            # 抓取场内ETF/LOF日线数据
            symbol = f"sh{cn_code}" if cn_code.startswith(('5', '6')) else f"sz{cn_code}"
            df = ak.stock_zh_index_daily_em(symbol=symbol).tail(100)
            df = df.rename(columns={'close': 'close', 'date': 'date'})
        else:
            # 抓取场外基金净值数据
            df = ak.fund_open_fund_info_em(symbol=of_code, indicator="单位净值走势")
            df = df[['净值日期', '单位净值']].rename(columns={'净值日期': 'date', '单位净值': 'close'}).tail(100)

        # 安全气囊2：数据有效性强校验
        if df.empty:
            print(f"ℹ️ 数据为空，cn_code={cn_code}, of_code={of_code}")
            return None
        # 校验核心字段是否存在
        if not all(col in df.columns for col in ['date', 'close']):
            print(f"ℹ️ 核心字段缺失，cn_code={cn_code}, of_code={of_code}")
            return None
        # 转换数值并校验合理性
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df = df.dropna(subset=['close'])  # 剔除空值
        # 校验价格是否为合理正数
        if (df['close'] <= 0).any():
            print(f"ℹ️ 价格异常（非正数），cn_code={cn_code}, of_code={of_code}")
            return None

        return df
    except Exception as e:
        # 主动抛出异常，让重试装饰器处理
        raise e

def check_alert_cooldown(name):
    """
    安全气囊3：检查同标的告警冷却时间，避免短时间重复推送
    """
    now = datetime.now()
    if name in alert_cache:
        last_alert_time = alert_cache[name]
        if (now - last_alert_time) < timedelta(minutes=ALERT_COOLDOWN):
            return True  # 仍在冷却期，不触发告警
    # 更新缓存时间
    alert_cache[name] = now
    return False

def run_analysis():
    """核心分析逻辑（集成所有安全气囊）"""
    print(f"\n正在进行盘中扫描: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    all_alerts = []

    for idx, (name, cn_code, of_code) in enumerate(MONITOR_LIST):
        # 安全气囊3：接口请求间隔，避免高频调用被风控
        if idx > 0:
            time.sleep(REQUEST_INTERVAL)
        
        print(f"🔍 分析标的：{name} (场内:{cn_code}, 场外:{of_code})")
        df = get_data(cn_code, of_code)
        
        # 安全气囊2：数据空值最终校验
        if df is None or df.empty:
            print(f"ℹ️ {name} 数据获取失败/为空，跳过分析")
            continue

        # 计算指标
        try:
            df.ta.rsi(length=6, append=True)
            df.ta.bbands(length=20, std=2, append=True)
        except Exception as e:
            print(f"ℹ️ {name} 指标计算失败：{str(e)}")
            continue

        # 安全气囊2：指标有效性校验
        rsi_cols = [col for col in df.columns if 'RSI' in col]
        bbl_cols = [col for col in df.columns if 'BBL' in col]
        bbu_cols = [col for col in df.columns if 'BBU' in col]
        if not (rsi_cols and bbl_cols and bbu_cols):
            print(f"ℹ️ {name} 指标列缺失，跳过分析")
            continue

        latest = df.iloc[-1]
        price = latest['close']
        rsi_val = latest[rsi_cols[0]]
        bbl = latest[bbl_cols[0]]
        bbu = latest[bbu_cols[0]]

        # 安全气囊2：指标数值合理性校验
        if not (isinstance(rsi_val, (int, float)) and 0 <= rsi_val <= 100):
            print(f"ℹ️ {name} RSI值异常：{rsi_val}")
            continue
        if not (isinstance(bbl, (int, float)) and isinstance(bbu, (int, float)) and bbl < bbu):
            print(f"ℹ️ {name} BOLL带值异常：下轨={bbl}, 上轨={bbu}")
            continue

        # 触发判断
        res = []
        if price <= bbl: res.append(f"触及BOLL下轨({price:.3f})")
        if price >= bbu: res.append(f"触及BOLL上轨({price:.3f})")
        if rsi_val <= RSI_LOWER: res.append(f"RSI超跌({rsi_val:.2f})")
        if rsi_val >= RSI_UPPER: res.append(f"RSI超买({rsi_val:.2f})")

        if res:
            # 安全气囊3：检查冷却时间
            if check_alert_cooldown(name):
                print(f"ℹ️ {name} 触发告警但仍在冷却期，跳过推送")
                continue
            all_alerts.append(f"**{name}**: " + " / ".join(res))

    if all_alerts:
        content = "### 🔔 交易参考预警\n\n" + "\n\n".join(all_alerts) + \
                  f"\n\n---\n**分析时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        send_wechat("⚠️ 基金监控提醒", content)
        print("\n🚩 发现符合条件的标的，已发送微信预警")
        print("="*50)
    else:
        print("\n✅ 当前所有标的指标均在正常范围内，无预警")
        print("="*50)

if __name__ == "__main__":
    # 循环运行（可选，注释掉则单次运行）
    while True:
        run_analysis()
        # 每15分钟扫描一次（可根据需求调整）
        time.sleep(15 * 60)

import akshare as ak
import pandas as pd
import pandas_ta as ta
import requests
import time
import warnings
from datetime import datetime

# 屏蔽不必要的警告
warnings.filterwarnings("ignore")

# --- 1. 核心配置 ---
SC_KEY = "os.environ.get("SC_KEY")"
RSI_UPPER = 80
RSI_LOWER = 20

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


def send_wechat(title, content):
    if not SC_KEY or "替换" in SC_KEY: return
    url = f"https://sctapi.ftqq.com/{SC_KEY}.send"
    try:
        requests.post(url, data={"title": title, "desp": content}, timeout=10)
    except:
        pass


def get_data(cn_code, of_code):
    """优先获取场内实时性更好的数据"""
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

        df['close'] = pd.to_numeric(df['close'])
        return df
    except:
        return None


def run_analysis():
    print(f"正在进行盘中扫描: {datetime.now().strftime('%H:%M:%S')}")
    all_alerts = []

    for name, cn_code, of_code in MONITOR_LIST:
        df = get_data(cn_code, of_code)
        
        # --- 关键修复开始：加上这判断 ---
        if df is None or len(df) < 20: 
            print(f"⚠ {name} 数据获取不足，跳过")
            continue
        # --- 关键修复结束 ---

        # 计算指标
        df.ta.rsi(length=6, append=True)
        df.ta.bbands(length=20, std=2, append=True)

        latest = df.iloc[-1]
        price = latest['close']

        # 自动识别生成的指标列名
        rsi_val = latest.filter(like='RSI').iloc[0]
        bbl = latest.filter(like='BBL').iloc[0]
        bbu = latest.filter(like='BBU').iloc[0]

        # 触发判断
        res = []
        if price <= bbl: res.append(f"触及BOLL下轨({price:.3f})")
        if price >= bbu: res.append(f"触及BOLL上轨({price:.3f})")
        if rsi_val <= RSI_LOWER: res.append(f"RSI超跌({rsi_val:.2f})")
        if rsi_val >= RSI_UPPER: res.append(f"RSI超买({rsi_val:.2f})")

        if res:
            all_alerts.append(f"**{name}**: " + " / ".join(res))

    if all_alerts:
        content = "### 🔔 交易参考预警\n\n" + "\n\n".join(all_alerts) + \
                  f"\n\n---\n**分析时间**：{datetime.now().strftime('%H:%M')}"
        send_wechat("⚠️ 基金监控提醒", content)
        print("🚩 发现符合条件的标的，已发送微信。")
    else:
        print("✅ 当前指标均在正常范围内。")


if __name__ == "__main__":
    run_analysis()

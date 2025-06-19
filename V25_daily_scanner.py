# V25_daily_scanner.py
# 版本: 2.0 (自動化版)
# 功能: 每日盤後自動掃描、產生交易決策，並直接更新 index.html 檔案。

import os
import json
import pandas as pd
import talib
import requests
from datetime import datetime, timedelta
import logging
import re

# --- 全域設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- FIX: 從環境變數讀取 API Token，以符合 GitHub Actions 的安全規範 ---
API_TOKEN = os.getenv('API_TOKEN')

# --- 策略參數 ---
CONSOLIDATION_PERIOD = 50
VOLUME_SPIKE_MULT = 1.5
RSI_MIN_LEVEL = 50
RSI_MAX_LEVEL = 70
PROFIT_TARGET_RR = 1.5
RISK_PER_TRADE_PCT = 0.015
MAX_OPEN_POSITIONS = 6
MIN_TRADE_SHARES = 1000
MARKET_INDEX_ID = "TAIEX"

# --- 檔案路徑 ---
STATE_FILE = 'portfolio_state.json'
STOCK_LIST_FILE = 'stock_list.txt'
HTML_FILE = 'index.html' # 我們要更新的目標檔案

# --- 核心函式 (與前版相同) ---
def get_stock_data_from_finmind(stock_id: str, days_to_fetch: int = 300) -> pd.DataFrame:
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_to_fetch)
        url = (f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice"
               f"&data_id={stock_id}&start_date={start_date.strftime('%Y-%m-%d')}"
               f"&end_date={end_date.strftime('%Y-%m-%d')}&token={API_TOKEN}")
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data['msg'] != 'success':
            logging.warning(f"FinMind API for {stock_id}: {data['msg']}")
            return pd.DataFrame()
        df = pd.DataFrame(data['data'])
        if df.empty: return df
        df['date'] = pd.to_datetime(df['date'])
        return df.set_index('date')
    except Exception as e:
        logging.error(f"Failed to get {stock_id} data from FinMind: {e}")
        return pd.DataFrame()

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df) < 201: return pd.DataFrame()
    df['SMA_50'] = talib.SMA(df['close'], timeperiod=50)
    df['SMA_200'] = talib.SMA(df['close'], timeperiod=200)
    df['RSI_14'] = talib.RSI(df['close'], timeperiod=14)
    df['VOL_SMA_50'] = talib.SMA(df['Trading_Volume'], timeperiod=50)
    df['Consolidation_High'] = df['max'].rolling(window=CONSOLIDATION_PERIOD).max()
    df['Consolidation_Low'] = df['min'].rolling(window=CONSOLIDATION_PERIOD).min()
    return df.dropna()

def load_portfolio_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"cash": 5_000_000, "holdings": {}}
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to read state file: {e}, using initial state.")
        return {"cash": 5_000_000, "holdings": {}}

def save_portfolio_state(state: dict):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Failed to save state file: {e}")

# --- 決策產生函式 (與前版相同，但加入最新價格計算) ---
def find_buy_signals(stock_pool: list, market_data: pd.DataFrame, all_stock_data: dict) -> list:
    buy_signals = []
    if market_data.empty or market_data.iloc[-1]['close'] < market_data.iloc[-1]['SMA_200']:
        logging.info("Bear market, no buy signals today.")
        return []
    for stock_id in stock_pool:
        df = all_stock_data.get(stock_id)
        if df is None or len(df) < 2: continue
        latest, previous = df.iloc[-1], df.iloc[-2]
        is_breaking_out = previous['close'] < previous['Consolidation_High'] and latest['close'] > previous['Consolidation_High']
        is_rsi_ok = RSI_MIN_LEVEL < latest['RSI_14'] < RSI_MAX_LEVEL
        is_volume_ok = latest['Trading_Volume'] > (latest['VOL_SMA_50'] * VOLUME_SPIKE_MULT)
        if is_breaking_out and is_rsi_ok and is_volume_ok:
            buy_signals.append({"ticker": stock_id, "name": "", "stopLoss": latest['Consolidation_Low'], "signalPrice": latest['close']})
    return buy_signals

def generate_exit_signals_and_update_holdings(portfolio_state: dict, all_stock_data: dict):
    sell_signals = []
    holdings = portfolio_state['holdings']
    total_holdings_value = 0
    total_pnl = 0

    for stock_id, pos_info in list(holdings.items()):
        df = all_stock_data.get(stock_id)
        if df is None or df.empty:
            pos_info['currentPrice'] = pos_info['entryPrice'] # 數據獲取失敗則使用進場價
            pos_info['pnl'] = 0
            total_holdings_value += pos_info['currentPrice'] * pos_info['shares']
            continue
        
        latest = df.iloc[-1]
        pos_info['currentPrice'] = latest['close']
        pos_info['pnl'] = (latest['close'] - pos_info['entryPrice']) * pos_info['shares']
        total_holdings_value += pos_info['currentPrice'] * pos_info['shares']
        total_pnl += pos_info['pnl']
        
        exit_reason = None
        if latest['min'] <= pos_info['stop_loss_price']:
            exit_reason = "觸及初始停損" if not pos_info['breakeven_stop_set'] else "觸及盈虧平衡停損"
        elif not pos_info['breakeven_stop_set'] and latest['max'] >= (pos_info['entryPrice'] + (pos_info['entryPrice'] - pos_info['stop_loss_price']) * PROFIT_TARGET_RR):
             pos_info['breakeven_stop_set'] = True
             pos_info['stop_loss_price'] = pos_info['entryPrice']
             logging.info(f"持股 {stock_id} 風控升級，停損點移至 {pos_info['entryPrice']}.")
        elif pos_info['breakeven_stop_set'] and latest['close'] < latest['SMA_50']:
            exit_reason = "觸及追蹤停利 (50MA)"
        
        if exit_reason:
            sell_signals.append({"ticker": stock_id, "name": pos_info.get("name", ""), "reason": exit_reason})
    
    portfolio_state['overview'] = {
        "totalEquity": portfolio_state['cash'] + total_holdings_value,
        "cash": portfolio_state['cash'],
        "holdingsValue": total_holdings_value,
        "netPL": total_pnl
    }
    return sell_signals

# --- FIX: 新增函式，自動更新 HTML 檔案 ---
def update_html_file(trading_plan: dict):
    """讀取 index.html，並將最新的交易計畫數據注入其中"""
    try:
        with open(HTML_FILE, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # 使用正則表達式找到 tradingPlanData 變數並替換其內容
        # 這比簡單的字串替換更穩健
        json_string = json.dumps(trading_plan, indent=4, ensure_ascii=False)
        
        # re.DOTALL 讓 '.' 可以匹配換行符
        pattern = re.compile(r"(const tradingPlanData = )(\{.*?\});", re.DOTALL)
        
        if not pattern.search(html_content):
            logging.error(f"在 {HTML_FILE} 中找不到 'const tradingPlanData = {{...}};' 的模式。")
            return

        new_html_content = pattern.sub(f"\\1{json_string};", html_content, count=1)

        with open(HTML_FILE, 'w', encoding='utf-8') as f:
            f.write(new_html_content)
        
        logging.info(f"已成功將最新交易計畫更新至 {HTML_FILE}")

    except FileNotFoundError:
        logging.error(f"找不到 HTML 檔案: {HTML_FILE}")
    except Exception as e:
        logging.error(f"更新 HTML 檔案失敗: {e}")


def main():
    logging.info("--- 開始執行 V25 自動化掃描任務 ---")
    if not API_TOKEN:
        logging.error("錯誤：找不到 API_TOKEN 環境變數。請在 GitHub Secrets 中設定。")
        return

    try:
        with open(STOCK_LIST_FILE, 'r') as f:
            stock_pool = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logging.error(f"找不到股票列表檔案: {STOCK_LIST_FILE}，任務中止。")
        return
        
    portfolio_state = load_portfolio_state()
    
    all_stock_data = {}
    logging.info("正在獲取市場數據...")
    market_df_raw = get_stock_data_from_finmind(MARKET_INDEX_ID)
    market_df = calculate_indicators(market_df_raw)
    all_stock_data[MARKET_INDEX_ID] = market_df

    stocks_to_fetch = set(stock_pool + list(portfolio_state['holdings'].keys()))
    for stock_id in stocks_to_fetch:
        df_raw = get_stock_data_from_finmind(stock_id)
        all_stock_data[stock_id] = calculate_indicators(df_raw)

    sell_signals = generate_exit_signals_and_update_holdings(portfolio_state, all_stock_data)
    buy_signals_raw = find_buy_signals(stock_pool, market_df, all_stock_data)
    
    buy_signals = []
    available_slots = MAX_OPEN_POSITIONS - len(portfolio_state['holdings'])
    for signal in buy_signals_raw:
        if len(buy_signals) >= available_slots: break
        risk_per_share = signal['signalPrice'] - signal['stopLoss']
        if risk_per_share <= 0: continue
        dollar_to_risk = portfolio_state['overview']['totalEquity'] * RISK_PER_TRADE_PCT
        shares_to_buy = int((dollar_to_risk / risk_per_share) / 1000) * 1000 # 無條件捨去到千位
        if shares_to_buy > 0:
            signal['sharesToBuy'] = shares_to_buy
            signal['estimatedCost'] = shares_to_buy * signal['signalPrice']
            buy_signals.append(signal)

    # 組合最終的交易計畫
    final_trading_plan = {
        "overview": portfolio_state['overview'],
        "holdings": list(portfolio_state['holdings'].values()),
        "buySignals": buy_signals,
        "sellSignals": sell_signals
    }
    
    # 更新 HTML 檔案
    update_html_file(final_trading_plan)

    logging.info("--- V25 自動化掃描任務執行完畢 ---")

if __name__ == '__main__':
    main()

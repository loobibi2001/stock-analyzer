# V25_daily_scanner.py
# 版本: 1.0
# 功能: 每日盤後自動掃描、產生交易決策，並輸出為 JSON 檔案供前端儀表板使用。

import os
import json
import pandas as pd
import talib
import requests
from datetime import datetime, timedelta
import logging

# --- 全域設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# !!! 請在此處貼上您的 FinMind API Token !!!
API_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNS0wNi0xOSAxNDozMjozOSIsInVzZXJfaWQiOiJsb29iaWJpMjAwMSIsImlwIjoiMS4xNzIuMTQ4LjEwMiJ9.MBBb_KT2UpijKBdTMRIEtK5oajzyA9Wtbe7PK9Q17qU"

# --- 策略參數 (與回測腳本保持一致) ---
CONSOLIDATION_PERIOD = 50
VOLUME_SPIKE_MULT = 1.5
RSI_MIN_LEVEL = 50
RSI_MAX_LEVEL = 70
PROFIT_TARGET_RR = 1.5
RISK_PER_TRADE_PCT = 0.015
MAX_OPEN_POSITIONS = 6
MIN_TRADE_SHARES = 1000 # 假設單位為股
MARKET_INDEX_ID = "TAIEX"

# --- 檔案路徑 ---
# 這兩個檔案會儲存在執行腳本的同一個資料夾下
STATE_FILE = 'portfolio_state.json'
OUTPUT_FILE = 'trading_plan.json'
STOCK_LIST_FILE = 'stock_list.txt' # 您的股票池列表

# --- 核心函式 ---

def get_stock_data_from_finmind(stock_id: str, days_to_fetch: int = 300) -> pd.DataFrame:
    """從 FinMind API 獲取指定股票的歷史日K數據"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_to_fetch)
        
        url = (f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice"
               f"&data_id={stock_id}&start_date={start_date.strftime('%Y-%m-%d')}"
               f"&end_date={end_date.strftime('%Y-%m-%d')}&token={API_TOKEN}")
        
        response = requests.get(url)
        response.raise_for_status() # 如果請求失敗，會拋出異常
        data = response.json()

        if data['msg'] != 'success':
            logging.warning(f"FinMind API 對 {stock_id} 回應錯誤: {data['msg']}")
            return pd.DataFrame()

        df = pd.DataFrame(data['data'])
        if df.empty:
            return df
            
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        # FinMind 來的欄位是小寫，符合我們的需求
        return df
    except Exception as e:
        logging.error(f"從 FinMind 獲取 {stock_id} 數據失敗: {e}")
        return pd.DataFrame()

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """計算 V25 策略所需的全部技術指標"""
    if df.empty or len(df) < 201:
        return pd.DataFrame()
        
    df['SMA_50'] = talib.SMA(df['close'], timeperiod=50)
    df['SMA_200'] = talib.SMA(df['close'], timeperiod=200)
    df['RSI_14'] = talib.RSI(df['close'], timeperiod=14)
    df['VOL_SMA_50'] = talib.SMA(df['Trading_Volume'], timeperiod=50) # 注意: FinMind 的成交量欄位名
    df['Consolidation_High'] = df['max'].rolling(window=CONSOLIDATION_PERIOD).max() # FinMind: max
    df['Consolidation_Low'] = df['min'].rolling(window=CONSOLIDATION_PERIOD).min()   # FinMind: min
    
    # 刪除有NaN值的行，確保所有指標都已計算
    return df.dropna()

def load_portfolio_state() -> dict:
    """從檔案載入目前的投資組合狀態，如果檔案不存在則創建一個初始狀態"""
    if not os.path.exists(STATE_FILE):
        logging.info("找不到投資組合狀態檔案，創建新的初始狀態。")
        return {
            "cash": 5_000_000,
            "holdings": {} # key: stock_id, value: position_info
        }
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"讀取狀態檔案失敗: {e}，將使用初始狀態。")
        return { "cash": 5_000_000, "holdings": {} }

def save_portfolio_state(state: dict):
    """將最新的投資組合狀態儲存到檔案"""
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"儲存狀態檔案失敗: {e}")


def find_buy_signals(stock_pool: list, market_data: pd.DataFrame, all_stock_data: dict) -> list:
    """掃描股票池，找出所有符合條件的進場訊號"""
    buy_signals = []
    
    # 確認大盤為多頭
    if market_data.empty or market_data.iloc[-1]['close'] < market_data.iloc[-1]['SMA_200']:
        logging.info("大盤非多頭市場，今日不產生任何進場訊號。")
        return []

    logging.info(f"大盤為多頭市場，開始掃描 {len(stock_pool)} 支股票...")

    for stock_id in stock_pool:
        df = all_stock_data.get(stock_id)
        if df is None or len(df) < 2:
            continue
        
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        
        # 1. 結構: 突破盤整區高點
        is_breaking_out = previous['close'] < previous['Consolidation_High'] and \
                          latest['close'] > previous['Consolidation_High']
        
        # 2. 動能: RSI符合區間
        is_rsi_ok = RSI_MIN_LEVEL < latest['RSI_14'] < RSI_MAX_LEVEL
        
        # 3. 成交量: 顯著放大
        is_volume_ok = latest['Trading_Volume'] > (latest['VOL_SMA_50'] * VOLUME_SPIKE_MULT)

        if is_breaking_out and is_rsi_ok and is_volume_ok:
            signal = {
                "ticker": stock_id,
                "name": "", # 名稱可以後續填充或由前端處理
                "stopLoss": latest['Consolidation_Low'],
                "signalPrice": latest['close'] # 用於資訊顯示
            }
            buy_signals.append(signal)
            logging.info(f"發現進場訊號: {stock_id}")

    return buy_signals

def generate_exit_signals(current_holdings: dict, all_stock_data: dict) -> list:
    """檢查目前持股，找出所有符合條件的出場訊號"""
    sell_signals = []
    
    for stock_id, pos_info in current_holdings.items():
        df = all_stock_data.get(stock_id)
        if df is None or df.empty:
            continue
            
        latest = df.iloc[-1]
        exit_reason = None
        
        # 檢查是否觸發停損 (初始停損或盈虧平衡停損)
        if latest['min'] <= pos_info['stop_loss_price']:
            exit_reason = "觸及初始停損" if not pos_info['breakeven_stop_set'] else "觸及盈虧平衡停損"

        # 檢查是否觸發追蹤停利 (僅在已達盈虧平衡後)
        if not exit_reason and pos_info['breakeven_stop_set']:
            if latest['close'] < latest['SMA_50']:
                exit_reason = "觸及追蹤停利 (50MA)"
        
        if exit_reason:
            signal = {
                "ticker": stock_id,
                "name": pos_info.get("name", ""),
                "reason": exit_reason
            }
            sell_signals.append(signal)
            logging.info(f"產生出場訊號: {stock_id}, 原因: {exit_reason}")
    
    return sell_signals


def main():
    """主執行程序"""
    logging.info("--- 開始執行 V25 每日掃描任務 ---")

    # 1. 載入股票池與目前投資組合狀態
    try:
        with open(STOCK_LIST_FILE, 'r') as f:
            stock_pool = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logging.error(f"找不到股票列表檔案: {STOCK_LIST_FILE}，任務中止。")
        return
        
    portfolio_state = load_portfolio_state()
    
    # 2. 獲取所有需要的市場數據
    all_stock_data = {}
    logging.info("正在獲取市場數據...")
    # 首先獲取大盤指數
    market_df_raw = get_stock_data_from_finmind(MARKET_INDEX_ID)
    market_df = calculate_indicators(market_df_raw)
    all_stock_data[MARKET_INDEX_ID] = market_df

    # 獲取股票池中所有股票 + 當前持股的數據
    stocks_to_fetch = set(stock_pool + list(portfolio_state['holdings'].keys()))
    for stock_id in stocks_to_fetch:
        df_raw = get_stock_data_from_finmind(stock_id)
        all_stock_data[stock_id] = calculate_indicators(df_raw)

    # 3. 產生交易決策
    buy_signals_raw = find_buy_signals(stock_pool, market_df, all_stock_data)
    sell_signals = generate_exit_signals(portfolio_state['holdings'], all_stock_data)

    # 4. 計算倉位大小
    # (此處簡化，實際應根據 portfolio_state['cash'] 和持股市值計算總權益)
    # 假設總權益為初始資金，僅用於計算範例
    total_equity = portfolio_state['cash'] # 簡化估算
    buy_signals = []
    available_slots = MAX_OPEN_POSITIONS - len(portfolio_state['holdings'])
    
    for signal in buy_signals_raw:
        if len(buy_signals) >= available_slots:
            break # 持倉已滿

        risk_per_share = signal['signalPrice'] - signal['stopLoss']
        if risk_per_share <= 0: continue
        
        dollar_to_risk = total_equity * RISK_PER_TRADE_PCT
        shares_to_buy = int((dollar_to_risk / risk_per_share) / MIN_TRADE_SHARES) * MIN_TRADE_SHARES
        
        if shares_to_buy > 0:
            signal['sharesToBuy'] = shares_to_buy
            signal['estimatedCost'] = shares_to_buy * signal['signalPrice']
            buy_signals.append(signal)

    # 5. 準備輸出給前端的 JSON 檔案
    # 注意：這裡我們只 "產生" 決策，但還沒 "更新" 狀態檔案。
    # 狀態檔案的更新應該在下一個交易日開盤成交後才進行。
    # 但為了讓儀表板能顯示，我們先準備好輸出。
    output_data = {
        "overview": {
            "totalEquity": portfolio_state['cash'], # 簡化顯示，實際應加上持股市值
             # 其他總覽數據可以從歷史回測或每日狀態計算而來
        },
        "holdings": list(portfolio_state['holdings'].values()), # 將 dict 轉為 list
        "buySignals": buy_signals,
        "sellSignals": sell_signals
    }
    
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=4, ensure_ascii=False)
        logging.info(f"交易計畫已成功寫入至 {OUTPUT_FILE}")
    except Exception as e:
        logging.error(f"寫入交易計畫檔案失敗: {e}")

    logging.info("--- V25 每日掃描任務執行完畢 ---")


if __name__ == '__main__':
    # 為了能直接執行，我們創建一個假的股票列表檔案
    if not os.path.exists(STOCK_LIST_FILE):
        with open(STOCK_LIST_FILE, 'w') as f:
            f.write("2330\n")
            f.write("2454\n")
            f.write("2603\n")
            f.write("3008\n")
            f.write("6505\n")
            
    # 同時，創建一個假的 portfolio_state.json 讓腳本可以讀取
    if not os.path.exists(STATE_FILE):
        initial_state = {
            "cash": 3000000,
            "holdings": {
                "2603": {
                    "ticker": "2603",
                    "name": "長榮",
                    "shares": 10000,
                    "entryPrice": 160.2,
                    "stop_loss_price": 160.2,
                    "breakeven_stop_set": True,
                    "status": "風控升級"
                }
            }
        }
        save_portfolio_state(initial_state)

    main()

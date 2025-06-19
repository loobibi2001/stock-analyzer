# V25_scanner_with_metrics.py
# 版本: 3.0 (歷史績效分析版)
# 功能: 每日掃描，維護交易歷史，計算詳細績效指標，並直接更新 index.html。

import os
import json
import pandas as pd
import talib
import requests
from datetime import datetime, timedelta
import logging
import re
import numpy as np

# --- 全域設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
API_TOKEN = os.getenv('API_TOKEN')
ANNUAL_TRADING_DAYS = 252

# --- 策略參數 ---
CONSOLIDATION_PERIOD = 50
VOLUME_SPIKE_MULT = 1.5
RSI_MIN_LEVEL = 50
RSI_MAX_LEVEL = 70
PROFIT_TARGET_RR = 1.5
RISK_PER_TRADE_PCT = 0.015
MAX_OPEN_POSITIONS = 6
MARKET_INDEX_ID = "TAIEX"

# --- 檔案路徑 ---
STATE_FILE = 'portfolio_state.json'
STOCK_LIST_FILE = 'stock_list.txt'
HTML_FILE = 'index.html'

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
        df.rename(columns={'Trading_Volume': 'volume', 'max': 'high', 'min': 'low'}, inplace=True)
        return df.set_index('date')
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
    df['VOL_SMA_50'] = talib.SMA(df['volume'], timeperiod=50)
    df['Consolidation_High'] = df['high'].rolling(window=CONSOLIDATION_PERIOD).max()
    df['Consolidation_Low'] = df['low'].rolling(window=CONSOLIDATION_PERIOD).min()
    
    # 刪除有NaN值的行，確保所有指標都已計算
    return df.dropna()

def load_portfolio_state() -> dict:
    """從檔案載入目前的投資組合狀態，如果檔案不存在則創建一個初始狀態"""
    if not os.path.exists(STATE_FILE):
        logging.info("找不到投資組合狀態檔案，創建新的初始狀態。")
        return {
            "initial_capital": 5_000_000, 
            "cash": 5_000_000, 
            "start_date": datetime.now().strftime('%Y-%m-%d'), 
            "holdings": {}, 
            "trade_history": [], 
            "equity_curve": {datetime.now().strftime('%Y-%m-%d'): 5_000_000}
        }
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"讀取狀態檔案失敗: {e}，將使用初始狀態。")
        return {"initial_capital": 5_000_000, "cash": 5_000_000, "start_date": datetime.now().strftime('%Y-%m-%d'), "holdings": {}, "trade_history": [], "equity_curve": {}}

def save_portfolio_state(state: dict):
    """將最新的投資組合狀態儲存到檔案"""
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"儲存狀態檔案失敗: {e}")

def update_html_file(trading_plan: dict):
    """讀取 index.html，並將最新的交易計畫數據注入其中"""
    try:
        with open(HTML_FILE, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # 將 Python dict 轉換為格式化的 JSON 字串
        json_string = json.dumps(trading_plan, indent=8, ensure_ascii=False)
        
        # 使用正則表達式找到 tradingPlanData 變數並替換其內容
        pattern = re.compile(r"(const tradingPlanData = )(\{.*?\});", re.DOTALL)
        
        if not pattern.search(html_content):
            logging.error(f"在 {HTML_FILE} 中找不到 'const tradingPlanData = {{...}};' 的模式。")
            return

        new_html_content = pattern.sub(f"\\1{json_string};", html_content, count=1)

        with open(HTML_FILE, 'w', encoding='utf-8') as f:
            f.write(new_html_content)
        
        logging.info(f"已成功將最新交易計畫更新至 {HTML_FILE}")

    except FileNotFoundError:
        logging.error(f"HTML file not found: {HTML_FILE}")
    except Exception as e:
        logging.error(f"Failed to update HTML file: {e}")

# --- FIX: 新增績效計算核心函式 ---
def calculate_performance_metrics(state: dict) -> dict:
    """根據完整的狀態歷史計算所有績效指標"""
    trade_history = state.get("trade_history", [])
    initial_capital = state.get("initial_capital", 5_000_000)
    start_date = state.get("start_date", datetime.now().strftime('%Y-%m-%d'))

    metrics = {
        "netProfitDollar": 0, "netProfitPercent": 0, "finalEquity": initial_capital,
        "cagrPercent": 0, "maxDrawdownPercent": 0, "sharpeRatio": 0,
        "totalTrades": 0, "winRatePercent": 0, "profitFactor": "N/A",
        "payoffRatio": "N/A", "grossProfitDollar": 0, "grossLossDollar": 0,
        "totalCostDollar": 0, "avgProfitPercent": None, "avgLossPercent": None,
        "maxProfitPercent": None, "maxLossPercent": None, "avgHoldingDays": None,
        "avgWinHoldingDays": None, "avgLossHoldingDays": None,
        "backtestDays": (datetime.now() - datetime.strptime(start_date, '%Y-%m-%d')).days
    }
    
    if not trade_history:
        return metrics

    trades_df = pd.DataFrame(trade_history)
    if 'entry_value' in trades_df.columns and trades_df['entry_value'].sum() > 0:
        trades_df['pnl_percent'] = (trades_df['pnl_net'] / trades_df['entry_value'].replace(0, np.nan)) * 100
    else:
        trades_df['pnl_percent'] = 0

    total_trades = len(trades_df)
    winning_trades = trades_df[trades_df['pnl_net'] > 0]
    losing_trades = trades_df[trades_df['pnl_net'] <= 0]

    gross_profit = winning_trades['pnl_gross'].sum()
    gross_loss = abs(losing_trades['pnl_gross'].sum())
    
    metrics.update({
        "totalTrades": total_trades,
        "winRatePercent": (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0,
        "profitFactor": gross_profit / gross_loss if gross_loss > 0 else float('inf'),
        "grossProfitDollar": gross_profit,
        "grossLossDollar": gross_loss,
        "totalCostDollar": trades_df['trade_cost'].sum(),
        "avgProfitPercent": winning_trades['pnl_percent'].mean(),
        "avgLossPercent": losing_trades['pnl_percent'].mean(),
        "maxProfitPercent": trades_df['pnl_percent'].max(),
        "maxLossPercent": trades_df['pnl_percent'].min(),
        "avgHoldingDays": trades_df['holding_days'].mean(),
        "avgWinHoldingDays": winning_trades['holding_days'].mean(),
        "avgLossHoldingDays": losing_trades['holding_days'].mean(),
    })
    metrics['payoffRatio'] = abs(metrics['avgProfitPercent'] / metrics['avgLossPercent']) if metrics['avgLossPercent'] != 0 and not np.isnan(metrics['avgLossPercent']) else float('inf')

    equity_series = pd.Series(state.get('equity_curve', {})).sort_index()
    if not equity_series.empty:
        equity_series.index = pd.to_datetime(equity_series.index)
        peak = equity_series.expanding(min_periods=1).max()
        drawdown = (equity_series - peak) / peak
        max_drawdown = abs(drawdown.min() * 100) if not drawdown.empty else 0
        final_equity = equity_series.iloc[-1]
        
        years = metrics['backtestDays'] / 365.25 if metrics['backtestDays'] > 0 else 0
        cagr = ((final_equity / initial_capital)**(1/years) - 1) * 100 if years > 0 and final_equity > 0 else 0
        daily_returns = equity_series.pct_change().dropna()
        sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(ANNUAL_TRADING_DAYS) if not daily_returns.empty and daily_returns.std() != 0 else 0
        
        metrics.update({
            "netProfitDollar": final_equity - initial_capital,
            "netProfitPercent": ((final_equity / initial_capital) - 1) * 100,
            "finalEquity": final_equity, "cagrPercent": cagr, 
            "maxDrawdownPercent": max_drawdown, "sharpeRatio": sharpe_ratio
        })
    return {k: (v if not pd.isna(v) else None) for k, v in metrics.items()}


def process_daily_signals(portfolio_state, all_stock_data, stock_pool):
    """處理每日的進出場訊號，並更新 portfolio_state"""
    holdings = portfolio_state['holdings']
    trade_history = portfolio_state.setdefault('trade_history', [])
    today_str = datetime.now().strftime('%Y-%m-%d')
    sell_signals = []

    # 處理出場
    for stock_id, pos_info in list(holdings.items()):
        df = all_stock_data.get(stock_id)
        if df is None or df.empty: continue
        
        latest = df.iloc[-1]
        exit_reason = None
        
        if latest['low'] <= pos_info['stop_loss_price']:
            exit_reason = "觸及停損"
        elif pos_info.get('breakeven_stop_set', False) and latest['close'] < latest['SMA_50']:
            exit_reason = "觸及追蹤停利 (50MA)"

        if exit_reason:
            sell_signals.append({"ticker": stock_id, "name": pos_info.get("name", ""), "reason": exit_reason})
            
            exit_price = latest['close'] # 簡化為收盤價
            entry_value = pos_info['entryPrice'] * pos_info['shares']
            exit_value = exit_price * pos_info['shares']
            pnl_gross = exit_value - entry_value
            trade_cost = entry_value * 0.001425 + exit_value * (0.001425 + 0.003)
            pnl_net = pnl_gross - trade_cost
            
            trade_history.append({
                "stock_id": stock_id, "entry_date": pos_info['entryDate'], "exit_date": today_str,
                "entry_price": pos_info['entryPrice'], "exit_price": exit_price, "shares": pos_info['shares'],
                "entry_value": entry_value, "pnl_gross": pnl_gross, "pnl_net": pnl_net,
                "trade_cost": trade_cost,
                "holding_days": (datetime.strptime(today_str, '%Y-%m-%d') - datetime.strptime(pos_info['entryDate'], '%Y-%m-%d')).days
            })
            portfolio_state['cash'] += exit_value - (exit_value * (0.001425 + 0.003))
            del holdings[stock_id]
            logging.info(f"平倉 {stock_id}，原因: {exit_reason}，淨利: {pnl_net:.2f}")

        elif not pos_info.get('breakeven_stop_set', False) and latest['high'] >= (pos_info['entryPrice'] + (pos_info['entryPrice'] - pos_info['stop_loss_price']) * PROFIT_TARGET_RR):
            pos_info['breakeven_stop_set'] = True
            pos_info['stop_loss_price'] = pos_info['entryPrice']
            pos_info['status'] = "風控升級"
            logging.info(f"持股 {stock_id} 風控升級.")

    # 處理進場
    market_df = all_stock_data.get(MARKET_INDEX_ID, pd.DataFrame())
    buy_signals_raw = []
    if not market_df.empty and market_df.iloc[-1]['close'] > market_df.iloc[-1]['SMA_200']:
        for stock_id in stock_pool:
            if stock_id in holdings: continue
            df = all_stock_data.get(stock_id)
            if df is None or len(df) < 2: continue
            latest, previous = df.iloc[-1], df.iloc[-2]
            if previous['close'] < previous['Consolidation_High'] and latest['close'] > latest['Consolidation_High'] and RSI_MIN_LEVEL < latest['RSI_14'] < RSI_MAX_LEVEL and latest['volume'] > (latest['VOL_SMA_50'] * VOLUME_SPIKE_MULT):
                buy_signals_raw.append({"ticker": stock_id, "name": "", "stopLoss": latest['Consolidation_Low'], "signalPrice": latest['close']})

    buy_signals = []
    current_holdings_value = sum(p.get('currentPrice', p['entryPrice']) * p['shares'] for p in holdings.values())
    total_equity = portfolio_state['cash'] + current_holdings_value
    available_slots = MAX_OPEN_POSITIONS - len(holdings)
    for signal in buy_signals_raw:
        if len(buy_signals) >= available_slots: break
        risk_per_share = signal['signalPrice'] - signal['stopLoss']
        if risk_per_share <= 0: continue
        dollar_to_risk = total_equity * RISK_PER_TRADE_PCT
        shares_to_buy = int((dollar_to_risk / risk_per_share) / 1000) * 1000
        if shares_to_buy > 0:
            cost = shares_to_buy * signal['signalPrice']
            if portfolio_state['cash'] > cost * (1 + 0.001425):
                portfolio_state['cash'] -= cost * (1 + 0.001425)
                holdings[signal['ticker']] = {
                    "ticker": signal['ticker'], "name": signal['name'], "shares": shares_to_buy,
                    "entryPrice": signal['signalPrice'], "entryDate": today_str,
                    "stop_loss_price": signal['stopLoss'], "breakeven_stop_set": False, "status": "初始停損"
                }
                signal['sharesToBuy'] = shares_to_buy
                signal['estimatedCost'] = cost
                buy_signals.append(signal)
                logging.info(f"建立新倉位 {signal['ticker']}，股數: {shares_to_buy}")

    return buy_signals, sell_signals

def main():
    if not API_TOKEN:
        logging.error("錯誤：找不到 API_TOKEN 環境變數。請在 GitHub Secrets 中設定。")
        return

    portfolio_state = load_portfolio_state()
    try:
        with open(STOCK_LIST_FILE, 'r') as f:
            stock_pool = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logging.error(f"找不到股票列表檔案: {STOCK_LIST_FILE}，任務中止。")
        return
        
    all_stock_data = {}
    stocks_to_fetch = set(stock_pool + list(portfolio_state['holdings'].keys()) + [MARKET_INDEX_ID])
    logging.info(f"正在獲取 {len(stocks_to_fetch)} 支標的的市場數據...")
    for stock_id in stocks_to_fetch:
        df_raw = get_stock_data_from_finmind(stock_id)
        all_stock_data[stock_id] = calculate_indicators(df_raw)

    buy_signals, sell_signals = process_daily_signals(portfolio_state, all_stock_data, stock_pool)

    total_holdings_value = 0
    for stock_id, pos_info in portfolio_state['holdings'].items():
        if stock_id in all_stock_data and not all_stock_data[stock_id].empty:
            latest_price = all_stock_data[stock_id].iloc[-1]['close']
            pos_info['currentPrice'] = latest_price
            pos_info['pnl'] = (latest_price - pos_info['entryPrice']) * pos_info['shares']
            total_holdings_value += latest_price * pos_info['shares']

    today_str = datetime.now().strftime('%Y-%m-%d')
    current_equity = portfolio_state['cash'] + total_holdings_value
    portfolio_state.setdefault('equity_curve', {})[today_str] = current_equity
    
    performance_metrics = calculate_performance_metrics(portfolio_state)

    final_trading_plan = {
        "overview": {
            "cash": portfolio_state['cash'],
            "holdingsValue": total_holdings_value,
            "netPL": sum(p.get('pnl', 0) for p in portfolio_state['holdings'].values())
        },
        "holdings": list(portfolio_state['holdings'].values()),
        "buySignals": buy_signals,
        "sellSignals": sell_signals,
        "performance_metrics": performance_metrics
    }
    
    update_html_file(final_trading_plan)
    save_portfolio_state(portfolio_state)

    logging.info("--- V25 自動化掃描任務執行完畢 ---")

if __name__ == '__main__':
    main()

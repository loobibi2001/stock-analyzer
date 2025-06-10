import os
import pandas as pd
import pandas_ta as ta # <--- 改用 pandas-ta
from datetime import datetime, timedelta
import numpy as np
import time
import functools
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import json

# --- 設定 Matplotlib 後端為 Agg (如果需要繪圖) ---
import matplotlib
matplotlib.use('Agg')
# ---

logger = logging.getLogger(__name__)

# --- 常量定義 ---
MIN_REQUIRED_DAILY_DATA_BASELINE = 350

# --- 持股與路徑管理 ---
PORTFOLIO_FILE = "portfolio_berserker.json"

@dataclass
class Paths:
    base: str
    data_dir_name: str = "StockData_Parquet"
    list_file_name: str = "stock_list.txt"
    log_dir_name: str = "logs"
    portfolio_path: str = PORTFOLIO_FILE

    def __post_init__(self):
        self.data_dir: str = os.path.join(self.base, self.data_dir_name)
        self.list_path: str = os.path.join(self.base, self.list_file_name)
        script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() and os.path.exists(__file__) else os.getcwd()
        self.log_dir: str = os.path.join(script_dir, self.log_dir_name)
        self.portfolio_path = os.path.join(self.base, self.portfolio_path)

# --- 策略參數dataclasses (與回測腳本相同) ---
@dataclass
class IndParams:
    macd_f_d: int; macd_s_d: int; macd_sig_d: int
    adx_p_d: int; rsi_p_d: int; atr_p_d: int
    adx_p_w_exit: int; macd_f_w: int; macd_s_w: int
    macd_sig_w: int; vol_sma_p: int
@dataclass
class StratCfg:
    adx_entry_th: float; rsi_entry_th: float; rsi_exit_th: float
    use_macd_hist_exit: bool = False; use_macd_dx_exit: bool = False
@dataclass
class StopCfg:
    atr_mult: float; hard_sl_pct: float
    trail_act_pct: float; trail_ret_pct: float
@dataclass
class FilterCfg:
    use_w_macd: bool; use_vol: bool

# --- 持股資料結構 ---
@dataclass
class Position:
    stock_id: str; entry_date: str; entry_price: float
    initial_stop_loss_price: float; highest_price_since_entry: float
    trailing_stop_active: bool = False; current_trailing_stop_price: float = 0.0

# --- 核心邏輯函數 ---
def prep_data(stock_id: str, df_raw: pd.DataFrame, min_required_len: int) -> Optional[pd.DataFrame]:
    if df_raw.empty or len(df_raw) < min_required_len: return None
    df = df_raw.copy(); df.columns = [col.lower() for col in df.columns]
    if 'trading_volume' in df.columns and 'volume' not in df.columns: df.rename(columns={'trading_volume': 'volume'}, inplace=True)
    if 'date' not in df.columns:
        if df.index.name == 'date' and isinstance(df.index, pd.DatetimeIndex): df.reset_index(inplace=True)
        else: return None
    df.drop_duplicates(subset=['date'], keep='first', inplace=True)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df.dropna(subset=['date'], inplace=True)
    if df.empty: return None
    df = df.sort_values(by='date').set_index('date')
    required = ['high', 'low', 'close', 'open', 'volume']
    if not all(col in df.columns for col in required) or df[required].isnull().values.any(): return None
    return df

# ================= 全新的 calc_inds 函數 (使用 pandas-ta) =================
def calc_inds(df_in: pd.DataFrame, inds_cfg: IndParams, filter_cfg: FilterCfg) -> pd.DataFrame:
    if df_in.empty:
        return df_in
        
    df = df_in.copy()
    
    # --- 日線指標 ---
    # 使用 pandas-ta 計算指標，它會自動將結果附加到 df 上
    if all(p > 0 for p in [inds_cfg.macd_f_d, inds_cfg.macd_s_d, inds_cfg.macd_sig_d]):
        df.ta.macd(fast=inds_cfg.macd_f_d, slow=inds_cfg.macd_s_d, signal=inds_cfg.macd_sig_d, append=True)
        # 更名以匹配舊腳本的欄位名稱
        df.rename(columns={f'MACDh_{inds_cfg.macd_f_d}_{inds_cfg.macd_s_d}_{inds_cfg.macd_sig_d}': 'macd_hist_d'}, inplace=True)
        if 'macd_hist_d' in df.columns:
             df['macd_hist_d_prev'] = df['macd_hist_d'].shift(1)

    if inds_cfg.adx_p_d > 0:
        df.ta.adx(length=inds_cfg.adx_p_d, append=True)
        df.rename(columns={f'ADX_{inds_cfg.adx_p_d}': 'adx_d'}, inplace=True)
        if 'adx_d' in df.columns:
            df['adx_d_prev'] = df['adx_d'].shift(1)

    if inds_cfg.rsi_p_d > 0:
        df.ta.rsi(length=inds_cfg.rsi_p_d, append=True)
        df.rename(columns={f'RSI_{inds_cfg.rsi_p_d}': 'rsi_d'}, inplace=True)

    if inds_cfg.atr_p_d > 0:
        df.ta.atr(length=inds_cfg.atr_p_d, append=True)
        df.rename(columns={f'ATRr_{inds_cfg.atr_p_d}': 'atr_d'}, inplace=True)
        
    if filter_cfg.use_vol and inds_cfg.vol_sma_p > 0:
        df.ta.sma(close=df['volume'], length=inds_cfg.vol_sma_p, append=True)
        df.rename(columns={f'SMA_{inds_cfg.vol_sma_p}': 'vol_sma'}, inplace=True)

    # --- 週線指標 ---
    df_w = df.resample('W-FRI').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    if not df_w.empty and filter_cfg.use_w_macd and all(p > 0 for p in [inds_cfg.macd_f_w, inds_cfg.macd_s_w, inds_cfg.macd_sig_w]):
        df_w.ta.macd(fast=inds_cfg.macd_f_w, slow=inds_cfg.macd_s_w, signal=inds_cfg.macd_sig_w, append=True)
        df_w.rename(columns={f'MACDh_{inds_cfg.macd_f_w}_{inds_cfg.macd_s_w}_{inds_cfg.macd_sig_w}': 'macd_hist_w_calc'}, inplace=True)
        
        # 將計算好的週線指標合併回日線 df
        if 'macd_hist_w_calc' in df_w.columns:
            df = df.merge(df_w[['macd_hist_w_calc']], how='left', left_index=True, right_index=True)
            df['macd_hist_w'] = df['macd_hist_w_calc'].ffill()
            df.drop(columns=['macd_hist_w_calc'], inplace=True)
            
    return df
# ================= 函數結束 =================

def check_entry_signal(df: pd.DataFrame, inds_cfg: IndParams, strat_cfg: StratCfg, filter_cfg: FilterCfg) -> bool:
    if len(df) < 2: return False
    latest = df.iloc[-1]
    
    required_cols = ['macd_hist_d', 'macd_hist_d_prev', 'adx_d', 'adx_d_prev', 'rsi_d', 'atr_d', 'volume']
    if filter_cfg.use_w_macd: required_cols.append('macd_hist_w')
    if filter_cfg.use_vol: required_cols.append('vol_sma')
    if any(pd.isna(latest.get(col)) for col in required_cols): return False

    cond_macd_xo = latest['macd_hist_d'] > 0 and latest['macd_hist_d_prev'] <= 0
    cond_adx_rise = latest['adx_d'] > latest['adx_d_prev']
    cond_adx_str = latest['adx_d'] > strat_cfg.adx_entry_th
    cond_rsi_str = latest['rsi_d'] > strat_cfg.rsi_entry_th
    
    cond_w_macd = (not filter_cfg.use_w_macd) or (latest['macd_hist_w'] > 0)
    cond_vol = (not filter_cfg.use_vol) or (latest['volume'] > latest['vol_sma'])

    return all([cond_macd_xo, cond_adx_rise, cond_adx_str, cond_rsi_str, cond_w_macd, cond_vol])

def check_exit_signal(df: pd.DataFrame, pos: Position, inds_cfg: IndParams, strat_cfg: StratCfg, stop_cfg: StopCfg) -> Optional[str]:
    if len(df) < 2: return "數據不足"
    latest = df.iloc[-1]
    
    pos.highest_price_since_entry = max(pos.highest_price_since_entry, latest['high'])
    profit_pct_trail_check = ((latest['high'] - pos.entry_price) / pos.entry_price) * 100
    
    if not pos.trailing_stop_active and profit_pct_trail_check >= stop_cfg.trail_act_pct:
        pos.trailing_stop_active = True
        logger.info(f"[{pos.stock_id}] 追蹤停利已激活 at profit {profit_pct_trail_check:.2f}%")

    if pos.trailing_stop_active:
        potential_trail_stop = pos.highest_price_since_entry * (1.0 - stop_cfg.trail_ret_pct / 100.0)
        pos.current_trailing_stop_price = max(pos.current_trailing_stop_price, potential_trail_stop)

    if pos.trailing_stop_active and pos.current_trailing_stop_price > 0 and latest['low'] <= pos.current_trailing_stop_price:
        return f"觸發追蹤停利@{pos.current_trailing_stop_price:.2f}"

    if latest['low'] <= pos.initial_stop_loss_price:
        return f"觸發初始停損@{pos.initial_stop_loss_price:.2f}"
        
    if strat_cfg.use_macd_dx_exit:
        if pd.notna(latest.get('macd_hist_d')) and pd.notna(latest.get('macd_hist_d_prev')) and \
           latest['macd_hist_d'] < 0 and latest['macd_hist_d_prev'] >= 0:
            return "觸發日線MACD死叉"
    
    if pd.notna(latest.get('rsi_d')) and latest['rsi_d'] < strat_cfg.rsi_exit_th:
        return f"觸發RSI低於{strat_cfg.rsi_exit_th}"

    return None

def load_portfolio(path: str, manual_portfolio: Dict[str, Position]) -> Dict[str, Position]:
    if os.path.exists(path):
        logger.info(f"從 {path} 讀取現有持股...")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {stock_id: Position(**pos_data) for stock_id, pos_data in data.items()}
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"持股文件 {path} 格式錯誤或為空，將使用手動設定的持股組合。")
            return manual_portfolio
    else:
        logger.info("未找到持股文件，將使用腳本內手動設定的初始持股。")
        return manual_portfolio

def save_portfolio(path: str, portfolio: Dict[str, Position]):
    with open(path, 'w', encoding='utf-8') as f:
        data_to_save = {stock_id: asdict(pos) for stock_id, pos in portfolio.items()}
        json.dump(data_to_save, f, indent=4, ensure_ascii=False)

def create_position_from_manual_input(manual_input: Dict[str, Dict[str, Any]], paths: Paths, inds_cfg: IndParams, stop_cfg: StopCfg, filter_cfg: FilterCfg) -> Position:
    stock_id = manual_input['stock_id']
    entry_price = manual_input['entry_price']
    
    parquet_path = os.path.join(paths.data_dir, f"{stock_id}_history.parquet")
    if not os.path.exists(parquet_path):
        raise FileNotFoundError(f"無法為手動持股 {stock_id} 找到數據文件以計算停損。")

    df_raw = pd.read_parquet(parquet_path)
    df_prep = prep_data(stock_id, df_raw, MIN_REQUIRED_DAILY_DATA_BASELINE)
    if df_prep is None:
        raise ValueError(f"無法為手動持股 {stock_id} 準備數據。")

    df_inds = calc_inds(df_prep, inds_cfg, filter_cfg)
    
    entry_date = pd.to_datetime(manual_input['entry_date'])
    trade_day_data = df_inds.loc[df_inds.index <= entry_date].iloc[-1]

    atr_at_entry = trade_day_data['atr_d']
    if pd.isna(atr_at_entry):
        raise ValueError(f"在 {entry_date} 無法計算 {stock_id} 的ATR值，請檢查數據。")

    hard_sl = entry_price * (1.0 + stop_cfg.hard_sl_pct / 100.0)
    atr_sl = entry_price - (stop_cfg.atr_mult * atr_at_entry)
    initial_stop_loss_price = max(atr_sl, hard_sl)

    return Position(
        stock_id=stock_id, entry_date=manual_input['entry_date'], entry_price=entry_price,
        initial_stop_loss_price=initial_stop_loss_price,
        highest_price_since_entry=manual_input.get('highest_price_since_entry', entry_price),
        trailing_stop_active=False, current_trailing_stop_price=0.0
    )

def run_daily_scan(paths: Paths, inds_cfg: IndParams, strat_cfg: StratCfg, stop_cfg: StopCfg, filter_cfg: FilterCfg, manual_portfolio: Dict[str, Position]):
    today_str = datetime.now().strftime('%Y-%m-%d')
    report = [f"====== 狂戰士之路-每日神諭 ({today_str}) ======"]
    
    try:
        with open(paths.list_path, "r", encoding="utf-8") as f: stock_list = [line.strip() for line in f if line.strip().isdigit()]
    except FileNotFoundError: logger.error(f"股票列表文件 {paths.list_path} 未找到！"); return
        
    portfolio = load_portfolio(paths.portfolio_path, manual_portfolio)
    current_holdings_ids = list(portfolio.keys())
    
    # 掃描出場
    exits_today = []
    report.append("\n--- (1) 檢視戰場 (出場掃描) ---")
    if not current_holdings_ids: report.append("英靈殿中尚無戰士。")
    
    for stock_id in current_holdings_ids:
        pos = portfolio[stock_id]
        parquet_path = os.path.join(paths.data_dir, f"{stock_id}_history.parquet")
        if not os.path.exists(parquet_path):
            exits_today.append((stock_id, "數據文件遺失")); continue
            
        df_raw = pd.read_parquet(parquet_path)
        min_len = (datetime.now() - pd.to_datetime(pos.entry_date)).days + 60
        df_prep = prep_data(stock_id, df_raw, min_len)
        if df_prep is None: logger.warning(f"持股 {stock_id} 數據準備失敗，跳過。"); continue
        
        df_inds = calc_inds(df_prep, inds_cfg, filter_cfg)
        exit_reason = check_exit_signal(df_inds, pos, inds_cfg, strat_cfg, stop_cfg)
        
        if exit_reason:
            exits_today.append((stock_id, exit_reason))
            report.append(f"[撤退] {stock_id}: {exit_reason}")
        else:
            portfolio[stock_id] = pos 

    if not exits_today and current_holdings_ids: report.append("所有戰士仍在奮戰，無人撤退。")

    # 掃描進場
    entries_today = []
    report.append("\n--- (2) 尋找新的勇士 (進場掃描) ---")
    stocks_to_scan = [s for s in stock_list if s not in current_holdings_ids]
    logger.info(f"掃描 {len(stocks_to_scan)} 位潛在的勇士...")
    
    for stock_id in stocks_to_scan:
        parquet_path = os.path.join(paths.data_dir, f"{stock_id}_history.parquet")
        if not os.path.exists(parquet_path): continue
        df_raw = pd.read_parquet(parquet_path)
        df_prep = prep_data(stock_id, df_raw, MIN_REQUIRED_DAILY_DATA_BASELINE)
        if df_prep is None: continue
        
        df_inds = calc_inds(df_prep, inds_cfg, filter_cfg)
        if check_entry_signal(df_inds, inds_cfg, strat_cfg, filter_cfg):
            latest_price = df_inds.iloc[-1]['close']
            entries_today.append((stock_id, latest_price))
            report.append(f"[入列] {stock_id}: 響應召喚！ 最新價格 {latest_price:.2f}")

    if not entries_today: report.append("今日塵世寂靜，無新的勇士誕生。")
        
    # 更新持股
    for stock_id, _ in exits_today:
        if stock_id in portfolio: del portfolio[stock_id]
            
    for stock_id, entry_price in entries_today:
        df_raw = pd.read_parquet(os.path.join(paths.data_dir, f"{stock_id}_history.parquet"))
        df_prep = prep_data(stock_id, df_raw, MIN_REQUIRED_DAILY_DATA_BASELINE)
        df_inds = calc_inds(df_prep, inds_cfg, filter_cfg)
        atr_at_entry = df_inds.iloc[-1]['atr_d']
        hard_sl = entry_price * (1.0 + stop_cfg.hard_sl_pct / 100.0)
        atr_sl = entry_price - (stop_cfg.atr_mult * atr_at_entry)
        initial_stop_loss_price = max(atr_sl, hard_sl)
        
        new_pos = Position(
            stock_id=stock_id, entry_date=today_str, entry_price=entry_price,
            initial_stop_loss_price=initial_stop_loss_price, highest_price_since_entry=entry_price
        )
        portfolio[stock_id] = new_pos

    save_portfolio(paths.portfolio_path, portfolio)
    report.append(f"\n英靈殿名冊已更新: {paths.portfolio_path}")
    
    print("\n" + "="*50)
    print("\n".join(report))
    print("="*50 + "\n")
    logger.info("每日神諭發布完畢。")


if __name__ == '__main__':
    base_dir = r"D:\飆股篩選" # 這行在 Actions 中會被 sed 取代
    paths_config = Paths(base=base_dir)
    
    if not os.path.exists(paths_config.log_dir): os.makedirs(paths_config.log_dir)
    log_file = os.path.join(paths_config.log_dir, f"daily_berserker_{datetime.now().strftime('%Y%m%d')}.log")
    logging.basicConfig(level=logging.INFO, 
                        format='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s',
                        handlers=[logging.FileHandler(log_file, encoding='utf-8'), 
                                  logging.StreamHandler()])

    # --- 加冕神王：混沌神王．極速終焉 (VAL_B1_T05) ---
    logger.info("鑄造神兵：混沌神王．極速終焉...")
    CHAOS_KING_INDS = IndParams(
        macd_f_d=24, macd_s_d=60, macd_sig_d=24, adx_p_d=10, rsi_p_d=12, atr_p_d=15,
        adx_p_w_exit=0, macd_f_w=20, macd_s_w=50, macd_sig_w=20, vol_sma_p=20
    )
    CHAOS_KING_STRAT = StratCfg(
        adx_entry_th=14.0, rsi_entry_th=66.0, rsi_exit_th=20.0,
        use_macd_hist_exit=False, use_macd_dx_exit=True
    )
    CHAOS_KING_STOPS = StopCfg(
        atr_mult=10.0, hard_sl_pct=-40.0, trail_act_pct=80.0, trail_ret_pct=60.0
    )
    CHAOS_KING_FILTERS = FilterCfg(use_w_macd=True, use_vol=True)
    
    # --- 手動設定初始英靈 (如果 portfolio_berserker.json 不存在) ---
    MANUAL_INITIAL_STOCKS = {
        # "2330": {"entry_date": "2023-10-20", "entry_price": 543.0},
    }
    
    manual_portfolio_full = {}
    if MANUAL_INITIAL_STOCKS:
        logger.info("正在從手動名冊召喚初始英靈...")
        for stock_id, info in MANUAL_INITIAL_STOCKS.items():
            try:
                full_info = {'stock_id': stock_id, **info}
                manual_portfolio_full[stock_id] = create_position_from_manual_input(
                    full_info, paths_config, CHAOS_KING_INDS, CHAOS_KING_STOPS, CHAOS_KING_FILTERS
                )
                logger.info(f"成功召喚: {stock_id} @ {info['entry_price']} on {info['entry_date']}")
            except (FileNotFoundError, ValueError) as e:
                logger.error(f"無法召喚 {stock_id}: {e}")

    start_time = time.time()
    logger.info("--- 狂戰士之路已開啟，開始發布每日神諭 ---")
    
    run_daily_scan(
        paths=paths_config,
        inds_cfg=CHAOS_KING_INDS,
        strat_cfg=CHAOS_KING_STRAT,
        stop_cfg=CHAOS_KING_STOPS,
        filter_cfg=CHAOS_KING_FILTERS,
        manual_portfolio=manual_portfolio_full
    )
    
    end_time = time.time()
    logger.info(f"--- 神諭發布完畢，耗時: {end_time - start_time:.2f} 秒。願您武運昌隆！ ---")

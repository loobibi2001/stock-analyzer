import streamlit as st
import pandas as pd
import os
import time
import traceback

# --- 引入您自己的真實策略腳本 ---
# 確保 daily_trader_main.py 和這個 app.py 檔案在同一個資料夾中
try:
    import daily_trader_main
except ImportError:
    st.error("錯誤：找不到 'daily_trader_main.py' 檔案。請確保它和 app.py 在同一個目錄下。")
    st.stop()


# ==============================================================================
# --- 後端邏輯區 (真實邏輯呼叫) ---
# ==============================================================================

def run_champion_strategy():
    """
    執行您的冠軍策略分析腳本 (daily_trader_main.py)，並處理產出的 JSON 檔案。
    """
    st.write("程式提示：正在執行您的每日交易主腳本...")
    
    try:
        # --- ↓↓↓ 這是整合的核心步驟 ↓↓↓ ---
        # 直接呼叫您腳本中的 main() 函式來執行所有分析
        daily_trader_main.main() # 執行您的腳本
        # --- 整合的核心步驟結束 ---

        # **重要**: 現在我們處理 JSON 檔案
        original_filename = "portfolio_berserker.json" # <<< 已更新為您指定的檔名
        target_filename = "trade_signals.csv"

        if os.path.exists(original_filename):
            st.write(f"程式提示：已找到策略產出的檔案 '{original_filename}'。")
            
            # 讀取 JSON 檔案
            df_from_json = pd.read_json(original_filename)
            
            # 將 DataFrame 儲存為 CSV 檔案，供網頁前端使用
            df_from_json.to_csv(target_filename, index=False)
            
            st.write(f"程式提示：已成功將 '{original_filename}' 轉換並儲存為 '{target_filename}'。")
        else:
            st.error(f"錯誤：策略腳本執行完畢，但找不到預期的結果檔案 '{original_filename}'。請檢查您的策略腳本。")
            return False

        print("真實邏輯：策略分析完成，交易訊號已更新。")
        return True

    except Exception as e:
        st.error(f"執行您的策略腳本時發生錯誤：{e}")
        st.code(traceback.format_exc()) # 顯示詳細的錯誤追蹤訊息
        return False


# --- 以下的輔助函式通常不需要修改 ---

def load_trade_signals():
    """載入交易訊號檔案"""
    if os.path.exists("trade_signals.csv"):
        return pd.read_csv("trade_signals.csv")
    return pd.DataFrame()

def load_portfolio():
    """載入使用者儲存的持股檔案"""
    if os.path.exists("my_portfolio.csv"):
        return pd.read_csv("my_portfolio.csv")
    return pd.DataFrame([
        {"股票代號": "2330.TW", "持有股數": 1000, "平均成本": 600.5},
        {"股票代號": "00878.TW", "持有股數": 5000, "平均成本": 22.1},
    ])

def save_portfolio(df):
    """儲存持股 DataFrame 到 CSV 檔案"""
    df.to_csv("my_portfolio.csv", index=False)

# ==============================================================================
# --- 前端網頁介面 (UI) ---
# ==============================================================================

def main():
    # 設定頁面標題與佈局
    st.set_page_config(page_title="股市策略分析儀", layout="wide")

    # --- 側邊欄 (Sidebar) ---
    with st.sidebar:
        st.image("https://placehold.co/150x80/000000/FFFFFF?text=Logo", width=150)
        st.header("控制面板")
        
        # 根據您的個人化資訊，顯示冠軍策略名稱
        st.caption("當前冠軍策略: Alloc40_B1_T21_NoFiltVol")

        if st.button("更新今日資料與分析", type="primary", use_container_width=True):
            with st.spinner("正在執行您的每日交易腳本...請稍候..."):
                success = run_champion_strategy()
            
            if success:
                st.success("分析已全部完成！")
                st.toast("訊號已刷新！", icon="🎉")
            else:
                st.error("分析過程中發生錯誤，請查看上方訊息。")

        st.divider()

        st.header("我的持股管理")
        portfolio_df = load_portfolio()
        edited_portfolio = st.data_editor(
            portfolio_df, 
            num_rows="dynamic",
            key="portfolio_editor",
            use_container_width=True
        )
        
        if st.button("儲存我的持股", use_container_width=True):
            save_portfolio(edited_portfolio)
            st.success("持股資料已儲存！")

    # --- 主畫面 (Main Content) ---
    st.title("📈 股市策略分析儀")
    
    signals_df = load_trade_signals()

    if signals_df.empty:
        st.info("目前沒有交易訊號，請點擊左側按鈕進行分析。")
    else:
        st.subheader("今日交易訊號")
        # 為了應對不同的欄位名稱，做更具彈性的處理
        signal_column = None
        if 'Action' in signals_df.columns:
            signal_column = 'Action'
        elif '訊號' in signals_df.columns:
            signal_column = '訊號'
        
        if signal_column:
            filter_options = ['全部'] + signals_df[signal_column].unique().tolist()
            signal_filter = st.selectbox("訊號篩選：", options=filter_options)
            if signal_filter == '全部':
                st.dataframe(signals_df, use_container_width=True)
            else:
                st.dataframe(signals_df[signals_df[signal_column] == signal_filter], use_container_width=True)
        else:
            st.warning("在結果檔案中找不到可供篩選的 'Action' 或 '訊號' 欄位。")
            st.dataframe(signals_df, use_container_width=True)

        st.divider()

        st.subheader("我的持股訊號警示")
        my_portfolio = load_portfolio()
        if my_portfolio.empty:
            st.warning("您尚未建立持股清單，請至左側側邊欄新增。")
        else:
            # 為了應對不同的股票代號欄位名稱
            stock_id_column = None
            if 'Stock' in signals_df.columns:
                stock_id_column = 'Stock'
            elif '股票代號' in signals_df.columns:
                stock_id_column = '股票代號'
            
            if stock_id_column and '股票代號' in my_portfolio.columns:
                signals_df_renamed = signals_df.rename(columns={stock_id_column: '股票代號'})
                alerts_df = pd.merge(my_portfolio, signals_df_renamed, on='股票代號', how="inner")
                
                if alerts_df.empty:
                    st.success("太好了！您的持股目前沒有出現任何新的買賣訊號。")
                else:
                    st.warning("注意！您的以下持股出現新的交易訊號：")
                    st.dataframe(alerts_df, use_container_width=True)
            else:
                st.error("無法進行持股比對，因為訊號檔或持股檔中缺少可對應的股票代號欄位。")

if __name__ == "__main__":
    main()

import streamlit as st
import pandas as pd
import os
import time
import traceback
import logging # 引入 logging 模組

logger = logging.getLogger(__name__) # 初始化日誌記錄器

# --- 引入您自己的真實策略腳本 ---
# 確保 daily_trader_main.py 和這個 app.py 檔案在同一個資料夾中
try:
    # 嘗試導入 daily_trader_main 模組
    import daily_trader_main
except ImportError as e:
    st.error(f"錯誤：無法導入 'daily_trader_main.py' 模組。請確保它和 app.py 在同一個目錄下，且其內部沒有語法錯誤導致導入失敗。詳情：{e}")
    st.stop()
except Exception as e:
    st.error(f"在嘗試導入 'daily_trader_main.py' 時發生意外錯誤：{e}")
    st.code(traceback.format_exc()) # 顯示詳細的錯誤追蹤訊息
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
        # 確保 daily_trader_main.py 中有一個 main() 函式
        daily_trader_main.main() # 執行您的腳本
        # --- 整合的核心步驟結束 ---

        # **重要**: 現在我們處理 JSON 檔案
        original_filename = "portfolio_berserker.json" # <<< 已更新為您指定的檔名
        target_filename = "trade_signals.csv"

        if os.path.exists(original_filename):
            st.write(f"程式提示：已找到策略產出的檔案 '{original_filename}'。")
            
            # 讀取 JSON 檔案並處理可能的空文件或格式錯誤
            try:
                df_from_json = pd.read_json(original_filename)
                if df_from_json.empty:
                    st.warning(f"警告：'{original_filename}' 檔案是空的，沒有產生任何交易訊號。")
                    # 創建一個空的 trade_signals.csv，避免 EmptyDataError
                    pd.DataFrame(columns=['股票代號', '日期', '價格', '訊號', '理由']).to_csv(target_filename, index=False)
                    return True # 雖然沒有訊號，但流程是成功的
            except pd.errors.EmptyDataError:
                st.warning(f"警告：'{original_filename}' 檔案為空或無效 JSON，將生成空的交易訊號。")
                pd.DataFrame(columns=['股票代號', '日期', '價格', '訊號', '理由']).to_csv(target_filename, index=False)
                return True
            except Exception as e:
                st.error(f"讀取 '{original_filename}' 時發生錯誤：{e}。請檢查 JSON 檔案格式。")
                st.code(traceback.format_exc())
                return False
            
            # 將 DataFrame 儲存為 CSV 檔案，供網頁前端使用
            df_from_json.to_csv(target_filename, index=False)
            
            st.write(f"程式提示：已成功將 '{original_filename}' 轉換並儲存為 '{target_filename}'。")
        else:
            st.error(f"錯誤：策略腳本執行完畢，但找不到預期的結果檔案 '{original_filename}'。請檢查您的策略腳本是否成功生成了此檔案。")
            # 如果 json 文件都沒生成，也創建一個空的 CSV
            pd.DataFrame(columns=['股票代號', '日期', '價格', '訊號', '理由']).to_csv(target_filename, index=False)
            return False

        print("真實邏輯：策略分析完成，交易訊號已更新。")
        return True

    except Exception as e:
        st.error(f"執行您的策略腳本時發生錯誤：{e}")
        st.code(traceback.format_exc()) # 顯示詳細的錯誤追蹤訊息
        return False


# --- 以下的輔助函式通常不需要修改 ---

def load_trade_signals():
    """
    載入交易訊號檔案。
    已修改：如果檔案不存在或為空，返回一個空的 DataFrame，避免報錯。
    """
    if os.path.exists("trade_signals.csv"):
        try:
            df = pd.read_csv("trade_signals.csv")
            if df.empty:
                logger.warning("trade_signals.csv 檔案存在但為空。")
            return df
        except pd.errors.EmptyDataError:
            logger.warning("trade_signals.csv 檔案為空，無法解析列。")
            return pd.DataFrame() # 返回空DataFrame
        except Exception as e:
            logger.error(f"讀取 trade_signals.csv 時發生錯誤：{e}")
            # st.error(f"載入交易訊號時發生問題，請檢查日誌。") # 避免在 UI 上顯示過多技術錯誤
            return pd.DataFrame() # 返回空DataFrame
    logger.info("trade_signals.csv 檔案不存在，返回空的交易訊號。")
    return pd.DataFrame()

def load_portfolio():
    """載入使用者儲存的持股檔案"""
    # 檢查檔案是否存在，如果不存在則創建一個帶有預設值的 DataFrame
    if os.path.exists("my_portfolio.csv"):
        try:
            df = pd.read_csv("my_portfolio.csv")
            # 確保有預期的欄位，如果沒有則加上
            if '股票代號' not in df.columns:
                df['股票代號'] = ''
            if '持有股數' not in df.columns:
                df['持有股數'] = 0
            if '平均成本' not in df.columns:
                df['平均成本'] = 0.0
            return df
        except pd.errors.EmptyDataError:
            logger.warning("my_portfolio.csv 檔案為空，將載入預設持股範例。")
            pass # 繼續執行到返回預設 DataFrame
        except Exception as e:
            logger.error(f"讀取 my_portfolio.csv 時發生錯誤：{e}")
            st.warning("載入持股資料時發生錯誤，請檢查檔案。將載入預設範例。")
    return pd.DataFrame([
        {"股票代號": "2330.TW", "持有股數": 1000, "平均成本": 600.5},
        {"股票代號": "00878.TW", "持有股數": 5000, "平均成本": 22.1},
    ])

def save_portfolio(df):
    """儲存持股 DataFrame 到 CSV 檔案"""
    # 確保 DataFrame 不為空，避免寫入空檔案
    if not df.empty:
        df.to_csv("my_portfolio.csv", index=False)
    else:
        # 如果用戶清空了所有持股，也應將檔案寫入為空，或者刪除檔案
        if os.path.exists("my_portfolio.csv"):
            os.remove("my_portfolio.csv")
        st.info("持股清單已清空。")

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
        # 從Saved Information中讀取，這裡使用最新一條
        st.caption("當前冠軍策略: Alloc40_B1_T21_NoFiltVol")

        if st.button("更新今日資料與分析", type="primary", use_container_width=True):
            with st.spinner("正在執行您的每日交易腳本...請稍候..."):
                success = run_champion_strategy()
            
            if success:
                st.success("分析已全部完成！")
                st.toast("訊號已刷新！", icon="🎉")
                # 重新載入訊號以更新顯示
                st.session_state['signals_updated'] = True # 使用 session_state 觸發重繪
                # 觸發 Streamlit 的重新運行，以更新主內容區
                st.rerun() 
            else:
                st.error("分析過程中發生錯誤，請查看上方訊息。")
                st.session_state['signals_updated'] = False # 標記為未更新，以防萬一
                st.rerun()

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
            st.rerun() # 儲存後也重新運行一次以更新介面

    # --- 主畫面 (Main Content) ---
    st.title("📈 股市策略分析儀")
    
    # 每次運行都重新載入訊號，以確保是最新的
    signals_df = load_trade_signals()

    if signals_df.empty:
        # 這裡顯示友善的提示訊息
        st.info("今日搜尋不到適合進場或出場的個股。")
    else:
        st.subheader("今日交易訊號")
        # 為了應對不同的欄位名稱，做更具彈性的處理
        signal_column = None
        if '訊號' in signals_df.columns: # 優先檢查中文 '訊號'
            signal_column = '訊號'
        elif 'Action' in signals_df.columns: # 其次檢查英文 'Action'
            signal_column = 'Action'
        
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
            # 確保 signals_df 不為空，才進行合併操作
            if not signals_df.empty:
                # 為了應對不同的股票代號欄位名稱
                stock_id_column = None
                if '股票代號' in signals_df.columns: # 優先檢查中文 '股票代號'
                    stock_id_column = '股票代號'
                elif 'Stock' in signals_df.columns: # 其次檢查英文 'Stock'
                    stock_id_column = 'Stock'
                
                if stock_id_column and '股票代號' in my_portfolio.columns:
                    signals_df_renamed = signals_df.rename(columns={stock_id_column: '股票代號'})
                    # 使用 inner join 只保留同時在持股和訊號中存在的股票
                    alerts_df = pd.merge(my_portfolio, signals_df_renamed, on='股票代號', how="inner")
                    
                    if alerts_df.empty:
                        st.success("太好了！您的持股目前沒有出現任何新的買賣訊號。")
                    else:
                        st.warning("注意！您的以下持股出現新的交易訊號：")
                        st.dataframe(alerts_df, use_container_width=True)
                else:
                    st.error("無法進行持股比對，因為訊號檔或持股檔中缺少可對應的股票代號欄位。")
            else:
                st.info("沒有交易訊號產生，無法比對持股警示。")

if __name__ == "__main__":
    main()

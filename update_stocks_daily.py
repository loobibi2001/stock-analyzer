from FinMind.data import DataLoader
import os
import pandas as pd
from datetime import date, timedelta, datetime 
import time

print(f"--- 每日更新腳本開始執行 (FinMind API - 付費版, D槽路徑) --- ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")

# --- 設定 ---
# 【請務必填入您自己的 FinMind API Token】
finmind_api_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNS0wNS0yNSAxODo0MzozMSIsInVzZXJfaWQiOiJsb29iaWJpMjAwMSIsImlwIjoiMTE0LjQ3LjE1MS4xNTIifQ.DlJCvlAcFZBsFVuSja0VpVxX1AsH3MdFE-s32HAMfhA" 

# --- 【【【路徑變更部分】】】 ---
base_path = r"D:\飆股篩選" 
stock_data_folder_name = "StockData_FinMind" 
stock_list_file_name = "stock_list.txt" # 備用，如果 StockData_FinMind 為空

stock_folder = os.path.join(base_path, stock_data_folder_name) 
stock_list_file_path = os.path.join(base_path, stock_list_file_name)
# --- 【路徑變更結束】 ---

today = date.today()
# 【付費版可以嘗試較短的延遲，請依您的方案調整，更新時通常請求量不大】
delay_seconds = 0.5 
# 【設定一個較早的起始日期，用於當 StockData_FinMind 為空或某股票CSV不存在時，嘗試補齊數據】
default_start_date_for_missing = '2000-01-01' 

print(f"設定的基礎路徑: {base_path}")
print(f"設定的 CSV 資料夾路徑: {stock_folder}")
print(f"設定的股票列表檔案路徑 (備用): {stock_list_file_path}")
print(f"設定的請求延遲時間: {delay_seconds} 秒")
print(f"今天的日期: {today.strftime('%Y-%m-%d')}")

# --- 檢查 API Token ---
if not finmind_api_token or finmind_api_token == "YOUR_FINMIND_API_TOKEN" or finmind_api_token == "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNS0wNS0yNSAxODo0MzozMSIsInVzZXJfaWQiOiJsb29iaWJpMjAwMSIsImlwIjoiMTE0LjQ3LjE1MS4xNTIifQ.DlJCvlAcFZBsFVuSja0VpVxX1AsH3MdFE-s32HAMfhA":
    if finmind_api_token == "YOUR_FINMIND_API_TOKEN":
         print("!!!!!! 警告：您可能還在使用預設的 'YOUR_FINMIND_API_TOKEN'，請替換成您自己的 Token !!!!!!")
    pass

# --- 登入 API ---
print("--- 登入 FinMind API ---")
try:
    api = DataLoader()
    api.login_by_token(finmind_api_token)
    print("--- 成功登入 FinMind API ---")
except Exception as e:
    print(f"!!!!!! 登入 FinMind API 時發生錯誤: {e} !!!!!!")
    exit()

# --- 檢查 StockData 資料夾是否存在，不存在則嘗試建立 ---
# 每日更新腳本主要功能是更新已有的，但如果資料夾不存在，也嘗試建立一下
try:
    os.makedirs(stock_folder, exist_ok=True)
    print(f"確保資料夾 '{stock_folder}' 存在 (若不存在則建立)。")
except Exception as e:
    print(f"!!!!!! 建立主要資料夾 '{stock_folder}' 時發生錯誤: {e} !!!!!!")
    # 如果連主資料夾都無法建立，後續可能會有問題

# --- 取得要更新的股票列表 ---
stock_ids_to_update = []
if os.path.exists(stock_folder) and os.listdir(stock_folder): # 檢查資料夾存在且非空
    print(f"--- 正在讀取 {stock_folder} 中的 CSV 檔案列表 ---")
    try:
        csv_files = [f for f in os.listdir(stock_folder) if f.endswith('_history.csv')]
        stock_ids_to_update = [f.replace('_history.csv', '') for f in csv_files]
        print(f"找到 {len(stock_ids_to_update)} 個已下載的股票 CSV 檔案需要檢查更新。")
    except Exception as e:
        print(f"!!!!!! 讀取資料夾 {stock_folder} 時發生錯誤: {e} !!!!!!")
        # 如果讀取現有CSV列表失敗，仍然嘗試從 stock_list.txt 讀取
        stock_ids_to_update = [] 
else: # 如果 StockData_FinMind 不存在或為空
    print(f"!!!!!! 資料夾 {stock_folder} 不存在或為空。 !!!!!!")

if not stock_ids_to_update: # 如果從資料夾沒讀到，或讀取出錯
    print(f"!!!!!! 將嘗試從 {stock_list_file_path} 讀取股票列表以進行首次下載或補全。 !!!!!!")
    try:
        with open(stock_list_file_path, "r", encoding="utf-8") as f:
            stock_ids_to_update = [line.strip() for line in f if line.strip() and line.strip().isdigit() and (len(line.strip()) == 4 or len(line.strip()) == 6)]
        if stock_ids_to_update:
            print(f"從 {stock_list_file_path} 讀取了 {len(stock_ids_to_update)} 支股票代碼進行處理。")
        else:
            print(f"!!!!!! {stock_list_file_path} 是空的或不包含有效代碼。腳本結束。 !!!!!!")
            exit()
    except FileNotFoundError:
        print(f"!!!!!! 錯誤：也找不到 {stock_list_file_path} 檔案！請提供股票列表。腳本結束。 !!!!!!")
        exit()
    except Exception as e:
        print(f"!!!!!! 讀取 {stock_list_file_path} 時發生錯誤: {e} !!!!!!")
        exit()


if not stock_ids_to_update: # 再次檢查
    print("!!!!!! 最終沒有可供更新或下載的股票列表，腳本結束。 !!!!!!")
    exit()

# --- 迴圈更新 ---
print(f"--- 開始檢查並更新/下載 {len(stock_ids_to_update)} 支股票資料 ---")
updated_count = 0
newly_downloaded_count = 0
already_latest_count = 0
error_count = 0

for i, stock_id in enumerate(stock_ids_to_update):
    file_path = os.path.join(stock_folder, f"{stock_id}_history.csv")
    print(f"  > ({i+1}/{len(stock_ids_to_update)}) 正在處理: {stock_id}")

    last_date_in_file = None
    file_exists = os.path.exists(file_path)
    
    if file_exists:
        try:
            existing_df = pd.read_csv(file_path, usecols=['date']) 
            if not existing_df.empty:
                existing_df['date'] = pd.to_datetime(existing_df['date'])
                last_date_in_file = existing_df['date'].iloc[-1].date()
            else:
                print(f"    >> {stock_id}.csv 是空的，將嘗試從預設起始日期下載。")
        except pd.errors.EmptyDataError:
            print(f"    >> {stock_id}.csv 無法解析為空檔案，將嘗試從預設起始日期下載。")
        except Exception as e:
            print(f"    >> 讀取舊檔 {file_path} 時發生錯誤: {e}。將嘗試從預設起始日期下載。")

    # 決定下載的開始日期
    if last_date_in_file:
        start_date_to_download = last_date_in_file + timedelta(days=1)
    else: # 檔案不存在或是空的/讀取失敗
        print(f"    >> 找不到 {stock_id} 的現有資料或檔案為空/損壞，將從 {default_start_date_for_missing} 下載。")
        start_date_to_download = datetime.strptime(default_start_date_for_missing, '%Y-%m-%d').date()

    if start_date_to_download > today:
        print(f"    >> 資料已是最新 (檔案中最後日期: {last_date_in_file if last_date_in_file else 'N/A'})，無需更新。")
        already_latest_count += 1
        time.sleep(delay_seconds/10 if delay_seconds > 0.1 else 0.01) # 對已最新的可以縮短延遲
        continue 

    print(f"    >> 檔案中最後日期: {last_date_in_file if last_date_in_file else '無記錄'}, 將從 {start_date_to_download.strftime('%Y-%m-%d')} 下載至 {today.strftime('%Y-%m-%d')} ...")

    try:
        new_df = api.taiwan_stock_daily(
            stock_id=stock_id,
            start_date=start_date_to_download.strftime('%Y-%m-%d'), 
            end_date=today.strftime('%Y-%m-%d') 
        )

        if not new_df.empty:
            new_df = new_df.rename(columns={
                'date': 'date', 'open': 'Open', 'max': 'High',
                'min': 'Low', 'close': 'Close', 'Trading_Volume': 'Volume'
            })
            required_cols = ['date', 'Open', 'High', 'Low', 'Close', 'Volume']
            actual_cols = [col for col in required_cols if col in new_df.columns]
            
            if len(actual_cols) == len(required_cols):
                new_df_to_save = new_df[actual_cols].copy() # 使用 .copy() 避免 SettingWithCopyWarning
                new_df_to_save.loc[:, 'date'] = pd.to_datetime(new_df_to_save['date']).dt.strftime('%Y-%m-%d')
                
                if file_exists and last_date_in_file is not None: # 檔案存在且有內容，附加
                    new_df_to_save.to_csv(file_path, mode='a', header=False, index=False, encoding='utf-8')
                    print(f"    >> 成功附加 {stock_id} 的新資料 ({len(new_df_to_save)} 筆)。")
                    updated_count += 1
                else: # 檔案不存在或為空，則正常寫入 (含標頭)
                    new_df_to_save.to_csv(file_path, index=False, encoding='utf-8')
                    print(f"    >> 成功下載並儲存 {stock_id} 的新資料 ({len(new_df_to_save)} 筆)。")
                    newly_downloaded_count +=1
            else:
                missing_cols_report = [col for col in required_cols if col not in new_df.columns]
                print(f"    >> {stock_id} 新下載的資料缺少欄位: {missing_cols_report}。跳過儲存。")
                error_count += 1
        else:
            print(f"    >> 在此日期範圍內找不到 {stock_id} 的新資料。")
            already_latest_count +=1

    except Exception as e: 
        print(f"  !!!!!! 處理 {stock_id} 時發生未預期錯誤: {e} !!!!!!")
        error_count += 1
        if "limit" in str(e).lower() or "402" in str(e) or "403" in str(e):
            print("    >> 可能遇到 API 請求限制或權限問題，暫停 10 秒...")
            time.sleep(10)
            
    time.sleep(delay_seconds)

print(f"--- 每日更新腳本執行完畢 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")
print(f"總結：")
print(f"  - 檢查/處理股票總數: {len(stock_ids_to_update)}")
print(f"  - 成功附加更新檔案數: {updated_count}")
print(f"  - 成功全新下載檔案數: {newly_downloaded_count}")
print(f"  - 資料已是最新檔案數: {already_latest_count}")
print(f"  - 發生錯誤/跳過檔案數: {error_count}")
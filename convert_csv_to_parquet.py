import os
import pandas as pd
import time

print("--- CSV 轉 Parquet 轉換腳本開始執行 ---")

# --- 設定 ---
base_path = '.'  # <--- 請確認這是您的基礎路徑
input_csv_folder_name = "StockData_FinMind"  # 來源 CSV 資料夾名稱
output_parquet_folder_name = "StockData_Parquet" # <--- 這是新的 Parquet 儲存資料夾

# 建立完整路徑
input_folder = os.path.join(base_path, input_csv_folder_name)
output_folder = os.path.join(base_path, output_parquet_folder_name)

print(f"來源 CSV 資料夾: {input_folder}")
print(f"目標 Parquet 資料夾: {output_folder}")

# --- 檢查來源資料夾是否存在 ---
if not os.path.exists(input_folder):
    print(f"!!!!!! 錯誤：找不到來源 CSV 資料夾 '{input_folder}'，請確認路徑。 !!!!!!")
    exit() # 結束腳本

# --- 建立目標資料夾 ---
try:
    os.makedirs(output_folder, exist_ok=True)
    print(f"確保目標資料夾 '{output_folder}' 存在。")
except Exception as e:
    print(f"!!!!!! 建立目標資料夾 '{output_folder}' 時發生錯誤: {e} !!!!!!")
    exit()

# --- 開始轉換 ---
start_time = time.time()
converted_count = 0
skipped_count = 0
error_count = 0

print("\n--- 開始掃描並轉換檔案 ---")

# 獲取所有 CSV 檔案列表
try:
    csv_files = [f for f in os.listdir(input_folder) if f.lower().endswith('_history.csv')]
    total_files = len(csv_files)
    print(f"找到 {total_files} 個 '_history.csv' 檔案。")
except Exception as e:
    print(f"!!!!!! 掃描來源資料夾時發生錯誤: {e} !!!!!!")
    exit()

if total_files == 0:
    print("來源資料夾中沒有找到符合條件的 CSV 檔案，腳本結束。")
    exit()

# 逐一轉換
for i, csv_file in enumerate(csv_files):
    input_csv_path = os.path.join(input_folder, csv_file)
    # 將 .csv 替換為 .parquet
    parquet_file = csv_file.replace('_history.csv', '_history.parquet')
    output_parquet_path = os.path.join(output_folder, parquet_file)

    print(f"  > 正在處理 ({i+1}/{total_files}): {csv_file} ... ", end="")

    try:
        # 讀取 CSV
        df = pd.read_csv(input_csv_path)

        # 檢查是否為空
        if df.empty:
            print("檔案為空，跳過。")
            skipped_count += 1
            continue

        # 確保 'date' 欄位是 datetime 格式 (這很重要！)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        else:
             print("找不到 'date' 欄位，跳過。")
             skipped_count += 1
             continue

        # 儲存為 Parquet (使用 pyarrow 引擎)
        df.to_parquet(output_parquet_path, engine='pyarrow', index=False)
        print("轉換成功！")
        converted_count += 1

    except pd.errors.EmptyDataError:
        print("檔案為空 (EmptyDataError)，跳過。")
        skipped_count += 1
    except Exception as e:
        print(f"!!!!!! 轉換失敗: {e} !!!!!!")
        error_count += 1

# --- 轉換完成 ---
end_time = time.time()
duration = end_time - start_time

print("\n--- 轉換完成 ---")
print(f"總共耗時: {duration:.2f} 秒")
print(f"成功轉換: {converted_count} 個檔案")
print(f"跳過 (空檔或無日期): {skipped_count} 個檔案")
print(f"轉換失敗: {error_count} 個檔案")
print(f"Parquet 檔案已儲存至: {output_folder}")
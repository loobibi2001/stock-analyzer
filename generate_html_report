import os
import json
from datetime import datetime, timedelta

def get_latest_log_file(log_dir="logs"):
    """找到最新的日誌檔案"""
    if not os.path.exists(log_dir):
        return None, "日誌目錄不存在"

    log_files = [f for f in os.listdir(log_dir) if f.endswith('.log')]
    if not log_files:
        return None, "沒有找到任何日誌檔案"

    # 假設日誌檔名格式為 YYYY-MM-DD.log
    try:
        latest_file = max(log_files)
        with open(os.path.join(log_dir, latest_file), 'r', encoding='utf-8') as f:
            content = f.read()
        return latest_file, content
    except Exception as e:
        return None, f"讀取日誌檔案時發生錯誤: {e}"

def read_portfolio_data(file_path="portfolio_berserker.json"):
    """讀取投資組合 JSON 檔案"""
    if not os.path.exists(file_path):
        return None, "投資組合檔案不存在"
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data, "讀取成功"
    except Exception as e:
        return None, f"讀取 JSON 檔案時發生錯誤: {e}"

def generate_html_report(portfolio_data, log_filename, log_content):
    """根據資料產生 HTML 報告"""
    
    # --- HTML 模板 ---
    # 我們使用一個大的字串來當作 HTML 模板，之後會用 .format() 填入動態資料
    html_template = """
    <!DOCTYPE html>
    <html lang="zh-Hant">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>自動化投資策略報告</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f4f4f9; color: #333; }}
            .container {{ max-width: 800px; margin: 20px auto; padding: 20px; background-color: #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-radius: 8px; }}
            h1, h2 {{ color: #444; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
            .meta-info {{ background-color: #eef; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            .meta-info p {{ margin: 5px 0; }}
            .portfolio-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            .portfolio-table th, .portfolio-table td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            .portfolio-table th {{ background-color: #007bff; color: white; }}
            .portfolio-table tr:nth-child(even) {{ background-color: #f2f2f2; }}
            .log-section {{ margin-top: 30px; }}
            .log-content {{ background-color: #282c34; color: #abb2bf; padding: 15px; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-family: 'Courier New', Courier, monospace; }}
            .footer {{ text-align: center; margin-top: 20px; font-size: 0.9em; color: #777; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📈 自動化投資策略報告</h1>
            
            <div class="meta-info">
                <p><strong>報告產生時間:</strong> {generation_time}</p>
                <p><strong>最新資料日誌:</strong> {log_filename}</p>
            </div>

            <h2>📊 目前持股狀態</h2>
            {portfolio_html}

            <div class="log-section">
                <h2>📜 最新交易日誌</h2>
                <div class="log-content">{log_content}</div>
            </div>

            <div class="footer">
                <p>由 GitHub Actions 自動產生</p>
            </div>
        </div>
    </body>
    </html>
    """

    # --- 準備要填入的資料 ---

    # 1. 處理持股資料
    if portfolio_data:
        # 如果有股票代碼 (key)
        if portfolio_data.keys():
            table_html = '<table class="portfolio-table"><tr><th>股票代碼</th><th>持有股數</th><th>最後更新</th></tr>'
            for stock, info in portfolio_data.items():
                table_html += f"<tr><td>{stock}</td><td>{info.get('shares', 'N/A')}</td><td>{info.get('last_update', 'N/A')}</td></tr>"
            table_html += '</table>'
        else:
            table_html = "<p>目前無任何持股。</p>"
    else:
        table_html = "<p>無法讀取持股資料。</p>"

    # 2. 處理日誌內容
    log_content_formatted = log_content.replace('<', '&lt;').replace('>', '&gt;')

    # 3. 取得現在時間
    generation_time = (datetime.now() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S (CST)')

    # --- 產生最終 HTML ---
    final_html = html_template.format(
        generation_time=generation_time,
        log_filename=log_filename if log_filename else "N/A",
        portfolio_html=table_html,
        log_content=log_content_formatted
    )

    # --- 寫入檔案 ---
    with open("index.html", "w", encoding='utf-8') as f:
        f.write(final_html)
    print("HTML 報告 (index.html) 已成功產生！")


if __name__ == "__main__":
    # 主要執行區塊
    print("開始產生 HTML 報告...")
    
    portfolio, p_msg = read_portfolio_data()
    print(f"讀取持股檔案: {p_msg}")
    
    log_file, log_data = get_latest_log_file()
    print(f"讀取日誌檔案: {log_file}")
    
    generate_html_report(portfolio, log_file, log_data)

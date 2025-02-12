from flask import Flask, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import pandas as pd
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Fetch data from CoinGecko API
def fetch_top_50_cryptos():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 50,
        "page": 1,
        "sparkline": False
    }
    response = requests.get(url, params=params)
    return response.json() if response.status_code == 200 else None

# Analyze Crypto Data
def analyze_data(data):
    df = pd.DataFrame(data, columns=["name", "symbol", "current_price", "market_cap", "total_volume", "price_change_percentage_24h"])
    top_5_by_market_cap = df.nlargest(5, "market_cap")[["name", "market_cap"]]
    average_price = df["current_price"].mean()
    highest_change = df.nlargest(1, "price_change_percentage_24h")[["name", "price_change_percentage_24h"]]
    lowest_change = df.nsmallest(1, "price_change_percentage_24h")[["name", "price_change_percentage_24h"]]

    return top_5_by_market_cap, average_price, highest_change, lowest_change

# Update Google Sheets
def update_google_sheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_json = os.getenv("GOOGLE_CREDENTIALS")
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)

        sheet = client.open("Cryptocurrency Live Data").sheet1  # Google Sheet name

        data = fetch_top_50_cryptos()
        if not data:
            return {"status": "failed", "message": "Failed to fetch data from CoinGecko"}

        rows = [[crypto["name"], crypto["symbol"], crypto["current_price"], crypto["market_cap"],
                 crypto["total_volume"], crypto["price_change_percentage_24h"]] for crypto in data]

        top_5_by_market_cap, avg_price, highest_change, lowest_change = analyze_data(data)

        additional_columns_header = ["Top 5 Cryptos by Market Cap", "Average Price", "Highest 24h Change", "Lowest 24h Change"]
        additional_columns_data = [
            ", ".join(top_5_by_market_cap["name"].tolist()),
            f"${avg_price:.2f}",
            f"{highest_change['name'].values[0]} ({highest_change['price_change_percentage_24h'].values[0]:.2f}%)",
            f"{lowest_change['name'].values[0]} ({lowest_change['price_change_percentage_24h'].values[0]:.2f}%)"
        ]

        headers = ["Name", "Symbol", "Current Price (USD)", "Market Cap", "24h Volume", "24h Price Change (%)"] + additional_columns_header
        combined_data = [headers]  

        for i, row in enumerate(rows):
            combined_data.append(row + additional_columns_data if i == 0 else row + [""] * len(additional_columns_header))

        sheet.clear()
        sheet.update(combined_data)

        header_range = "A1:J1"  
        sheet.format(header_range, {"textFormat": {"bold": True}})  

        print("Google Sheet updated successfully")
        return {"status": "success", "message": "Google Sheet updated successfully"}

    except Exception as e:
        print(f"Error: {e}")
        return {"status": "error", "message": str(e)}

# Flask Route to Manually Trigger Google Sheet Update
@app.route('/update', methods=['GET'])
def update():
    result = update_google_sheet()
    return jsonify(result)

# Scheduler Setup
scheduler = BackgroundScheduler()
scheduler.add_job(func=update_google_sheet, trigger="interval", minutes=5)  # Run every 5 minutes
scheduler.start()

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)  # Use `use_reloader=False` to prevent multiple scheduler instances

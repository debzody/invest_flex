from flask import Flask, render_template, request, jsonify
from datetime import datetime, timedelta
import logging
import requests
import pytz

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Supabase Setup
SUPABASE_URL = "https://roqjzyveznkcmkozgrbc.supabase.co/rest/v1"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJvcWp6eXZlem5rY21rb3pncmJjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDE4NDcxMTgsImV4cCI6MjA1NzQyMzExOH0.kD7PS9jFryAEw28VPcQ2PkNukEP6gGwyDlCv08hk2AY"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Finnhub API Key 
FINNHUB_API_KEY = "cv67nshr01qi7f6oqp00cv67nshr01qi7f6oqp0g"

# Indian Standard Time
IST = pytz.timezone('Asia/Kolkata')

# Constants
SCHEME_CODES = {
    'HDFC_TECH': '152059',
    'INVESCO_TECH': '152863',
    'MO_SMALLCAP': '152237',
    'MO_MULTICAP': '152651',
    'MO_DEFENCE': '152712',
    'EDEL_TECH': '152438'
}

INITIAL_PRICES = {
    'SAP': 200.00,
    'HONASA.NS': 450.00,
    'HDFCLIFE.NS': 620.00,
    'JIOFIN.NS': 350.00,
    'NTPCGREEN.NS': 105.00,
    'TATATECH.NS': 1100.00,
    'HDFC_TECH': 14.74,
    'INVESCO_TECH': 31.36,
    'MO_SMALLCAP': 14.35,
    'MO_MULTICAP': 10.00,
    'MO_DEFENCE': 6.72,
    'EDEL_TECH': 15.82
}

CURRENCY = {
    'SAP': '$',
    'HONASA.NS': '₹',
    'HDFCLIFE.NS': '₹',
    'JIOFIN.NS': '₹',
    'NTPCGREEN.NS': '₹',
    'TATATECH.NS': '₹',
    'HDFC_TECH': '₹',
    'INVESCO_TECH': '₹',
    'MO_SMALLCAP': '₹',
    'MO_MULTICAP': '₹',
    'MO_DEFENCE': '₹',
    'EDEL_TECH': '₹'
}

USD_TO_INR = 87.2392

# Define the Indian number formatting function
def format_indian(value):
    value_str = f"{float(value):.2f}"
    parts = value_str.split('.')
    integer_part = parts[0]
    decimal_part = parts[1] if len(parts) > 1 else '00'
    
    integer_part = integer_part.replace(',', '')
    length = len(integer_part)
    
    if length <= 3:
        formatted_integer = integer_part
    else:
        formatted_integer = integer_part[-3:]
        remaining = integer_part[:-3]
        while remaining:
            formatted_integer = remaining[-2:] + ',' + formatted_integer
            remaining = remaining[:-2]
        formatted_integer = remaining + ',' + formatted_integer if remaining else formatted_integer
    
    return f"{formatted_integer}.{decimal_part}"

# Register the filter with Flask's Jinja environment
app.jinja_env.filters['format_indian'] = format_indian

def fetch_finnhub_price(symbol):
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        price = data.get("c")
        logger.info(f"Fetched Finnhub price for {symbol}: {price}")
        return float(price) if price and price > 0 else INITIAL_PRICES.get(symbol, 0)
    except Exception as e:
        logger.error(f"Finnhub API error for {symbol}: {e}")
        return INITIAL_PRICES.get(symbol, 0)

def get_nse_live_price(symbol):
    nse_symbol = symbol.replace('.NS', '')
    url = f"https://www.nseindia.com/api/quote-equity?symbol={nse_symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com"
    }
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers)
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        price = data.get("priceInfo", {}).get("lastPrice")
        logger.info(f"Fetched NSE price for {symbol}: {price}")
        return float(price) if price else INITIAL_PRICES.get(symbol, 0)
    except Exception as e:
        logger.error(f"NSE API error for {symbol}: {e}")
        return INITIAL_PRICES.get(symbol, 0)

def get_mutual_fund_nav(symbol):
    scheme_code = SCHEME_CODES.get(symbol)
    if not scheme_code:
        return INITIAL_PRICES.get(symbol, 0)
    url = f"https://api.mfapi.in/mf/{scheme_code}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        nav_data = data["data"][0]
        nav = float(nav_data["nav"])
        logger.info(f"Fetched NAV for {symbol}: {nav}")
        return nav
    except Exception as e:
        logger.error(f"MF API error for {symbol}: {e}")
        return INITIAL_PRICES.get(symbol, 0)

def get_current_price(symbol):
    if symbol == 'SAP':
        return fetch_finnhub_price(symbol)
    elif symbol in SCHEME_CODES:
        return get_mutual_fund_nav(symbol)
    elif symbol.endswith('.NS'):
        return get_nse_live_price(symbol)
    else:
        logger.warning(f"No price fetch method for {symbol}, using initial price")
        return INITIAL_PRICES.get(symbol, 0)

def fetch_investments():
    url = f"{SUPABASE_URL}/investments?select=*"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        logger.info(f"Fetched investments: {data}")
        return data
    except Exception as e:
        logger.error(f"Supabase fetch_investments error: {e}")
        return []

def fetch_accounts():
    url = f"{SUPABASE_URL}/accounts?select=epf,bank_balance&limit=1"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        result = data[0] if data else {"epf": 0, "bank_balance": 0}
        logger.info(f"Fetched accounts: {result}")
        return result
    except Exception as e:
        logger.error(f"Supabase fetch_accounts error: {e}")
        return {"epf": 0, "bank_balance": 0}

def store_daily_values(total_investment, total_mf, total_nse, total_sap, epf, total_liquid):
    today = datetime.now(IST).strftime('%Y-%m-%d')
    url = f"{SUPABASE_URL}/daily_values"
    payload = {
        "date": today,
        "total_investment": total_investment,
        "total_mf": total_mf,
        "total_nse": total_nse,
        "total_sap": total_sap,
        "epf": epf,
        "total_liquid": total_liquid
    }
    try:
        check_url = f"{url}?date=eq.{today}"
        check = requests.get(check_url, headers=HEADERS)
        if check.status_code == 200 and check.json():
            requests.patch(check_url, headers=HEADERS, json=payload)
        else:
            requests.post(url, headers=HEADERS, json=payload)
        logger.info(f"Stored daily values for {today}")
    except Exception as e:
        logger.error(f"Supabase store_daily_values error: {e}")

def get_previous_day_values():
    yesterday = (datetime.now(IST) - timedelta(days=1)).strftime('%Y-%m-%d')
    url = f"{SUPABASE_URL}/daily_values?date=eq.{yesterday}"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        if data:
            d = data[0]
            result = (d["total_investment"], d["total_mf"], d["total_nse"], d["total_sap"], d["epf"], d["total_liquid"])
            logger.info(f"Previous day values for {yesterday}: {result}")
            return result
        return (0, 0, 0, 0, 0, 0)
    except Exception as e:
        logger.error(f"Supabase get_previous_day_values error: {e}")
        return (0, 0, 0, 0, 0, 0)

def get_historical_values():
    url = f"{SUPABASE_URL}/daily_values?select=*&order=date.desc&limit=5"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        result = [[d["date"], d["total_investment"], d["total_mf"], d["total_nse"], d["total_sap"], d["epf"], d["total_liquid"]] for d in data]
        logger.info(f"Historical values: {result}")
        return result
    except Exception as e:
        logger.error(f"Supabase get_historical_values error: {e}")
        return []

def get_monthly_values():
    thirty_days_ago = (datetime.now(IST) - timedelta(days=30)).strftime('%Y-%m-%d')
    url = f"{SUPABASE_URL}/daily_values?date=gte.{thirty_days_ago}&select=*&order=date.asc"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        result = [[d["date"], d["total_investment"]] for d in data]
        logger.info(f"Monthly values: {result}")
        return result
    except Exception as e:
        logger.error(f"Supabase get_monthly_values error: {e}")
        return []

@app.route('/')
def index():
    investments = fetch_investments()
    total_investment = total_mf = total_nse = total_sap = 0
    investment_data = []

    for inv in investments:
        current_price = get_current_price(inv["instrument"])
        value = inv["units"] * current_price if current_price is not None else 0
        if inv["instrument"] == 'SAP':
            total_sap += value * USD_TO_INR
        elif inv["instrument"] in SCHEME_CODES:
            total_mf += value
        elif inv["instrument"].endswith('.NS'):
            total_nse += value
        total_investment += value if inv["currency"] == '₹' else value * USD_TO_INR
        investment_data.append({
            'id': str(inv["id"]),
            'instrument': inv["instrument"],
            'units': inv["units"],
            'current_price': current_price if current_price is not None else 0,
            'currency': inv["currency"],
            'value': value
        })

    accounts = fetch_accounts()
    epf = accounts["epf"]
    bank_balance = accounts["bank_balance"]
    total_liquid = bank_balance
    total_investment += epf + bank_balance

    store_daily_values(total_investment, total_mf, total_nse, total_sap, epf, total_liquid)
    prev_values = get_previous_day_values()
    historical_values = get_historical_values()
    monthly_values = get_monthly_values()

    return render_template('index.html',
                         investments=investment_data,
                         total_investment=total_investment,
                         total_mf=total_mf,
                         total_nse=total_nse,
                         total_sap=total_sap,
                         total_liquid=total_liquid,
                         epf=epf,
                         bank_balance=bank_balance,
                         initial_prices=INITIAL_PRICES,
                         prev_values=prev_values,
                         historical_values=historical_values,
                         monthly_values=monthly_values)

@app.route('/get_prices')
def get_prices():
    investments = fetch_investments()
    total_investment = total_mf = total_nse = total_sap = 0
    investment_data = []

    for inv in investments:
        current_price = get_current_price(inv["instrument"])
        value = inv["units"] * current_price if current_price is not None else 0
        if inv["instrument"] == 'SAP':
            total_sap += value * USD_TO_INR
        elif inv["instrument"] in SCHEME_CODES:
            total_mf += value
        elif inv["instrument"].endswith('.NS'):
            total_nse += value
        total_investment += value if inv["currency"] == '₹' else value * USD_TO_INR
        investment_data.append({
            'id': str(inv["id"]),
            'instrument': inv["instrument"],
            'units': inv["units"],
            'current_price': current_price if current_price is not None else 0,
            'currency': inv["currency"],
            'value': value
        })

    accounts = fetch_accounts()
    epf = accounts["epf"]
    bank_balance = accounts["bank_balance"]
    total_liquid = bank_balance
    total_investment += epf + bank_balance

    store_daily_values(total_investment, total_mf, total_nse, total_sap, epf, total_liquid)
    prev_values = get_previous_day_values()
    historical_values = get_historical_values()
    monthly_values = get_monthly_values()

    return jsonify({
        'investments': investment_data,
        'total_investment': total_investment,
        'total_mf': total_mf,
        'total_nse': total_nse,
        'total_sap': total_sap,
        'total_liquid': total_liquid,
        'epf': epf,
        'bank_balance': bank_balance,
        'prev_values': prev_values,
        'historical_values': historical_values,
        'monthly_values': monthly_values
    })

@app.route('/add_investment', methods=['POST'])
def add_investment():
    data = request.form
    instrument = data['instrument']
    if instrument not in SCHEME_CODES and instrument != 'SAP' and not instrument.endswith('.NS'):
        instrument += '.NS'
    units = float(data['units'])
    initial_price = INITIAL_PRICES.get(instrument, 0)
    currency = CURRENCY.get(instrument, '₹')

    url = f"{SUPABASE_URL}/investments"
    payload = {
        "instrument": instrument,
        "units": units,
        "initial_price": initial_price,
        "current_price": initial_price,
        "currency": currency,
        "purchase_date": datetime.now(IST).strftime('%Y-%m-%d')
    }
    try:
        check_url = f"{url}?instrument=eq.{instrument}"
        check = requests.get(check_url, headers=HEADERS)
        if check.status_code == 200 and check.json():
            existing = check.json()[0]
            new_units = existing["units"] + units
            requests.patch(f"{url}?id=eq.{existing['id']}", headers=HEADERS, json={"units": new_units, "current_price": initial_price})
        else:
            requests.post(url, headers=HEADERS, json=payload)
        logger.info(f"Added/Updated investment: {instrument}, units: {units}")
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Supabase add_investment error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/delete_investment/<id>', methods=['POST'])
def delete_investment(id):
    url = f"{SUPABASE_URL}/investments?id=eq.{id}"
    try:
        requests.delete(url, headers=HEADERS)
        logger.info(f"Deleted investment with id: {id}")
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Supabase delete_investment error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/update_epf', methods=['POST'])
def update_epf():
    data = request.form
    epf = float(data['epf']) if data['epf'] else 0
    
    url = f"{SUPABASE_URL}/accounts"
    payload = {"epf": epf}
    try:
        check_url = f"{url}?select=id&limit=1"
        check = requests.get(check_url, headers=HEADERS)
        if check.status_code == 200 and check.json():
            existing_id = check.json()[0]["id"]
            requests.patch(f"{url}?id=eq.{existing_id}", headers=HEADERS, json=payload)
        else:
            payload["bank_balance"] = 0
            requests.post(url, headers=HEADERS, json=payload)
        logger.info(f"Updated EPF: {epf}")
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Supabase update_epf error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/update_bank_balance', methods=['POST'])
def update_bank_balance():
    data = request.form
    bank_balance = float(data['bank_balance']) if data['bank_balance'] else 0
    
    url = f"{SUPABASE_URL}/accounts"
    payload = {"bank_balance": bank_balance}
    try:
        check_url = f"{url}?select=id&limit=1"
        check = requests.get(check_url, headers=HEADERS)
        if check.status_code == 200 and check.json():
            existing_id = check.json()[0]["id"]
            requests.patch(f"{url}?id=eq.{existing_id}", headers=HEADERS, json=payload)
        else:
            payload["epf"] = 0
            requests.post(url, headers=HEADERS, json=payload)
        logger.info(f"Updated bank balance: {bank_balance}")
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Supabase update_bank_balance error: {e}")
        return jsonify({'status': 'error'}), 500

if __name__ == '__main__':
    try:
        test_response = requests.get(f"{SUPABASE_URL}/investments?limit=1", headers=HEADERS)
        if test_response.status_code == 200:
            logger.info("Successfully connected to Supabase!")
        else:
            logger.error(f"Failed to connect to Supabase: {test_response.status_code} - {test_response.text}")
    except Exception as e:
        logger.error(f"Supabase connection test failed: {e}")
    app.run(debug=True)
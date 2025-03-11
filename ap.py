from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime, timedelta
import logging
import requests
import pytz

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def init_db():
    with sqlite3.connect('investments.db') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS investments
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     instrument TEXT UNIQUE, 
                     units REAL, 
                     initial_price REAL, 
                     current_price REAL, 
                     currency TEXT,
                     purchase_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS accounts
                    (id INTEGER PRIMARY KEY, 
                     epf REAL DEFAULT 0, 
                     bank_balance REAL DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS daily_values
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     date TEXT,
                     total_investment REAL,
                     total_mf REAL,
                     total_nse REAL,
                     total_sap REAL,
                     epf REAL,
                     total_liquid REAL)''')
        c.execute("INSERT OR IGNORE INTO accounts (id, epf, bank_balance) VALUES (1, 0, 0)")

def fetch_finnhub_price(symbol):
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        price = data.get("c")
        return float(price) if price and price > 0 else INITIAL_PRICES.get(symbol, 0)
    except:
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
        return float(price) if price else INITIAL_PRICES.get(symbol, 0)
    except:
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
        return float(nav_data["nav"])
    except:
        return INITIAL_PRICES.get(symbol, 0)

def get_current_price(symbol):
    if symbol == 'SAP':
        return fetch_finnhub_price(symbol)
    elif symbol in SCHEME_CODES:
        return get_mutual_fund_nav(symbol)
    elif symbol.endswith('.NS'):
        return get_nse_live_price(symbol)
    else:
        return INITIAL_PRICES.get(symbol, 0)

def store_daily_values(total_investment, total_mf, total_nse, total_sap, epf, total_liquid):
    with sqlite3.connect('investments.db') as conn:
        c = conn.cursor()
        today = datetime.now(IST).strftime('%Y-%m-%d')
        c.execute("INSERT INTO daily_values (date, total_investment, total_mf, total_nse, total_sap, epf, total_liquid) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (today, total_investment, total_mf, total_nse, total_sap, epf, total_liquid))
        conn.commit()

def get_previous_day_values():
    with sqlite3.connect('investments.db') as conn:
        c = conn.cursor()
        yesterday = (datetime.now(IST) - timedelta(days=1)).strftime('%Y-%m-%d')
        c.execute("SELECT total_investment, total_mf, total_nse, total_sap, epf, total_liquid FROM daily_values WHERE date = ? ORDER BY id DESC LIMIT 1", (yesterday,))
        return c.fetchone() or (0, 0, 0, 0, 0, 0)

def get_historical_values():
    with sqlite3.connect('investments.db') as conn:
        c = conn.cursor()
        c.execute("SELECT date, total_investment, total_mf, total_nse, total_sap, epf, total_liquid FROM daily_values ORDER BY date DESC LIMIT 5")
        return c.fetchall()

@app.route('/')
def index():
    with sqlite3.connect('investments.db') as conn:
        c = conn.cursor()
        
        c.execute("SELECT * FROM investments")
        investments = c.fetchall()
        
        total_investment = total_mf = total_nse = total_sap = 0
        investment_data = []
        for inv in investments:
            current_price = get_current_price(inv[1])
            value = inv[2] * current_price if current_price is not None else 0
            if inv[1] == 'SAP':
                total_sap += value * USD_TO_INR
            elif inv[1] in SCHEME_CODES:
                total_mf += value
            elif inv[1].endswith('.NS'):
                total_nse += value
            total_investment += value if inv[5] == '₹' else value * USD_TO_INR
            investment_data.append({
                'id': inv[0],
                'instrument': inv[1],
                'units': inv[2],
                'current_price': current_price if current_price is not None else 0,
                'currency': inv[5],
                'value': value
            })
        
        c.execute("SELECT epf, bank_balance FROM accounts WHERE id=1")
        account = c.fetchone()
        epf = account[0] if account and account[0] is not None else 0
        bank_balance = account[1] if account and account[1] is not None else 0
        total_liquid = bank_balance
        total_investment += epf + bank_balance
        
        store_daily_values(total_investment, total_mf, total_nse, total_sap, epf, total_liquid)
        prev_values = get_previous_day_values()
        historical_values = get_historical_values()

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
                         historical_values=historical_values)

@app.route('/get_prices')
def get_prices():
    with sqlite3.connect('investments.db') as conn:
        c = conn.cursor()
        c.execute("SELECT id, instrument, units, currency FROM investments")
        investments = c.fetchall()
        
        total_investment = total_mf = total_nse = total_sap = 0
        investment_data = []
        for inv in investments:
            current_price = get_current_price(inv[1])
            value = inv[2] * current_price if current_price is not None else 0
            if inv[1] == 'SAP':
                total_sap += value * USD_TO_INR
            elif inv[1] in SCHEME_CODES:
                total_mf += value
            elif inv[1].endswith('.NS'):
                total_nse += value
            total_investment += value if inv[3] == '₹' else value * USD_TO_INR
            investment_data.append({
                'id': inv[0],
                'instrument': inv[1],
                'units': inv[2],
                'current_price': current_price if current_price is not None else 0,
                'currency': inv[3],
                'value': value
            })
        
        c.execute("SELECT epf, bank_balance FROM accounts WHERE id=1")
        account = c.fetchone()
        epf = account[0] if account else 0
        bank_balance = account[1] if account else 0
        total_liquid = bank_balance
        total_investment += epf + bank_balance
        
        store_daily_values(total_investment, total_mf, total_nse, total_sap, epf, total_liquid)
        prev_values = get_previous_day_values()
        historical_values = get_historical_values()

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
        'historical_values': historical_values
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
    
    with sqlite3.connect('investments.db') as conn:
        c = conn.cursor()
        c.execute("SELECT units FROM investments WHERE instrument = ?", (instrument,))
        existing = c.fetchone()
        
        if existing:
            new_units = existing[0] + units
            c.execute("UPDATE investments SET units = ?, current_price = ? WHERE instrument = ?",
                     (new_units, initial_price, instrument))
        else:
            c.execute("INSERT INTO investments (instrument, units, initial_price, current_price, currency, purchase_date) VALUES (?, ?, ?, ?, ?, ?)",
                     (instrument, units, initial_price, initial_price, currency, datetime.now(IST).strftime('%Y-%m-%d')))
        conn.commit()
    return jsonify({'status': 'success'})

@app.route('/delete_investment/<int:id>', methods=['POST'])
def delete_investment(id):
    with sqlite3.connect('investments.db') as conn:
        c = conn.cursor()
        c.execute("DELETE FROM investments WHERE id = ?", (id,))
        conn.commit()
    return jsonify({'status': 'success'})

@app.route('/update_accounts', methods=['POST'])
def update_accounts():
    data = request.form
    epf = float(data['epf']) if data['epf'] else 0
    bank_balance = float(data['bank_balance']) if data['bank_balance'] else 0
    
    with sqlite3.connect('investments.db') as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO accounts (id, epf, bank_balance) VALUES (1, ?, ?)",
                 (epf, bank_balance))
        conn.commit()
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
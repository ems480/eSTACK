from flask import Flask, request, jsonify, g
import os, sqlite3, json, uuid, logging, requests
from datetime import datetime, timedelta

# --------------------
# CONFIG
# --------------------
API_MODE = os.getenv("API_MODE", "sandbox")
SANDBOX_API_TOKEN = os.getenv("SANDBOX_API_TOKEN")
LIVE_API_TOKEN = os.getenv("LIVE_API_TOKEN")

API_TOKEN = LIVE_API_TOKEN if API_MODE == "live" else SANDBOX_API_TOKEN
PAWAPAY_DEPOSIT_URL = "https://api.pawapay.io/deposits" if API_MODE=="live" else "https://api.sandbox.pawapay.io/deposits"
PAWAPAY_PAYOUT_URL = "https://api.pawapay.io/v2/payouts" if API_MODE=="live" else "https://api.sandbox.pawapay.io/v2/payouts"

DATABASE = os.path.join(os.path.dirname(__file__), "transact.db")
INTEREST_RATE = float(os.getenv("INTEREST_RATE", 0.1))
INTEREST_DAYS = int(os.getenv("INTEREST_DAYS", 30))

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------
# DATABASE
# --------------------
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        init_db(db)
    return db

def init_db(db):
    cur = db.cursor()
    # Transactions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            depositId TEXT UNIQUE,
            status TEXT,
            amount REAL,
            currency TEXT,
            phoneNumber TEXT,
            provider TEXT,
            providerTransactionId TEXT,
            failureCode TEXT,
            failureMessage TEXT,
            metadata TEXT,
            received_at TEXT
        )
    """)
    # Investments table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investmentId TEXT UNIQUE,
            user_id TEXT,
            depositId TEXT,
            amount REAL,
            status TEXT,
            created_at TEXT,
            confirmed_at TEXT,
            return_date TEXT,
            interest REAL,
            balance REAL
        )
    """)
    # Loans table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loanId TEXT UNIQUE,
            user_id TEXT,
            amount REAL,
            balance REAL,
            status TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    # Task queue table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT,
            payload TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TEXT,
            updated_at TEXT
        )
    """)
    db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db:
        db.close()

# --------------------
# UTILS
# --------------------
def add_task(db, task_type, payload):
    cur = db.cursor()
    cur.execute("""
        INSERT INTO tasks (task_type, payload, status, created_at)
        VALUES (?, ?, 'PENDING', ?)
    """, (task_type, json.dumps(payload), datetime.utcnow().isoformat()))
    db.commit()

# --------------------
# ROUTES
# --------------------
@app.route("/")
def home():
    return "eStack Investment & Loan Server ✅"

# ---- INVESTMENT ----
@app.route("/api/investments/initiate", methods=["POST"])
def initiate_investment():
    data = request.json or {}
    user_id = data.get("user_id")
    amount = data.get("amount")
    phone = data.get("phone")
    correspondent = data.get("correspondent", "MTN_MOMO_ZMB")
    currency = data.get("currency", "ZMW")

    if not user_id or not amount or not phone:
        return jsonify({"error": "Missing user_id, amount or phone"}), 400

    deposit_id = str(uuid.uuid4())
    investment_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()

    payload = {
        "depositId": deposit_id,
        "amount": str(amount),
        "currency": currency,
        "correspondent": correspondent,
        "payer": {"type": "MSISDN", "address": {"value": phone}},
        "customerTimestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "statementDescription": "eStack Investment",
        "metadata": [
            {"fieldName": "investmentId", "fieldValue": investment_id},
            {"fieldName": "userId", "fieldValue": user_id}
        ]
    }

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO transactions
        (depositId, status, amount, currency, phoneNumber, provider, providerTransactionId, metadata, received_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (deposit_id, "PENDING", amount, currency, phone, correspondent, None, json.dumps(payload["metadata"]), created_at))
    db.commit()

    cur.execute("""
        INSERT INTO investments (investmentId, user_id, depositId, amount, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (investment_id, user_id, deposit_id, amount, "PENDING_PAYMENT", created_at))
    db.commit()

    # Add to task queue to call deposit API
    add_task(db, "investment_deposit", payload)

    return jsonify({"investment_id": investment_id, "deposit_id": deposit_id, "status": "PENDING_PAYMENT"}), 200

@app.route("/api/investments/<user_id>", methods=["GET"])
def get_investments(user_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT investmentId, depositId, amount, status, created_at, confirmed_at,
               return_date, interest, balance
        FROM investments WHERE user_id=? ORDER BY created_at DESC
    """, (user_id,))
    rows = cur.fetchall()
    return jsonify({"investments": [dict(r) for r in rows]}), 200

# ---- LOAN ----
@app.route("/api/loans/request", methods=["POST"])
def request_loan():
    data = request.json or {}
    user_id = data.get("user_id")
    amount = data.get("amount")
    phone = data.get("phone")

    if not user_id or not amount or not phone:
        return jsonify({"error": "Missing user_id, amount or phone"}), 400

    loan_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        INSERT INTO loans (loanId, user_id, amount, balance, status, created_at)
        VALUES (?, ?, ?, ?, 'PENDING', ?)
    """, (loan_id, user_id, amount, amount, created_at))
    db.commit()

    payload = {
        "payoutId": str(uuid.uuid4()),
        "recipient": {"type": "MMO", "accountDetails": {"phoneNumber": phone, "provider": "MTN_MOMO_ZMB"}},
        "amount": str(amount),
        "currency": "ZMW",
        "customerMessage": f"Loan {loan_id}",
        "metadata": [{"loanId": loan_id, "userId": user_id}]
    }
    add_task(db, "loan_disbursement", payload)

    return jsonify({"loan_id": loan_id, "status": "PENDING"}), 200

@app.route("/api/loans/<user_id>", methods=["GET"])
def get_loans(user_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT loanId, amount, balance, status, created_at, updated_at
        FROM loans WHERE user_id=? ORDER BY created_at DESC
    """, (user_id,))
    rows = cur.fetchall()
    return jsonify({"loans": [dict(r) for r in rows]}), 200

# --------------------
# CALLBACK
# --------------------
@app.route("/callback/deposit", methods=["POST"])
def deposit_callback():
    data = request.json or {}
    deposit_id = data.get("depositId")
    status = str(data.get("status", "")).upper()

    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE transactions SET status=?, received_at=? WHERE depositId=?", (status, datetime.utcnow().isoformat(), deposit_id))
    db.commit()

    cur.execute("SELECT investmentId, amount FROM investments WHERE depositId=?", (deposit_id,))
    row = cur.fetchone()
    if row and status in ["COMPLETED", "SUCCESS", "PAYMENT_COMPLETED"]:
        investment_id, inv_amount = row
        confirmed_at = datetime.utcnow().isoformat()
        interest = round(float(inv_amount)*INTEREST_RATE,2)
        return_date = (datetime.utcnow() + timedelta(days=INTEREST_DAYS)).isoformat()
        balance = float(inv_amount) + interest
        cur.execute("""
            UPDATE investments SET status='CONFIRMED', confirmed_at=?, return_date=?, interest=?, balance=?
            WHERE investmentId=?
        """, (confirmed_at, return_date, interest, balance, investment_id))
        db.commit()
    return jsonify({"ok": True})

# --------------------
# MAIN
# --------------------
if __name__ == "__main__":
    db = sqlite3.connect(DATABASE)
    init_db(db)
    db.close()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

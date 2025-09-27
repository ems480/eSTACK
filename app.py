# from dotenv import load_dotenv
# load_dotenv()

# from flask import Flask, request, jsonify, g
# import os, logging, sqlite3, json, uuid
# from datetime import datetime, timedelta
# import requests

# # --------------------
# # CONFIG
# # --------------------
# API_MODE = os.getenv("API_MODE", "sandbox")
# SANDBOX_API_TOKEN = os.getenv("SANDBOX_API_TOKEN")
# LIVE_API_TOKEN = os.getenv("LIVE_API_TOKEN")

# if API_MODE == "live":
#     API_TOKEN = LIVE_API_TOKEN
#     PAWAPAY_URL = "https://api.pawapay.io/deposits"
#     PAWAPAY_PAYOUT_URL = "https://api.pawapay.io/v2/payouts"
# else:
#     API_TOKEN = SANDBOX_API_TOKEN
#     PAWAPAY_URL = "https://api.sandbox.pawapay.io/deposits"
#     PAWAPAY_PAYOUT_URL = "https://api.sandbox.pawapay.io/v2/payouts"

# DATABASE = os.path.join(os.path.dirname(__file__), "transact.db")

# INTEREST_RATE = float(os.getenv("INTEREST_RATE", "0.10"))
# INTEREST_DAYS = int(os.getenv("INTEREST_DAYS", "30"))

# app = Flask(__name__)
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


# # --------------------
# # DATABASE
# # --------------------
# def init_db():
#     db = sqlite3.connect(DATABASE)
#     cur = db.cursor()

#     # Transactions table
#     cur.execute("""
#     CREATE TABLE IF NOT EXISTS transactions (
#         id INTEGER PRIMARY KEY AUTOINCREMENT,
#         depositId TEXT UNIQUE,
#         status TEXT,
#         amount REAL,
#         currency TEXT,
#         phoneNumber TEXT,
#         provider TEXT,
#         providerTransactionId TEXT,
#         failureCode TEXT,
#         failureMessage TEXT,
#         metadata TEXT,
#         received_at TEXT
#     )
#     """)

#     # Investments table
#     cur.execute("""
#     CREATE TABLE IF NOT EXISTS investments (
#         id INTEGER PRIMARY KEY AUTOINCREMENT,
#         investmentId TEXT UNIQUE,
#         user_id TEXT,
#         depositId TEXT,
#         amount REAL,
#         status TEXT,
#         created_at TEXT,
#         confirmed_at TEXT,
#         return_date TEXT,
#         interest REAL,
#         balance REAL
#     )
#     """)

#     # Loans table
#     cur.execute("""
#     CREATE TABLE IF NOT EXISTS loans (
#         id INTEGER PRIMARY KEY AUTOINCREMENT,
#         loanId TEXT UNIQUE,
#         user_id TEXT,
#         amount REAL,
#         balance REAL,
#         status TEXT,
#         created_at TEXT
#     )
#     """)

#     db.commit()
#     db.close()


# def get_db():
#     db = getattr(g, "_database", None)
#     if db is None:
#         db = g._database = sqlite3.connect(DATABASE)
#         db.row_factory = sqlite3.Row
#     return db


# @app.teardown_appcontext
# def close_connection(exception):
#     db = getattr(g, "_database", None)
#     if db is not None:
#         db.close()


# # --------------------
# # ROUTES
# # --------------------
# @app.route("/")
# def home():
#     return "eStack Investment & Loan Server ✅"


# # --------------------
# # INVESTMENT ENDPOINTS
# # --------------------
# @app.route("/api/investments/initiate", methods=["POST"])
# def initiate_investment():
#     try:
#         data = request.json or {}
#         user_id = data.get("user_id")
#         amount = data.get("amount")
#         phone = data.get("phone")
#         correspondent = data.get("correspondent", "MTN_MOMO_ZMB")
#         currency = data.get("currency", "ZMW")

#         if not user_id or not amount or not phone:
#             return jsonify({"error": "Missing user_id, amount or phone"}), 400

#         deposit_id = str(uuid.uuid4())
#         investment_id = str(uuid.uuid4())
#         created_at = datetime.utcnow().isoformat()
#         customer_timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

#         payload = {
#             "depositId": deposit_id,
#             "amount": str(amount),
#             "currency": currency,
#             "correspondent": correspondent,
#             "payer": {"type": "MSISDN", "address": {"value": phone}},
#             "customerTimestamp": customer_timestamp,
#             "statementDescription": "eStack Investment",
#             "metadata": [
#                 {"fieldName": "investmentId", "fieldValue": investment_id},
#                 {"fieldName": "userId", "fieldValue": user_id}
#             ]
#         }

#         headers = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

#         try:
#             resp = requests.post(PAWAPAY_URL, json=payload, headers=headers, timeout=15)
#             pay_result = resp.json() if resp.content else {"status": "PENDING"}
#         except Exception as e:
#             logger.warning("PawaPay request failed: %s", e)
#             pay_result = {"status": "PENDING", "error": str(e)}

#         # Save to transactions
#         db = get_db()
#         cur = db.cursor()
#         cur.execute("""
#             INSERT OR REPLACE INTO transactions
#             (depositId, status, amount, currency, phoneNumber, provider,
#              providerTransactionId, failureCode, failureMessage, metadata, received_at)
#             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
#         """, (
#             deposit_id,
#             pay_result.get("status", "PENDING"),
#             float(amount),
#             currency,
#             phone,
#             correspondent,
#             pay_result.get("providerTransactionId"),
#             None, None,
#             json.dumps(payload["metadata"]),
#             datetime.utcnow().isoformat()
#         ))
#         db.commit()

#         # Save to investments
#         cur.execute("""
#             INSERT INTO investments (investmentId, user_id, depositId, amount, status, created_at)
#             VALUES (?, ?, ?, ?, ?, ?)
#         """, (investment_id, user_id, deposit_id, float(amount), "PENDING_PAYMENT", created_at))
#         db.commit()

#         return jsonify({
#             "investment_id": investment_id,
#             "deposit_id": deposit_id,
#             "status": "PENDING_PAYMENT",
#             "amount": amount,
#             "payment_response": pay_result
#         }), 200

#     except Exception as e:
#         logger.exception("Error in initiate_investment")
#         return jsonify({"error": "Internal server error", "detail": str(e)}), 500


# @app.route("/callback/deposit", methods=["POST"])
# def deposit_callback():
#     try:
#         data = request.get_json()
#         if not data:
#             return jsonify({"error": "No JSON"}), 400

#         deposit_id = data.get("depositId")
#         status = str(data.get("status", "")).upper()
#         amount = data.get("amount")

#         db = get_db()
#         cur = db.cursor()

#         cur.execute("UPDATE transactions SET status=?, received_at=? WHERE depositId=?",
#                     (status, datetime.utcnow().isoformat(), deposit_id))
#         db.commit()

#         cur.execute("SELECT investmentId, amount FROM investments WHERE depositId=?", (deposit_id,))
#         row = cur.fetchone()
#         if row:
#             investment_id, inv_amount = row
#             if status in ["COMPLETED", "SUCCESS", "PAYMENT_COMPLETED"]:
#                 confirmed_at = datetime.utcnow().isoformat()
#                 interest = round(float(inv_amount) * INTEREST_RATE, 2)
#                 return_date = (datetime.utcnow() + timedelta(days=INTEREST_DAYS)).isoformat()
#                 balance = float(inv_amount) + interest
#                 cur.execute("""
#                     UPDATE investments SET status=?, confirmed_at=?, return_date=?, interest=?, balance=?
#                     WHERE investmentId=?
#                 """, ("CONFIRMED", confirmed_at, return_date, interest, balance, investment_id))
#                 db.commit()
#                 logger.info("Investment %s confirmed", investment_id)
#             else:
#                 cur.execute("UPDATE investments SET status=? WHERE investmentId=?", (status, investment_id))
#                 db.commit()
#                 logger.info("Investment %s updated to %s", investment_id, status)

#         return jsonify({"ok": True}), 200

#     except Exception as e:
#         logger.exception("Error in deposit_callback")
#         return jsonify({"error": "Internal server error"}), 500


# @app.route("/api/investments/<user_id>", methods=["GET"])
# def get_investments(user_id):
#     db = get_db()
#     cur = db.cursor()
#     cur.execute("""
#         SELECT investmentId, depositId, amount, status, created_at, confirmed_at,
#                return_date, interest, balance
#         FROM investments WHERE user_id=? ORDER BY created_at DESC
#     """, (user_id,))
#     rows = cur.fetchall()
#     return jsonify({"investments": [dict(r) for r in rows]}), 200


# # --------------------
# # LOAN ENDPOINTS
# # --------------------
# @app.route("/api/loans/request", methods=["POST"])
# def request_loan():
#     try:
#         data = request.json or {}
#         user_id = data.get("user_id")
#         amount = data.get("amount")
#         if not user_id or not amount:
#             return jsonify({"error": "Missing user_id or amount"}), 400

#         loan_id = str(uuid.uuid4())
#         created_at = datetime.utcnow().isoformat()

#         db = get_db()
#         cur = db.cursor()
#         cur.execute("""
#             INSERT INTO loans (loanId, user_id, amount, balance, status, created_at)
#             VALUES (?, ?, ?, ?, ?, ?)
#         """, (loan_id, user_id, float(amount), float(amount), "PENDING", created_at))
#         db.commit()

#         return jsonify({"loan_id": loan_id, "status": "PENDING", "amount": amount}), 200

#     except Exception as e:
#         logger.exception("Error requesting loan")
#         return jsonify({"error": str(e)}), 500


# @app.route("/api/loans/<user_id>", methods=["GET"])
# def get_loans(user_id):
#     db = get_db()
#     cur = db.cursor()
#     cur.execute("SELECT loanId, amount, balance, status, created_at FROM loans WHERE user_id=? ORDER BY created_at DESC", (user_id,))
#     rows = cur.fetchall()
#     return jsonify({"loans": [dict(r) for r in rows]}), 200


# @app.route("/api/loans/<loan_id>/repay", methods=["POST"])
# def repay_loan(loan_id):
#     try:
#         data = request.json or {}
#         amount = float(data.get("amount", 0))
#         phone = data.get("phone")
#         if not amount or not phone:
#             return jsonify({"error": "Missing amount or phone"}), 400

#         db = get_db()
#         cur = db.cursor()
#         cur.execute("SELECT user_id, balance, status FROM loans WHERE loanId=?", (loan_id,))
#         row = cur.fetchone()
#         if not row:
#             return jsonify({"error": "Loan not found"}), 404

#         user_id, balance, status = row
#         if status not in ["PENDING", "ACTIVE"]:
#             return jsonify({"error": f"Loan status {status} cannot be repaid"}), 400

#         # Create payout to server (simulate repayment)
#         payout_id = str(uuid.uuid4())
#         payload = {
#             "payoutId": payout_id,
#             "recipient": {
#                 "type": "MMO",
#                 "accountDetails": {
#                     "phoneNumber": phone,
#                     "provider": "MTN_MOMO_ZMB"
#                 }
#             },
#             "amount": str(amount),
#             "currency": "ZMW",
#             "customerMessage": "Loan repayment",
#             "metadata": [{"loanId": loan_id}]
#         }
#         headers = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

#         try:
#             resp = requests.post(PAWAPAY_PAYOUT_URL, json=payload, headers=headers, timeout=15)
#             result = resp.json() if resp.content else {"status": "PENDING"}
#         except Exception as e:
#             logger.warning("Payout request failed: %s", e)
#             result = {"status": "PENDING", "error": str(e)}

#         # Update loan balance
#         new_balance = max(float(balance) - float(amount), 0)
#         new_status = "PAID" if new_balance <= 0 else "ACTIVE"
#         cur.execute("UPDATE loans SET balance=?, status=? WHERE loanId=?", (new_balance, new_status, loan_id))
#         db.commit()

#         return jsonify({
#             "loan_id": loan_id,
#             "status": new_status,
#             "balance": new_balance,
#             "payout_response": result
#         }), 200

#     except Exception as e:
#         logger.exception("Error repaying loan")
#         return jsonify({"error": str(e)}), 500


# # --------------------
# # MAIN
# # --------------------
# if __name__ == "__main__":
#     init_db()
#     port = int(os.environ.get("PORT", 5000))
#     app.run(host="0.0.0.0", port=port)
import uuid
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)
DB_NAME = "transact.db"


# -----------------------------
# DB INITIALIZATION
# -----------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # Transactions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            investmentId TEXT,
            amount REAL,
            status TEXT,
            phone TEXT,
            provider TEXT,
            providerTxn TEXT,
            failureReason TEXT,
            failureMessage TEXT,
            metadata TEXT,
            created_at TEXT
        )
    """)

    # Loans table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            loanId TEXT PRIMARY KEY,
            user_id TEXT,
            amount REAL,
            balance REAL,
            status TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


# call init_db() when server starts
init_db()


# -----------------------------
# INVESTMENTS ENDPOINTS
# -----------------------------
@app.route("/api/investments/initiate", methods=["POST"])
def initiate_investment():
    data = request.json
    user_id = data.get("user_id")
    amount = data.get("amount")
    phone = data.get("phone")
    provider = data.get("correspondent")
    currency = data.get("currency")

    if not user_id or not amount:
        return jsonify({"error": "Missing fields"}), 400

    deposit_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO transactions
        (id, user_id, investmentId, amount, status, phone, provider, providerTxn,
         failureReason, failureMessage, metadata, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        deposit_id, user_id, str(uuid.uuid4()), float(amount), "PENDING",
        phone, provider, None, None, None, str(data), created_at
    ))
    conn.commit()
    conn.close()

    return jsonify({"deposit_id": deposit_id, "status": "PENDING"})


@app.route("/transactions/<deposit_id>", methods=["GET"])
def get_transaction(deposit_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT status FROM transactions WHERE id=?", (deposit_id,))
    row = cur.fetchone()
    conn.close()

    if row:
        return jsonify({"deposit_id": deposit_id, "status": row[0]})
    return jsonify({"error": "Transaction not found"}), 404


@app.route("/api/investments/<user_id>", methods=["GET"])
def get_investments(user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT amount, status, created_at FROM transactions WHERE user_id=?", (user_id,))
    rows = cur.fetchall()
    conn.close()

    investments = []
    for r in rows:
        investments.append({
            "amount": r[0],
            "status": r[1],
            "balance": r[0],  # later update with real balance calc
            "return_date": r[2]
        })

    return jsonify({"investments": investments})


# -----------------------------
# LOANS ENDPOINTS
# -----------------------------
@app.route("/api/loans/request", methods=["POST"])
def request_loan():
    data = request.json
    user_id = data.get("user_id")
    amount = data.get("amount")

    if not user_id or not amount:
        return jsonify({"error": "Missing fields"}), 400

    loan_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO loans (loanId, user_id, amount, balance, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (loan_id, user_id, float(amount), float(amount), "PENDING", created_at))
    conn.commit()
    conn.close()

    return jsonify({"loan_id": loan_id, "status": "PENDING"})


@app.route("/api/loans/<user_id>", methods=["GET"])
def get_loans(user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT loanId, amount, balance, status, created_at FROM loans WHERE user_id=?", (user_id,))
    rows = cur.fetchall()
    conn.close()

    loans = []
    for r in rows:
        loans.append({
            "loanId": r[0],
            "amount": r[1],
            "balance": r[2],
            "status": r[3],
            "created_at": r[4]
        })

    return jsonify({"loans": loans})


@app.route("/api/loans/repay", methods=["POST"])
def repay_loan():
    data = request.json
    loan_id = data.get("loan_id")
    amount = data.get("amount")

    if not loan_id or not amount:
        return jsonify({"error": "Missing fields"}), 400

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT balance FROM loans WHERE loanId=?", (loan_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({"error": "Loan not found"}), 404

    balance = row[0] - float(amount)
    status = "COMPLETED" if balance <= 0 else "ACTIVE"

    cur.execute("UPDATE loans SET balance=?, status=? WHERE loanId=?", (balance, status, loan_id))
    conn.commit()
    conn.close()

    return jsonify({"loan_id": loan_id, "new_balance": balance, "status": status})


# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

# from flask import Flask, request, jsonify, g
# import sqlite3, os, logging
# from datetime import datetime, timedelta
# from uuid import uuid4

# # --------------------
# # CONFIG
# # --------------------
# DATABASE = os.path.join(os.path.dirname(__file__), "transact.db")

# INTEREST_RATE = 0.10  # 10% interest for investments
# INTEREST_DAYS = 30    # 30-day investment term

# app = Flask(__name__)
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


# # --------------------
# # DATABASE
# # --------------------
# def get_db():
#     db = getattr(g, "_database", None)
#     if db is None:
#         db = g._database = sqlite3.connect(DATABASE)
#         db.row_factory = sqlite3.Row
#     return db


# def init_db():
#     db = get_db()
#     cur = db.cursor()

#     # Transactions
#     cur.execute("""
#     CREATE TABLE IF NOT EXISTS transactions (
#         id INTEGER PRIMARY KEY AUTOINCREMENT,
#         depositId TEXT UNIQUE,
#         userId TEXT,
#         investmentId TEXT,
#         amount REAL,
#         status TEXT,
#         createdAt TEXT
#     )
#     """)

#     # Investments
#     cur.execute("""
#     CREATE TABLE IF NOT EXISTS investments (
#         id INTEGER PRIMARY KEY AUTOINCREMENT,
#         investmentId TEXT UNIQUE,
#         userId TEXT,
#         amount REAL,
#         status TEXT,
#         createdAt TEXT
#     )
#     """)

#     # Loans
#     cur.execute("""
#     CREATE TABLE IF NOT EXISTS loans (
#         id INTEGER PRIMARY KEY AUTOINCREMENT,
#         loanId TEXT UNIQUE,
#         userId TEXT,
#         amount REAL,
#         status TEXT,
#         interestRate REAL,
#         createdAt TEXT,
#         dueDate TEXT
#     )
#     """)

#     # Loan-Investors bridge
#     cur.execute("""
#     CREATE TABLE IF NOT EXISTS loan_investors (
#         id INTEGER PRIMARY KEY AUTOINCREMENT,
#         loanId TEXT,
#         investorId TEXT,
#         amount REAL,
#         status TEXT
#     )
#     """)

#     # Repayments
#     cur.execute("""
#     CREATE TABLE IF NOT EXISTS repayments (
#         id INTEGER PRIMARY KEY AUTOINCREMENT,
#         loanId TEXT,
#         amount REAL,
#         paidAt TEXT
#     )
#     """)

#     # Notifications
#     cur.execute("""
#     CREATE TABLE IF NOT EXISTS notifications (
#         id INTEGER PRIMARY KEY AUTOINCREMENT,
#         userId TEXT,
#         message TEXT,
#         createdAt TEXT,
#         read INTEGER DEFAULT 0
#     )
#     """)

#     db.commit()
#     db.close()


# @app.teardown_appcontext
# def close_connection(exception):
#     db = getattr(g, "_database", None)
#     if db:
#         db.close()


# init_db()


# # --------------------
# # ROUTES
# # --------------------

# # Investment initiation
# @app.route("/api/investments/initiate", methods=["POST"])
# def initiate_investment():
#     data = request.json or {}
#     userId = data.get("userId")
#     amount = data.get("amount")

#     if not userId or not amount:
#         return jsonify({"error": "Missing userId or amount"}), 400

#     investmentId = str(uuid4())
#     createdAt = datetime.utcnow().isoformat()

#     db = get_db()
#     cur = db.cursor()
#     cur.execute("""
#         INSERT INTO investments (investmentId, userId, amount, status, createdAt)
#         VALUES (?, ?, ?, ?, ?)
#     """, (investmentId, userId, float(amount), "ACTIVE", createdAt))
#     db.commit()

#     return jsonify({"investmentId": investmentId, "status": "ACTIVE"}), 200


# # Loan request by borrower
# @app.route("/api/loans/request", methods=["POST"])
# def request_loan():
#     data = request.json or {}
#     userId = data.get("userId")
#     amount = data.get("amount")
#     interestRate = data.get("interestRate", 10.0)

#     if not userId or not amount:
#         return jsonify({"error": "Missing userId or amount"}), 400

#     loanId = str(uuid4())
#     createdAt = datetime.utcnow()
#     dueDate = createdAt + timedelta(days=30)

#     db = get_db()
#     cur = db.cursor()
#     cur.execute("""
#         INSERT INTO loans (loanId, userId, amount, status, interestRate, createdAt, dueDate)
#         VALUES (?, ?, ?, ?, ?, ?, ?)
#     """, (loanId, userId, float(amount), "PENDING", interestRate, createdAt.isoformat(), dueDate.isoformat()))
#     db.commit()

#     return jsonify({"loanId": loanId, "status": "PENDING"}), 200


# # Fund a loan as an investor
# @app.route("/api/loans/<loanId>/fund", methods=["POST"])
# def fund_loan(loanId):
#     data = request.json or {}
#     investorId = data.get("investorId")
#     amount = data.get("amount")

#     if not investorId or not amount:
#         return jsonify({"error": "Missing investorId or amount"}), 400

#     db = get_db()
#     cur = db.cursor()
#     cur.execute("SELECT * FROM loans WHERE loanId=?", (loanId,))
#     loan = cur.fetchone()
#     if not loan:
#         return jsonify({"error": "Loan not found"}), 404

#     # Record funding
#     cur.execute("""
#         INSERT INTO loan_investors (loanId, investorId, amount, status)
#         VALUES (?, ?, ?, ?)
#     """, (loanId, investorId, float(amount), "FUNDED"))

#     # Update loan status to ACTIVE
#     cur.execute("UPDATE loans SET status=? WHERE loanId=?", ("ACTIVE", loanId))

#     # Notify borrower
#     cur.execute("""
#         INSERT INTO notifications (userId, message, createdAt)
#         VALUES (?, ?, ?)
#     """, (loan["userId"], f"Your loan {loanId} has been funded!", datetime.utcnow().isoformat()))

#     db.commit()
#     return jsonify({"loanId": loanId, "status": "FUNDED"}), 200


# # Repay a loan
# @app.route("/api/loans/<loanId>/repay", methods=["POST"])
# def repay_loan(loanId):
#     data = request.json or {}
#     amount = data.get("amount")
#     if not amount:
#         return jsonify({"error": "Missing repayment amount"}), 400

#     paidAt = datetime.utcnow().isoformat()
#     db = get_db()
#     cur = db.cursor()

#     cur.execute("SELECT * FROM loans WHERE loanId=?", (loanId,))
#     loan = cur.fetchone()
#     if not loan:
#         return jsonify({"error": "Loan not found"}), 404

#     # Record repayment
#     cur.execute("""
#         INSERT INTO repayments (loanId, amount, paidAt)
#         VALUES (?, ?, ?)
#     """, (loanId, float(amount), paidAt))

#     # Notify investors
#     cur.execute("SELECT * FROM loan_investors WHERE loanId=?", (loanId,))
#     investors = cur.fetchall()
#     for inv in investors:
#         cur.execute("""
#             INSERT INTO notifications (userId, message, createdAt)
#             VALUES (?, ?, ?)
#         """, (inv["investorId"], f"You received repayment for loan {loanId}: {amount} ZMW", paidAt))

#     # Update loan status if fully repaid
#     cur.execute("UPDATE loans SET status=? WHERE loanId=?", ("REPAID", loanId))

#     db.commit()
#     return jsonify({"loanId": loanId, "status": "REPAID"}), 200


# # Get loans for a specific investor
# @app.route("/api/investor/<userId>/loans", methods=["GET"])
# def investor_loans(userId):
#     db = get_db()
#     cur = db.cursor()
#     cur.execute("""
#         SELECT l.loanId, l.amount AS loanAmount, l.status, li.amount AS investedAmount
#         FROM loans l
#         JOIN loan_investors li ON l.loanId = li.loanId
#         WHERE li.investorId=?
#     """, (userId,))
#     rows = cur.fetchall()
#     return jsonify([dict(r) for r in rows]), 200


# # Get notifications for a user
# @app.route("/api/notifications/<userId>", methods=["GET"])
# def get_notifications(userId):
#     db = get_db()
#     cur = db.cursor()
#     cur.execute("""
#         SELECT * FROM notifications WHERE userId=? ORDER BY createdAt DESC
#     """, (userId,))
#     rows = cur.fetchall()
#     return jsonify([dict(r) for r in rows]), 200


# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, g
import os, logging, sqlite3, json, requests, uuid
from datetime import datetime, timedelta

# --------------------
# CONFIG
# --------------------
API_MODE = os.getenv("API_MODE", "sandbox")
SANDBOX_API_TOKEN = os.getenv("SANDBOX_API_TOKEN")
LIVE_API_TOKEN = os.getenv("LIVE_API_TOKEN")

if API_MODE == "live":
    API_TOKEN = LIVE_API_TOKEN
    PAWAPAY_DEPOSIT_URL = "https://api.pawapay.io/deposits"
    PAWAPAY_PAYOUT_URL = "https://api.pawapay.io/v2/payouts"
else:
    API_TOKEN = SANDBOX_API_TOKEN
    PAWAPAY_DEPOSIT_URL = "https://api.sandbox.pawapay.io/deposits"
    PAWAPAY_PAYOUT_URL = "https://api.sandbox.pawapay.io/v2/payouts"

DATABASE = os.path.join(os.path.dirname(__file__), "transact.db")

INTEREST_RATE = float(os.getenv("INTEREST_RATE", "0.10"))  # 10%
INTEREST_DAYS = int(os.getenv("INTEREST_DAYS", "30"))      # 30 days

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------
# DATABASE
# --------------------
def init_db():
    db = sqlite3.connect(DATABASE)
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
        status TEXT,
        created_at TEXT,
        disbursed_at TEXT,
        repaid_at TEXT,
        interest REAL,
        balance REAL,
        payout_metadata TEXT
    )
    """)
    
    db.commit()
    db.close()

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

# --------------------
# ROUTES
# --------------------
@app.route("/")
def home():
    return "eStack Investment Server ✅"

# ---- INITIATE INVESTMENT ----
@app.route("/api/investments/initiate", methods=["POST"])
def initiate_investment():
    try:
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
        customer_timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        payload = {
            "depositId": deposit_id,
            "amount": str(amount),
            "currency": currency,
            "correspondent": correspondent,
            "payer": {"type": "MSISDN", "address": {"value": phone}},
            "customerTimestamp": customer_timestamp,
            "statementDescription": "eStack Investment",
            "metadata": [
                {"fieldName": "investmentId", "fieldValue": investment_id},
                {"fieldName": "userId", "fieldValue": user_id}
            ]
        }
        headers = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

        try:
            resp = requests.post(PAWAPAY_DEPOSIT_URL, json=payload, headers=headers, timeout=15)
            pay_result = resp.json() if resp.content else {"status": "PENDING"}
        except Exception as e:
            logger.warning("PawaPay request failed: %s", e)
            pay_result = {"status": "PENDING", "error": str(e)}

        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO transactions
            (depositId, status, amount, currency, phoneNumber, provider,
             providerTransactionId, failureCode, failureMessage, metadata, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            deposit_id,
            pay_result.get("status", "PENDING"),
            float(amount),
            currency,
            phone,
            correspondent,
            pay_result.get("providerTransactionId"),
            None, None,
            json.dumps(payload["metadata"]),
            datetime.utcnow().isoformat()
        ))
        db.commit()

        cur.execute("""
            INSERT INTO investments (investmentId, user_id, depositId, amount, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (investment_id, user_id, deposit_id, float(amount), "PENDING_PAYMENT", created_at))
        db.commit()

        return jsonify({
            "investment_id": investment_id,
            "deposit_id": deposit_id,
            "status": "PENDING_PAYMENT",
            "amount": amount,
            "payment_response": pay_result
        }), 200
    except Exception as e:
        logger.exception("Error in initiate_investment")
        return jsonify({"error": "Internal server error", "detail": str(e)}), 500

# ---- REQUEST LOAN ----
@app.route("/api/loans/request", methods=["POST"])
def request_loan():
    try:
        data = request.json or {}
        user_id = data.get("user_id")
        amount = data.get("amount")
        phone = data.get("phone")
        provider = data.get("provider", "MTN_MOMO_ZMB")
        currency = data.get("currency", "ZMW")

        if not user_id or not amount or not phone:
            return jsonify({"error": "Missing user_id, amount or phone"}), 400

        loan_id = str(uuid.uuid4())
        payout_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()

        payload = {
            "payoutId": payout_id,
            "recipient": {
                "type": "MMO",
                "accountDetails": {
                    "phoneNumber": phone,
                    "provider": provider
                }
            },
            "customerMessage": f"Loan disbursement: {loan_id}",
            "amount": str(amount),
            "currency": currency,
            "metadata": [
                {"loanId": loan_id},
                {"userId": user_id}
            ]
        }

        headers = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}
        try:
            resp = requests.post(PAWAPAY_PAYOUT_URL, json=payload, headers=headers, timeout=15)
            payout_result = resp.json() if resp.content else {"status": "PENDING"}
        except Exception as e:
            logger.warning("PawaPay loan payout failed: %s", e)
            payout_result = {"status": "PENDING", "error": str(e)}

        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO loans (loanId, user_id, amount, status, created_at, balance, payout_metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (loan_id, user_id, float(amount), payout_result.get("status", "PENDING"), created_at, float(amount), json.dumps(payout_result)))
        db.commit()

        return jsonify({"loan_id": loan_id, "status": payout_result.get("status", "PENDING"), "payout_response": payout_result}), 200

    except Exception as e:
        logger.exception("Error in request_loan")
        return jsonify({"error": "Internal server error", "detail": str(e)}), 500

# ---- REPAY LOAN ----
@app.route("/api/loans/<loan_id>/repay", methods=["POST"])
def repay_loan(loan_id):
    try:
        data = request.json or {}
        amount = data.get("amount")
        if not amount:
            return jsonify({"error": "Missing repayment amount"}), 400

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT balance, status FROM loans WHERE loanId=?", (loan_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Loan not found"}), 404

        balance, status = row
        new_balance = float(balance) - float(amount)
        new_status = "PAID" if new_balance <= 0 else "PARTIALLY_PAID"
        repaid_at = datetime.utcnow().isoformat()

        cur.execute("UPDATE loans SET balance=?, status=?, repaid_at=? WHERE loanId=?", (new_balance, new_status, repaid_at, loan_id))
        db.commit()

        # Here you could trigger payout to investors if needed
        return jsonify({"loan_id": loan_id, "new_balance": new_balance, "status": new_status}), 200
    except Exception as e:
        logger.exception("Error in repay_loan")
        return jsonify({"error": "Internal server error", "detail": str(e)}), 500

# ---- GET LOANS ----
@app.route("/api/loans/<user_id>", methods=["GET"])
def get_loans(user_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT loanId, amount, balance, status, created_at, disbursed_at, repaid_at FROM loans WHERE user_id=? ORDER BY created_at DESC", (user_id,))
    rows = cur.fetchall()
    return jsonify({"loans": [dict(r) for r in rows]}), 200

# ---- MAIN ----
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

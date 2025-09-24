from flask import Flask, request, jsonify, g
import os, sqlite3, json, uuid, logging, requests
from datetime import datetime, timedelta

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------
# CONFIG
# ---------------------------
API_MODE = os.getenv("API_MODE", "sandbox")  # sandbox | live
SANDBOX_API_TOKEN = os.getenv("SANDBOX_API_TOKEN")
LIVE_API_TOKEN = os.getenv("LIVE_API_TOKEN")

if API_MODE == "live":
    API_TOKEN = LIVE_API_TOKEN
    PAWAPAY_URL = "https://api.pawapay.io/deposits"
else:
    API_TOKEN = SANDBOX_API_TOKEN
    PAWAPAY_URL = "https://api.sandbox.pawapay.io/deposits"

DATABASE = os.path.join(os.path.dirname(__file__), "investments.db")

INTEREST_RATE = float(os.getenv("INTEREST_RATE", "0.10"))  # 10%
INTEREST_DAYS = int(os.getenv("INTEREST_DAYS", "30"))      # 30 days


# ---------------------------
# DB SETUP
# ---------------------------
def init_db():
    db = sqlite3.connect(DATABASE)
    cur = db.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS investments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        investmentId TEXT UNIQUE,
        user_id TEXT,
        depositId TEXT UNIQUE,
        amount REAL,
        status TEXT,
        created_at TEXT,
        confirmed_at TEXT,
        return_date TEXT,
        interest REAL,
        balance REAL
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


# ---------------------------
# ROUTES
# ---------------------------
@app.route("/")
def home():
    return "VillageBank Investment Server ✅"


# ---- 1. Initiate Investment ----
@app.route("/api/investments/initiate", methods=["POST"])
def initiate_investment():
    """
    Client sends: { "user_id": "user123", "amount": 100, "phone": "26097..." }
    """
    try:
        data = request.json or {}
        user_id = data.get("user_id")
        amount = data.get("amount")
        phone = data.get("phone")
        currency = data.get("currency", "ZMW")
        correspondent = data.get("correspondent", "MTN_MOMO_ZMB")

        if not user_id or not amount or not phone:
            return jsonify({"error": "Missing user_id, amount or phone"}), 400

        investment_id = str(uuid.uuid4())
        deposit_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()

        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO investments (investmentId, user_id, depositId, amount, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (investment_id, user_id, deposit_id, float(amount), "PENDING_PAYMENT", created_at))
        db.commit()

        # Build payload for pawapay
        payload = {
            "depositId": deposit_id,
            "amount": str(amount),
            "currency": currency,
            "correspondent": correspondent,
            "payer": {"type": "MSISDN", "address": {"value": phone}},
            "customerTimestamp": created_at,
            "statementDescription": "VillageBank Investment",
            "metadata": [
                {"fieldName": "investmentId", "fieldValue": investment_id},
                {"fieldName": "userId", "fieldValue": user_id}
            ]
        }
        headers = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

        # Call pawapay deposit API
        try:
            resp = requests.post(PAWAPAY_URL, json=payload, headers=headers, timeout=15)
            pay_result = resp.json() if resp.content else {"status": "PENDING"}
        except Exception as e:
            logger.warning("PawaPay error: %s", e)
            pay_result = {"status": "PENDING", "error": str(e)}

        return jsonify({
            "investment_id": investment_id,
            "deposit_id": deposit_id,
            "status": "PENDING_PAYMENT",
            "payment_response": pay_result
        }), 200

    except Exception as e:
        logger.exception("Error in initiate_investment")
        return jsonify({"error": "Server error", "detail": str(e)}), 500


# ---- 2. Deposit Callback ----
@app.route("/callback/deposit", methods=["POST"])
def deposit_callback():
    """
    PawaPay calls this after deposit attempt.
    """
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data"}), 400

        deposit_id = data.get("depositId")
        status = str(data.get("status", "")).upper()

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT investmentId, amount, user_id FROM investments WHERE depositId=?", (deposit_id,))
        row = cur.fetchone()

        if row:
            investment_id, amount, user_id = row
            if status in ["COMPLETED", "SUCCESS", "PAYMENT_COMPLETED"]:
                confirmed_at = datetime.utcnow().isoformat()
                interest = round(float(amount) * INTEREST_RATE, 2)
                return_date = (datetime.utcnow() + timedelta(days=INTEREST_DAYS)).isoformat()
                balance = float(amount) + interest
                cur.execute("""
                    UPDATE investments
                    SET status=?, confirmed_at=?, return_date=?, interest=?, balance=?
                    WHERE investmentId=?
                """, ("CONFIRMED", confirmed_at, return_date, interest, balance, investment_id))
                db.commit()
                logger.info("Investment %s confirmed", investment_id)
            else:
                cur.execute("UPDATE investments SET status=? WHERE investmentId=?", (status, investment_id))
                db.commit()
                logger.info("Investment %s updated to %s", investment_id, status)

        return jsonify({"ok": True}), 200

    except Exception:
        logger.exception("Error in deposit_callback")
        return jsonify({"error": "Server error"}), 500


# ---- 3. Get User Investments ----
@app.route("/api/investments/<user_id>", methods=["GET"])
def get_investments(user_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT investmentId, amount, status, created_at, confirmed_at, return_date, interest, balance
        FROM investments WHERE user_id=? ORDER BY created_at DESC
    """, (user_id,))
    rows = cur.fetchall()
    return jsonify({"investments": [dict(r) for r in rows]}), 200


# ---------------------------
# MAIN
# ---------------------------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

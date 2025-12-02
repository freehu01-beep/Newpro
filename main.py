
import os
import threading
import sqlite3
from datetime import date
from flask import Flask, request, send_from_directory
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ====== CONFIG ======
API_ID    = int(os.getenv("API_ID", "123456"))
API_HASH  = os.getenv("API_HASH", "your_api_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))  # Telegram ID to receive withdraw requests

DB_PATH = "bot.db"

COINS_MONETAG  = 3
COINS_ADSTERRA = 5
COINS_UNITY    = 7
COINS_GAMEZOP  = 4

DAILY_BONUS      = 5
COINS_PER_RUPEE  = 10  # 10 coins = 1₹
MIN_WITHDRAW_RUP = 10  # minimum 10₹ (so 100 coins)

TAGLINE = "Turn Your Time Into Dhan — Only on DhanRush!"

# ====== DATABASE ======
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row

def init_db():
    with conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                coins INTEGER DEFAULT 0,
                referrals INTEGER DEFAULT 0,
                last_bonus TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                coins INTEGER,
                rupees REAL,
                method TEXT,
                details TEXT,
                status TEXT,
                created_at TEXT
            )"""
        )

def ensure_user(user_id: int):
    with conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))

def get_user(user_id: int):
    cur = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return cur.fetchone()

def add_coins(user_id: int, amount: int):
    with conn:
        conn.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id))

def add_referral(user_id: int):
    with conn:
        conn.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (user_id,))

def set_last_bonus(user_id: int, d: date):
    with conn:
        conn.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (d.isoformat(), user_id))

def create_withdrawal(user_id: int, coins: int, rupees: float, method: str, details: str):
    with conn:
        conn.execute(
            "INSERT INTO withdrawals (user_id, coins, rupees, method, details, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', datetime('now'))",
            (user_id, coins, rupees, method, details),
        )

# ====== BOT ======
bot = Client("dhanrush_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_states = {}  # for withdraw details: {user_id: {"step": "withdraw_details", "method": "UPI"}}

def main_menu():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎥 Watch Ads", callback_data="watch")],
            [InlineKeyboardButton("🎁 Daily Bonus", callback_data="bonus")],
            [InlineKeyboardButton("👥 Invite Friends", callback_data="invite")],
            [InlineKeyboardButton("🏆 My Balance", callback_data="bal")],
            [InlineKeyboardButton("💳 Withdraw", callback_data="withdraw")],
            [InlineKeyboardButton("🌐 Open DhanRush WebApp", callback_data="open_web")]
        ]
    )

@bot.on_message(filters.command("start"))
async def start_handler(_, message):
    user = message.from_user
    ensure_user(user.id)

    # referral
    if len(message.command) > 1:
        try:
            ref_id = int(message.command[1])
            if ref_id != user.id:
                ref_row = get_user(ref_id)
                if ref_row:
                    add_referral(ref_id)
                    add_coins(ref_id, 5)
                    try:
                        await bot.send_message(
                            ref_id,
                            "🎉 New user joined via your DhanRush link! +5 coins credited."
                        )
                    except Exception:
                        pass
        except ValueError:
            pass

    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={user.id}"

    text = (
        f"Hey {user.mention} 👋\n"
        "<b>Welcome to DhanRush!</b> 💸\n\n"
        f"{TAGLINE}\n\n"
        "Watch ads, play games & collect coins.\n"
        "10 coins = 1₹. Minimum withdrawal 10₹ (100 coins).\n\n"
        f"Your referral link:\n<code>{link}</code>"
    )

    await message.reply_text(text, reply_markup=main_menu(), disable_web_page_preview=True)

@bot.on_callback_query(filters.regex("^open_web$"))
async def open_web_cb(_, query):
    uid = query.from_user.id
    ensure_user(uid)
    base_url = os.getenv("WEB_URL", "https://your-render-app.onrender.com")
    web_url = f"{base_url}/web/index.html?uid={uid}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🌐 Open WebApp", url=web_url)],
                               [InlineKeyboardButton("⬅️ Back", callback_data="back")]])
    await query.message.edit_text(
        "Tap below to open the DhanRush WebApp for watching ads & playing games:",
        reply_markup=kb
    )

@bot.on_callback_query(filters.regex("^watch$"))
async def watch_cb(_, query):
    await open_web_cb(_, query)

@bot.on_callback_query(filters.regex("^bonus$"))
async def bonus_cb(_, query):
    uid = query.from_user.id
    ensure_user(uid)
    row = get_user(uid)
    today = date.today().isoformat()
    if row["last_bonus"] == today:
        await query.answer("You already claimed today's bonus.", show_alert=True)
        return
    set_last_bonus(uid, date.today())
    add_coins(uid, DAILY_BONUS)
    row = get_user(uid)
    await query.message.edit_text(
        f"🎁 Daily bonus claimed! +{DAILY_BONUS} coins\n"
        f"Current balance: {row['coins']} coins",
        reply_markup=main_menu()
    )

@bot.on_callback_query(filters.regex("^invite$"))
async def invite_cb(_, query):
    uid = query.from_user.id
    ensure_user(uid)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={uid}"
    await query.message.edit_text(
        "👥 <b>Invite Friends</b>\n\n"
        "Share this link with your friends so they can also join DhanRush:\n"
        f"<code>{link}</code>",
        reply_markup=main_menu(),
        disable_web_page_preview=True
    )

@bot.on_callback_query(filters.regex("^bal$"))
async def bal_cb(_, query):
    uid = query.from_user.id
    ensure_user(uid)
    row = get_user(uid)
    coins = row["coins"]
    rupees = coins / COINS_PER_RUPEE
    await query.message.edit_text(
        "💰 <b>Your DhanRush Balance</b>\n\n"
        f"Coins: <b>{coins}</b>\n"
        f"Approx: <b>{rupees:.2f}₹</b> (10 coins = 1₹)",
        reply_markup=main_menu()
    )

@bot.on_callback_query(filters.regex("^withdraw$"))
async def withdraw_cb(_, query):
    uid = query.from_user.id
    ensure_user(uid)
    row = get_user(uid)
    coins = row["coins"]
    rupees = coins / COINS_PER_RUPEE
    if rupees < MIN_WITHDRAW_RUP:
        await query.answer(
            f"Min withdraw is {MIN_WITHDRAW_RUP}₹ (need {MIN_WITHDRAW_RUP*COINS_PER_RUPEE} coins).",
            show_alert=True
        )
        return
    text = (
        "💳 <b>DhanRush Withdraw</b>\n\n"
        f"Balance: {coins} coins ≈ {rupees:.2f}₹\n"
        f"Min withdraw: {MIN_WITHDRAW_RUP}₹\n\n"
        "Choose withdrawal method:"
    )
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("UPI", callback_data="w_m_upi"),
                InlineKeyboardButton("Paytm", callback_data="w_m_paytm"),
            ],
            [
                InlineKeyboardButton("Bank", callback_data="w_m_bank"),
                InlineKeyboardButton("Other", callback_data="w_m_other"),
            ],
            [InlineKeyboardButton("⬅️ Back", callback_data="back")],
        ]
    )
    await query.message.edit_text(text, reply_markup=kb)

@bot.on_callback_query(filters.regex("^w_m_"))
async def withdraw_method_cb(_, query):
    uid = query.from_user.id
    ensure_user(uid)
    method_map = {
        "w_m_upi": "UPI",
        "w_m_paytm": "Paytm",
        "w_m_bank": "Bank",
        "w_m_other": "Other",
    }
    method = method_map.get(query.data)
    if not method:
        await query.answer("Unknown method.", show_alert=True)
        return
    user_states[uid] = {"step": "withdraw_details", "method": method}
    prompt = {
        "UPI": "Send your UPI ID (example: name@upi):",
        "Paytm": "Send your Paytm number or ID:",
        "Bank": "Send bank details (Account No, IFSC, Name):",
        "Other": "Send details for your withdrawal method:",
    }[method]
    await query.message.edit_text(
        f"💳 <b>{method} Withdraw</b>\n\n{prompt}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="back")]])
    )

@bot.on_message(filters.private & filters.text)
async def text_handler(_, message):
    uid = message.from_user.id
    state = user_states.get(uid)
    if state and state.get("step") == "withdraw_details":
        method = state["method"]
        details = message.text.strip()
        row = get_user(uid)
        coins = row["coins"]
        rupees = coins / COINS_PER_RUPEE
        if rupees < MIN_WITHDRAW_RUP:
            await message.reply_text("Balance dropped below minimum withdraw. Try again later.", reply_markup=main_menu())
            user_states.pop(uid, None)
            return
        create_withdrawal(uid, coins, rupees, method, details)
        with conn:
            conn.execute("UPDATE users SET coins = 0 WHERE user_id = ?", (uid,))
        user_states.pop(uid, None)

        await message.reply_text(
            "✅ Withdraw request created!\n"
            f"Amount: {rupees:.2f}₹ ({coins} coins)\n"
            f"Method: {method}\n"
            "It will be processed manually by DhanRush admin.",
            reply_markup=main_menu()
        )

        if ADMIN_ID:
            try:
                await bot.send_message(
                    ADMIN_ID,
                    "💳 New DhanRush withdraw request:\n"
                    f"User: <code>{uid}</code>\n"
                    f"Amount: {rupees:.2f}₹ ({coins} coins)\n"
                    f"Method: {method}\n"
                    f"Details: {details}"
                )
            except Exception:
                pass
    else:
        if message.text.startswith("/start"):
            return
        await message.reply_text(
            "Use the menu buttons to watch ads, earn coins, and withdraw on DhanRush.\n"
            "Commands: /start",
            reply_markup=main_menu()
        )

@bot.on_callback_query(filters.regex("^back$"))
async def back_cb(_, query):
    await query.message.edit_text("Main menu:", reply_markup=main_menu())

# ====== FLASK (WEB + REWARD) ======
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "DhanRush Bot is running", 200

@flask_app.route("/web/<path:filename>")
def web_files(filename):
    base = os.path.join(os.path.dirname(__file__), "web")
    return send_from_directory(base, filename)

@flask_app.route("/reward")
def reward_endpoint():
    uid = request.args.get("uid", type=int)
    network = request.args.get("network", "unknown")
    if not uid:
        return "missing uid", 400
    ensure_user(uid)
    reward_map = {
        "monetag": COINS_MONETAG,
        "adsterra": COINS_ADSTERRA,
        "unity": COINS_UNITY,
        "gamezop": COINS_GAMEZOP,
    }
    coins = reward_map.get(network, 1)
    add_coins(uid, coins)
    print(f"Rewarded user {uid} from {network}: +{coins} coins")
    return "ok", 200

def run_flask():
    port = int(os.getenv("PORT", "10000"))
    flask_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    init_db()
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    bot.start()
    idle()
    bot.stop()

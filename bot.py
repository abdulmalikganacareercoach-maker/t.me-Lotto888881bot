import asyncio
import datetime
import logging
import os
import random
import sqlite3
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
log = logging.getLogger("bot")

# ---------- Config (set these as Railway Variables) ----------
BOT_TOKEN = os.environ["BOT_TOKEN"]
DAILY_HOUR = int(os.getenv("DAILY_HOUR", "8"))          # hour of day for the daily post
TIMEZONE = os.getenv("TIMEZONE", "Africa/Lagos")         # any IANA timezone name
DATA_DIR = os.getenv("DATA_DIR", ".")                    # point at a Railway Volume to keep subscribers
DB_PATH = os.path.join(DATA_DIR, "subscribers.db")

DISCLAIMER = (
    "Educational content only, not financial advice. "
    "Trading involves risk and you can lose money."
)

# ---------- Content ----------
MENTAL_MODELS = [
    ("First Principles Thinking",
     "Break a problem down to its basic truths and rebuild from there instead of copying what others do. "
     "Ask: what do I know for certain, and what am I only assuming?"),
    ("Inversion",
     "Instead of asking how to succeed, ask how you would guarantee failure, then avoid those things. "
     "Great for spotting risks in a plan or a trade."),
    ("Circle of Competence",
     "Know the edges of what you truly understand. Operate inside it, and expand it slowly. "
     "The size of the circle matters less than knowing where its boundary is."),
    ("Second-Order Thinking",
     "Don't stop at the first consequence. Ask: and then what? "
     "Most poor decisions come from ignoring the second and third effects."),
    ("Margin of Safety",
     "Build in a buffer for being wrong. Plans, budgets and positions should survive your errors, "
     "not depend on you being perfect."),
    ("Opportunity Cost",
     "Every yes is a no to something else. The real price of a choice is the best alternative you gave up."),
    ("Confirmation Bias",
     "We look for evidence that agrees with us. Actively seek the strongest argument against your view "
     "before you commit."),
    ("Sunk Cost Fallacy",
     "Money, time or effort already spent should not decide your next move. "
     "Judge a decision by its future costs and benefits only."),
    ("Pareto Principle (80/20)",
     "Roughly 80% of results come from 20% of causes. Find your vital few and put your energy there."),
    ("Occam's Razor",
     "When several explanations fit, start with the one that needs the fewest assumptions."),
    ("Hanlon's Razor",
     "Don't assume malice where incompetence or misunderstanding is a likelier explanation. "
     "It saves relationships and clears your thinking."),
    ("Compounding",
     "Small, consistent gains stacked over time beat sporadic big moves. "
     "It works for skills, habits and capital, and it punishes interruptions."),
    ("The Map Is Not the Territory",
     "Models, charts and opinions are simplifications of reality. Use them, but check them against what is actually happening."),
    ("Loss Aversion",
     "Losses feel about twice as painful as equal gains feel good. "
     "Knowing this helps you avoid holding losers too long and cutting winners too early."),
]

FOREX_TIPS = [
    ("Risk a small fixed % per trade",
     "Many traders cap risk at 1-2% of their account per trade. "
     "It keeps one bad trade from becoming a disaster."),
    ("Always know your stop before you enter",
     "Decide where you are wrong before you click buy or sell. "
     "Moving a stop further away after entry is a classic account killer."),
    ("Check risk-to-reward",
     "If you risk 1 to make 1, you need to win more than half the time just to break even. "
     "Many traders look for setups paying at least 1.5 to 2 times the risk."),
    ("Mind the news calendar",
     "Major releases (NFP, CPI, central bank decisions) can spike spreads and cause sudden gaps. "
     "Know when they hit before you hold a trade."),
    ("Keep a trading journal",
     "Record your reason for entry, the result and how you felt. "
     "Patterns in your mistakes are the cheapest education you will get."),
    ("Understand leverage",
     "Leverage magnifies losses as much as gains. Trade a size you can afford to lose, not the maximum your broker allows."),
    ("Don't revenge trade",
     "After a loss, the urge to win it back immediately leads to oversized, low-quality trades. "
     "Step away and review instead."),
    ("Trade the session, not the clock",
     "Liquidity and volatility differ across Asian, London and New York sessions. "
     "Match your pair and strategy to when it actually moves."),
    ("Watch correlations",
     "Going long EUR/USD and GBP/USD at once is often close to doubling one bet on the US dollar. "
     "Know your real exposure."),
    ("Test on a demo first",
     "Prove a strategy over many trades on a demo account before risking real money. "
     "A few wins is luck, not an edge."),
    ("Spreads and fees are a hidden cost",
     "Frequent trading on wide spreads quietly eats returns. Factor costs into every strategy."),
    ("Protect your capital first",
     "Staying in the game matters more than any single trade. "
     "Survive long enough and the learning compounds."),
]

# ---------- Storage ----------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS subscribers (chat_id INTEGER PRIMARY KEY)"
    )
    return conn


def add_sub(chat_id: int):
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO subscribers VALUES (?)", (chat_id,))


def remove_sub(chat_id: int):
    with db() as conn:
        conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))


def is_sub(chat_id: int) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT 1 FROM subscribers WHERE chat_id = ?", (chat_id,)
        ).fetchone()
    return row is not None


def all_subs():
    with db() as conn:
        return [r[0] for r in conn.execute("SELECT chat_id FROM subscribers")]


# ---------- Message builders ----------
def model_text() -> str:
    title, body = random.choice(MENTAL_MODELS)
    return f"🧠 *{title}*\n\n{body}"


def forex_text() -> str:
    title, body = random.choice(FOREX_TIPS)
    return f"📈 *{title}*\n\n{body}\n\n_{DISCLAIMER}_"


def keyboard(chat_id: int) -> InlineKeyboardMarkup:
    sub_btn = (
        InlineKeyboardButton("🔕 Stop daily", callback_data="unsub")
        if is_sub(chat_id)
        else InlineKeyboardButton("🔔 Get daily", callback_data="sub")
    )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🧠 Mental model", callback_data="model"),
                InlineKeyboardButton("📈 Forex tip", callback_data="forex"),
            ],
            [sub_btn],
        ]
    )


# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (
        "👋 Welcome! I share short mental models and forex education tips "
        "to help you think clearer and trade smarter.\n\n"
        "Tap a button below, or use /help to see all commands."
    )
    await update.message.reply_text(text, reply_markup=keyboard(chat_id))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n"
        "/model - a random mental model\n"
        "/forex - a random forex education tip\n"
        "/daily - get a fresh tip every day\n"
        "/stop - stop the daily tips\n"
        "/about - about this bot\n\n" + DISCLAIMER
    )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "This bot delivers bite-sized mental models and forex education. "
        "It does not run lotteries, take payments or offer prizes.\n\n" + DISCLAIMER
    )


async def model_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        model_text(),
        parse_mode="Markdown",
        reply_markup=keyboard(update.effective_chat.id),
    )


async def forex_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        forex_text(),
        parse_mode="Markdown",
        reply_markup=keyboard(update.effective_chat.id),
    )


async def daily_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_sub(update.effective_chat.id)
    await update.message.reply_text(
        f"✅ Subscribed. You'll get a daily tip around {DAILY_HOUR}:00 ({TIMEZONE}). Use /stop to cancel."
    )


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remove_sub(update.effective_chat.id)
    await update.message.reply_text("🔕 Unsubscribed. Use /daily any time to rejoin.")


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id

    if q.data == "model":
        await q.message.reply_text(
            model_text(), parse_mode="Markdown", reply_markup=keyboard(chat_id)
        )
    elif q.data == "forex":
        await q.message.reply_text(
            forex_text(), parse_mode="Markdown", reply_markup=keyboard(chat_id)
        )
    elif q.data == "sub":
        add_sub(chat_id)
        await q.message.reply_text(
            f"✅ Subscribed. Daily tip around {DAILY_HOUR}:00 ({TIMEZONE}).",
            reply_markup=keyboard(chat_id),
        )
    elif q.data == "unsub":
        remove_sub(chat_id)
        await q.message.reply_text(
            "🔕 Unsubscribed.", reply_markup=keyboard(chat_id)
        )


# ---------- Daily broadcast ----------
async def send_daily(context: ContextTypes.DEFAULT_TYPE):
    subs = all_subs()
    log.info("Sending daily tip to %d subscribers", len(subs))
    # Alternate between a mental model and a forex tip by day of year
    day = datetime.date.today().timetuple().tm_yday
    text = (
        "☀️ *Daily tip*\n\n" + model_text()
        if day % 2 == 0
        else "☀️ *Daily tip*\n\n" + forex_text()
    )
    for chat_id in subs:
        try:
            await context.bot.send_message(chat_id, text, parse_mode="Markdown")
        except Forbidden:
            remove_sub(chat_id)  # user blocked the bot
        except Exception as e:
            log.warning("Failed to send to %s: %s", chat_id, e)
        await asyncio.sleep(0.05)  # stay well under Telegram's rate limits


# ---------- Main ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("model", model_cmd))
    app.add_handler(CommandHandler("forex", forex_cmd))
    app.add_handler(CommandHandler("daily", daily_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CallbackQueryHandler(on_button))

    app.job_queue.run_daily(
        send_daily,
        time=datetime.time(hour=DAILY_HOUR, minute=0, tzinfo=ZoneInfo(TIMEZONE)),
    )

    log.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

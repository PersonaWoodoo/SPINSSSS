"""
🎰 Telegram-бот «Казино» — один файл.
Запуск: python bot.py
"""
import asyncio
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Optional, Any, Callable, Awaitable

import aiosqlite
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    ChatMemberUpdated,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# ══════════════════════════════════════════════════════════
#                        CONFIG
# ══════════════════════════════════════════════════════════
BOT_TOKEN = "8588518585:AAH5V0iKnfrsLxIlQ0GoHwPKhyUBmeuiLlI"
BOT_USERNAME = "BIG_SPINS_bot"        # ← поменяй на юзернейм своего бота
ADMIN_IDS = [8959461245]

# Обязательная подписка
REQUIRED_CHANNELS = [
    {"username": "BIG_SPINS", "title": "BIG SPINS", "url": "https://t.me/BIG_SPINS"},
]

DB_PATH = "casino.db"
LOG_PATH = "bot.log"

START_BALANCE = 1000
DAILY_BONUS = 500
DAILY_STREAK_BONUS = 100
DAILY_COOLDOWN = 24 * 60 * 60
WORK_COOLDOWN = 60 * 60
BONUS_COOLDOWN = 4 * 60 * 60

MIN_BET = 10
MAX_BET = 100000
REF_BONUS = 0.5
REFERRAL_PERCENT = 5
DEFAULT_EMOJI = "💰"

JACKPOT_CHANCE = 1 / 10000
JACKPOT_CONTRIBUTION = 0.01

SUB_CHECK_CACHE_TTL = 300  # секунд

# ══════════════════════════════════════════════════════════
#                        LOGGING
# ══════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("casino")

# ══════════════════════════════════════════════════════════
#                        BOT
# ══════════════════════════════════════════════════════════
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# ══════════════════════════════════════════════════════════
#                        HELPERS
# ══════════════════════════════════════════════════════════
def fmt(n) -> str:
    """1 000 000"""
    if isinstance(n, float) and n.is_integer():
        n = int(n)
    try:
        return f"{n:,}".replace(",", " ")
    except Exception:
        return str(n)


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ══════════════════════════════════════════════════════════
#                        DATABASE
# ══════════════════════════════════════════════════════════
async def init_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            bank INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            xp INTEGER DEFAULT 0,
            total_bets INTEGER DEFAULT 0,
            total_wins INTEGER DEFAULT 0,
            total_losses INTEGER DEFAULT 0,
            biggest_win INTEGER DEFAULT 0,
            biggest_loss INTEGER DEFAULT 0,
            last_daily INTEGER DEFAULT 0,
            daily_streak INTEGER DEFAULT 0,
            last_work INTEGER DEFAULT 0,
            last_bonus INTEGER DEFAULT 0,
            referrer_id INTEGER DEFAULT 0,
            referral_count INTEGER DEFAULT 0,
            clan_id INTEGER,
            married_to INTEGER,
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            ban_until INTEGER DEFAULT 0,
            is_premium INTEGER DEFAULT 0,
            created_at INTEGER,
            last_seen INTEGER
        );
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, game TEXT, amount INTEGER,
            result TEXT, payout INTEGER, multiplier REAL,
            created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount REAL, type TEXT,
            reason TEXT, created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS achievements_list (
            code TEXT PRIMARY KEY, name TEXT, description TEXT,
            reward INTEGER, icon TEXT
        );
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, code TEXT, unlocked_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS quests_list (
            code TEXT PRIMARY KEY, name TEXT, description TEXT,
            type TEXT, target INTEGER, reward INTEGER
        );
        CREATE TABLE IF NOT EXISTS quests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, code TEXT, progress INTEGER DEFAULT 0,
            target INTEGER, reward INTEGER, completed INTEGER DEFAULT 0,
            expires_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY, amount INTEGER DEFAULT 0,
            uses_left INTEGER, max_uses INTEGER, expires_at INTEGER,
            created_by INTEGER, created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS promo_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT, user_id INTEGER, used_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS shop_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, description TEXT, price INTEGER,
            type TEXT, value TEXT, icon TEXT,
            is_active INTEGER DEFAULT 1, stock INTEGER DEFAULT -1
        );
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, item_id INTEGER,
            quantity INTEGER DEFAULT 1, equipped INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS clans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, tag TEXT, owner_id INTEGER,
            balance INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
            members_count INTEGER DEFAULT 1, created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS clan_members (
            clan_id INTEGER, user_id INTEGER, role TEXT,
            joined_at INTEGER, PRIMARY KEY (clan_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, game TEXT, entry_fee INTEGER,
            prize_pool INTEGER, max_players INTEGER,
            starts_at INTEGER, ends_at INTEGER,
            status TEXT DEFAULT 'open', winner_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS tournament_players (
            tournament_id INTEGER, user_id INTEGER,
            score INTEGER DEFAULT 0, joined_at INTEGER,
            PRIMARY KEY (tournament_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS lotteries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prize INTEGER, ticket_price INTEGER,
            tickets_sold INTEGER DEFAULT 0,
            ends_at INTEGER, winner_id INTEGER,
            status TEXT DEFAULT 'open'
        );
        CREATE TABLE IF NOT EXISTS lottery_tickets (
            lottery_id INTEGER, user_id INTEGER, tickets INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS gifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id INTEGER, to_id INTEGER, item_id INTEGER,
            message TEXT, claimed INTEGER DEFAULT 0, created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS marriages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id INTEGER, user2_id INTEGER,
            married_at INTEGER, divorce_at INTEGER,
            is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER, action TEXT, target_id INTEGER,
            details TEXT, created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, type TEXT, multiplier REAL,
            starts_at INTEGER, ends_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS jackpot (
            id INTEGER PRIMARY KEY CHECK (id = 1), amount INTEGER DEFAULT 0
        );
        """)

        await conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('currency_emoji', ?)",
            (DEFAULT_EMOJI,))
        await conn.execute("INSERT OR IGNORE INTO jackpot (id, amount) VALUES (1, 0)")

        games = ["slots", "dice", "coin", "roulette", "blackjack", "mines",
                 "wheel", "crash", "plinko", "keno", "baccarat", "poker",
                 "football", "basketball", "bowling", "darts", "rps",
                 "guess", "snake", "lottery"]
        for g in games:
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, '1')",
                (f"game_{g}_enabled",))
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, '95')",
                (f"rtp_{g}",))
        await conn.commit()


# ═══════════════ SETTINGS ═══════════════
async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value))
        await conn.commit()


async def get_emoji() -> str:
    return await get_setting("currency_emoji", DEFAULT_EMOJI)


# ═══════════════ USERS ═══════════════
async def get_user(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_user_by_username(username: str) -> Optional[dict]:
    username = username.lstrip("@")
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_user(user_id: int, username: str, first_name: str,
                      referrer_id: int = 0) -> dict:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT OR IGNORE INTO users
            (id, username, first_name, balance, created_at, last_seen, referrer_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, username, first_name, START_BALANCE, now, now, referrer_id))
        await conn.execute(
            "INSERT INTO transactions (user_id, amount, type, reason, created_at) "
            "VALUES (?, ?, 'start', 'Регистрация', ?)",
            (user_id, START_BALANCE, now))

        if referrer_id and referrer_id != user_id:
            ref = await get_user(referrer_id)
            if ref:
                bonus = int(REF_BONUS)
                await conn.execute(
                    "UPDATE users SET balance = balance + ?, referral_count = referral_count + 1 "
                    "WHERE id = ?", (bonus, referrer_id))
                await conn.execute(
                    "INSERT INTO transactions (user_id, amount, type, reason, created_at) "
                    "VALUES (?, ?, 'ref', 'Реферальный бонус', ?)",
                    (referrer_id, REF_BONUS, now))
        await conn.commit()
    return await get_user(user_id)


async def update_user(user_id: int, **fields):
    if not fields:
        return
    keys = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [user_id]
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(f"UPDATE users SET {keys} WHERE id = ?", vals)
        await conn.commit()


async def add_balance(user_id: int, amount: int, tx_type: str = "bet",
                      reason: str = "") -> int:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?",
            (amount, user_id))
        await conn.execute(
            "INSERT INTO transactions (user_id, amount, type, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, tx_type, reason, now))
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
        row = await cur.fetchone()
        await conn.commit()
        return row["balance"] if row else 0


async def set_balance(user_id: int, value: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET balance = ? WHERE id = ?", (value, user_id))
        await conn.commit()


async def add_xp(user_id: int, amount: int) -> int:
    user = await get_user(user_id)
    if not user:
        return 1
    new_xp = user["xp"] + amount
    new_level = 1 + new_xp // 1000
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET xp = ?, level = ? WHERE id = ?",
            (new_xp, new_level, user_id))
        await conn.commit()
    return new_level


async def log_bet(user_id: int, game: str, amount: int, result: str,
                  payout: int, multiplier: float = 0):
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO bets (user_id, game, amount, result, payout, multiplier, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, game, amount, result, payout, multiplier, now))
        if result == "win":
            await conn.execute(
                """UPDATE users SET total_bets = total_bets + 1,
                   total_wins = total_wins + 1,
                   biggest_win = MAX(biggest_win, ?)
                   WHERE id = ?""", (payout - amount, user_id))
        elif result == "lose":
            await conn.execute(
                """UPDATE users SET total_bets = total_bets + 1,
                   total_losses = total_losses + 1,
                   biggest_loss = MAX(biggest_loss, ?)
                   WHERE id = ?""", (amount, user_id))
        else:
            await conn.execute(
                "UPDATE users SET total_bets = total_bets + 1 WHERE id = ?",
                (user_id,))

        if result == "lose":
            cur = await conn.execute("SELECT referrer_id FROM users WHERE id = ?", (user_id,))
            row = await cur.fetchone()
            if row and row[0]:
                ref_bonus = int(amount * REFERRAL_PERCENT / 100)
                if ref_bonus > 0:
                    await conn.execute(
                        "UPDATE users SET balance = balance + ? WHERE id = ?",
                        (ref_bonus, row[0]))
                    await conn.execute(
                        "INSERT INTO transactions (user_id, amount, type, reason, created_at) "
                        "VALUES (?, ?, 'ref_percent', 'Процент с реферала', ?)",
                        (row[0], ref_bonus, now))

        jp = int(amount * JACKPOT_CONTRIBUTION)
        if jp > 0:
            await conn.execute(
                "UPDATE jackpot SET amount = amount + ? WHERE id = 1", (jp,))
        await conn.commit()


async def get_top(by: str = "balance", limit: int = 10):
    col = {
        "balance": "balance",
        "bets": "total_bets",
        "wins": "total_wins",
        "biggest_win": "biggest_win",
    }.get(by, "balance")
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            f"SELECT username, first_name, {col} FROM users "
            f"WHERE is_banned = 0 ORDER BY {col} DESC LIMIT ?", (limit,))
        return await cur.fetchall()


async def count_referrals(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0


async def get_jackpot() -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT amount FROM jackpot WHERE id = 1")
        row = await cur.fetchone()
        return row[0] if row else 0


async def reset_jackpot():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE jackpot SET amount = 0 WHERE id = 1")
        await conn.commit()


async def admin_log(admin_id: int, action: str, target_id: int = 0, details: str = ""):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO admin_logs (admin_id, action, target_id, details, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (admin_id, action, target_id, details, int(time.time())))
        await conn.commit()

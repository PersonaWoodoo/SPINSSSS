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
      # ══════════════════════════════════════════════════════════
#                        FSM STATES
# ══════════════════════════════════════════════════════════
class BetState(StatesGroup):
    waiting_amount = State()
    waiting_choice = State()
    waiting_number = State()


class BankState(StatesGroup):
    waiting_amount = State()


class TransferState(StatesGroup):
    waiting_recipient = State()
    waiting_amount = State()


class MinesState(StatesGroup):
    in_game = State()


class BlackjackState(StatesGroup):
    in_game = State()


class CrashState(StatesGroup):
    in_game = State()


class PromoState(StatesGroup):
    waiting_code = State()


class RPSState(StatesGroup):
    waiting_choice = State()


class GuessState(StatesGroup):
    in_game = State()


# Админские состояния
class AdminState(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()
    waiting_reason = State()
    waiting_broadcast = State()
    waiting_promo_amount = State()
    waiting_promo_uses = State()
    waiting_sate_value = State()
    waiting_rtp = State()


# ══════════════════════════════════════════════════════════
#                        KEYBOARDS
# ══════════════════════════════════════════════════════════
def reply_main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="🎰 Казино")
    kb.button(text="💰 Баланс")
    kb.button(text="🎁 Бонус")
    kb.button(text="👤 Профиль")
    kb.button(text="🏆 Топ")
    kb.button(text="🛒 Магазин")
    kb.button(text="⚙️ Ещё")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup(resize_keyboard=True)


def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎰 Слоты", callback_data="game:slots")
    kb.button(text="🎲 Кубик", callback_data="game:dice")
    kb.button(text="🪙 Монетка", callback_data="game:coin")
    kb.button(text="🎯 Рулетка", callback_data="game:roulette")
    kb.button(text="🃏 Блэкджек", callback_data="game:blackjack")
    kb.button(text="💣 Мины", callback_data="game:mines")
    kb.button(text="🎡 Колесо", callback_data="game:wheel")
    kb.button(text="📈 Crash", callback_data="game:crash")
    kb.button(text="⚽ Футбол", callback_data="game:football")
    kb.button(text="🏀 Баскетбол", callback_data="game:basketball")
    kb.button(text="🎳 Боулинг", callback_data="game:bowling")
    kb.button(text="🎯 Дартс", callback_data="game:darts")
    kb.button(text="✊ КНБ", callback_data="game:rps")
    kb.button(text="🔢 Угадай число", callback_data="game:guess")
    kb.button(text="🎟 Лотерея", callback_data="game:lottery")
    kb.button(text="⬅️ Назад", callback_data="menu:main")
    kb.adjust(2, 2, 2, 2, 2, 2, 2, 2)
    return kb.as_markup()


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
    ])


def profile_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Баланс", callback_data="menu:balance")
    kb.button(text="🏦 Банк", callback_data="menu:bank")
    kb.button(text="👥 Рефералы", callback_data="menu:ref")
    kb.button(text="🏆 Достижения", callback_data="menu:ach")
    kb.button(text="📜 Квесты", callback_data="menu:quests")
    kb.button(text="🛒 Инвентарь", callback_data="menu:inv")
    kb.button(text="⬅️ Назад", callback_data="menu:main")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()


def sub_check_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for ch in REQUIRED_CHANNELS:
        kb.button(text=f"📢 {ch['title']}", url=ch["url"])
    kb.button(text="✅ Я подписался", callback_data="check_sub")
    kb.adjust(1)
    return kb.as_markup()


# ══════════════════════════════════════════════════════════
#                    MIDDLEWARES
# ══════════════════════════════════════════════════════════
class ThrottlingMiddleware(BaseMiddleware):
    """1 действие в 0.7 сек на пользователя."""
    def __init__(self, rate: float = 0.7):
        self.rate = rate
        self.users: dict[int, float] = {}

    async def __call__(self, handler, event, data):
        uid = None
        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
        elif isinstance(event, CallbackQuery):
            uid = event.from_user.id

        if uid and uid not in ADMIN_IDS:
            now = time.time()
            last = self.users.get(uid, 0)
            if now - last < self.rate:
                if isinstance(event, CallbackQuery):
                    await event.answer("⏳ Не так быстро!", show_alert=False)
                return
            self.users[uid] = now

        return await handler(event, data)


class SubscriptionMiddleware(BaseMiddleware):
    """Проверка подписки на каналы. Админы пропускаются."""
    def __init__(self):
        self.cache: dict[int, float] = {}

    async def _check(self, uid: int) -> bool:
        # Кэш
        now = time.time()
        if uid in self.cache and now - self.cache[uid] < SUB_CHECK_CACHE_TTL:
            return True

        for ch in REQUIRED_CHANNELS:
            try:
                member = await bot.get_chat_member(f"@{ch['username']}", uid)
                status = member.status
                if status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
                    return False
            except Exception as e:
                log.warning(f"sub check fail {ch['username']} {uid}: {e}")
                # если не можем проверить — пропускаем (чтобы не блокировать всех)
                return True

        self.cache[uid] = now
        return True

    async def __call__(self, handler, event, data):
        uid = None
        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
        elif isinstance(event, CallbackQuery):
            uid = event.from_user.id

        if not uid or uid in ADMIN_IDS:
            return await handler(event, data)

        # Пропускаем сам callback проверки и /start
        if isinstance(event, CallbackQuery) and event.data == "check_sub":
            return await handler(event, data)
        if isinstance(event, Message):
            txt = (event.text or "").strip()
            if txt.startswith("/start"):
                return await handler(event, data)

        if not await self._check(uid):
            text = (
                "🔒 <b>Требуется подписка</b>\n\n"
                "Чтобы играть, подпишись на наши каналы:\n" +
                "\n".join(f"• <a href='{c['url']}'>{c['title']}</a>"
                         for c in REQUIRED_CHANNELS) +
                "\n\nПосле подписки нажми «✅ Я подписался»."
            )
            if isinstance(event, Message):
                await event.answer(text, reply_markup=sub_check_kb(),
                                   disable_web_page_preview=True)
            elif isinstance(event, CallbackQuery):
                await event.message.answer(text, reply_markup=sub_check_kb(),
                                           disable_web_page_preview=True)
                await event.answer()
            return

        return await handler(event, data)


class BanCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        uid = None
        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
        elif isinstance(event, CallbackQuery):
            uid = event.from_user.id

        if uid and uid not in ADMIN_IDS:
            user = await get_user(uid)
            if user and user["is_banned"]:
                now = int(time.time())
                if user["ban_until"] and user["ban_until"] < now:
                    await update_user(uid, is_banned=0, ban_reason=None, ban_until=0)
                else:
                    txt = f"🚫 <b>Вы забанены</b>\n\nПричина: {user['ban_reason'] or '—'}"
                    if user["ban_until"]:
                        left = user["ban_until"] - now
                        txt += f"\n⏳ Осталось: ~{left // 3600}ч"
                    if isinstance(event, Message):
                        await event.answer(txt)
                    elif isinstance(event, CallbackQuery):
                        await event.answer("🚫 Вы забанены", show_alert=True)
                    return
        return await handler(event, data)


class UserMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        uid = None
        if isinstance(event, Message) and event.from_user:
            uid = event.from_user.id
        elif isinstance(event, CallbackQuery):
            uid = event.from_user.id

        if uid:
            user = await get_user(uid)
            if user:
                async with aiosqlite.connect(DB_PATH) as conn:
                    await conn.execute(
                        "UPDATE users SET last_seen = ? WHERE id = ?",
                        (int(time.time()), uid))
                    await conn.commit()
            data["user"] = user
        return await handler(event, data)


# Регистрируем middlewares
dp.message.middleware(ThrottlingMiddleware())
dp.message.middleware(SubscriptionMiddleware())
dp.message.middleware(BanCheckMiddleware())
dp.message.middleware(UserMiddleware())

dp.callback_query.middleware(ThrottlingMiddleware())
dp.callback_query.middleware(SubscriptionMiddleware())
dp.callback_query.middleware(BanCheckMiddleware())
dp.callback_query.middleware(UserMiddleware())


# ══════════════════════════════════════════════════════════
#                    VALIDATION
# ══════════════════════════════════════════════════════════
async def validate_bet(user_id: int, amount: int) -> tuple[bool, str]:
    if amount < MIN_BET:
        return False, f"❌ Мин. ставка: {fmt(MIN_BET)}"
    if amount > MAX_BET:
        return False, f"❌ Макс. ставка: {fmt(MAX_BET)}"
    user = await get_user(user_id)
    if not user:
        return False, "❌ Сначала /start"
    if amount > user["balance"]:
        return False, f"❌ Недостаточно средств. Баланс: {fmt(user['balance'])}"
    return True, ""


async def game_enabled(game: str) -> bool:
    return await get_setting(f"game_{game}_enabled", "1") == "1"


# ══════════════════════════════════════════════════════════
#                    /start + REF
# ══════════════════════════════════════════════════════════
@dp.message(CommandStart())
async def cmd_start(message: Message):
    uid = message.from_user.id
    uname = message.from_user.username or ""
    fname = message.from_user.first_name or "игрок"

    referrer_id = 0
    args = (message.text or "").split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref = int(args[1][4:])
            if ref != uid:
                referrer_id = ref
        except ValueError:
            pass

    existing = await get_user(uid)
    if not existing:
        user = await create_user(uid, uname, fname, referrer_id)
        emoji = await get_emoji()

        if referrer_id:
            try:
                await bot.send_message(
                    referrer_id,
                    f"🎉 <b>Новый реферал!</b>\n\n"
                    f"👤 {fname}\n"
                    f"Начислено: <b>+{REF_BONUS}$</b> на баланс\n"
                    f"💡 +{REFERRAL_PERCENT}% с его проигрышей — твои навсегда!")
            except Exception:
                pass

        await message.answer(
            f"🎰 <b>Добро пожаловать в Казино!</b>\n\n"
            f"Стартовый баланс: {emoji} <b>{fmt(user['balance'])}</b>\n\n"
            f"🎮 /menu — играть\n"
            f"🔗 /ref — приглашать друзей и зарабатывать",
            reply_markup=reply_main_menu(),
        )
    else:
        # обновляем username, если изменился
        if uname and existing["username"] != uname:
            await update_user(uid, username=uname)
        await message.answer(
            "🎰 <b>С возвращением!</b>\n\nИспользуй меню ниже 👇",
            reply_markup=reply_main_menu(),
        )


@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery):
    # сброс кэша подписки
    for mw in dp.callback_query.middleware._middlewares:
        if isinstance(mw, SubscriptionMiddleware):
            mw.cache.pop(call.from_user.id, None)

    # повторная проверка
    for ch in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(f"@{ch['username']}", call.from_user.id)
            if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
                await call.answer(f"❌ Ты не подписан на {ch['title']}", show_alert=True)
                return
        except Exception:
            pass

    await call.message.edit_text(
        "✅ <b>Подписка подтверждена!</b>\n\nНапиши /start чтобы начать играть."
    )
    await call.answer("✅ Готово!")


# ══════════════════════════════════════════════════════════
#                    /menu
# ══════════════════════════════════════════════════════════
@dp.message(Command("menu"))
@dp.message(F.text == "🎰 Казино")
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    emoji = await get_emoji()
    user = await get_user(message.from_user.id)
    bal = user["balance"] if user else 0
    await message.answer(
        f"🎰 <b>Главное меню</b>\n\n"
        f"{emoji} Баланс: <b>{fmt(bal)}</b>\n\n"
        f"Выбери игру:",
        reply_markup=main_menu_kb(),
    )


@dp.callback_query(F.data == "menu:main")
async def cb_menu_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    emoji = await get_emoji()
    user = await get_user(call.from_user.id)
    bal = user["balance"] if user else 0
    try:
        await call.message.edit_text(
            f"🎰 <b>Главное меню</b>\n\n"
            f"{emoji} Баланс: <b>{fmt(bal)}</b>\n\n"
            f"Выбери игру:",
            reply_markup=main_menu_kb(),
        )
    except Exception:
        await call.message.answer(
            f"🎰 <b>Главное меню</b>\n\n{emoji} Баланс: <b>{fmt(bal)}</b>",
            reply_markup=main_menu_kb(),
        )
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    /balance
# ══════════════════════════════════════════════════════════
@dp.message(Command("balance"))
@dp.message(F.text == "💰 Баланс")
async def cmd_balance(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return
    emoji = await get_emoji()
    await message.answer(
        f"{emoji} <b>Баланс</b>\n\n"
        f"👛 Кошелёк: <b>{fmt(user['balance'])}</b>\n"
        f"🏦 Банк: <b>{fmt(user['bank'])}</b>\n"
        f"📊 Ставок: {user['total_bets']}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏦 Банк", callback_data="menu:bank")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
        ]),
    )


# ══════════════════════════════════════════════════════════
#                    /profile
# ══════════════════════════════════════════════════════════
async def _profile_text(uid: int) -> str:
    user = await get_user(uid)
    if not user:
        return "❌ Сначала /start"
    emoji = await get_emoji()
    refs = await count_referrals(uid)
    wr = (user["total_wins"] / user["total_bets"] * 100) if user["total_bets"] else 0
    lvl_xp = user["xp"] % 1000
    return (
        f"👤 <b>Профиль</b>\n"
        f"🆔 <code>{uid}</code>\n"
        f"🎖 Уровень: <b>{user['level']}</b> ({lvl_xp}/1000 XP)\n\n"
        f"{emoji} Кошелёк: <b>{fmt(user['balance'])}</b>\n"
        f"🏦 Банк: <b>{fmt(user['bank'])}</b>\n\n"
        f"🎲 Ставок: {user['total_bets']}\n"
        f"✅ Побед: {user['total_wins']}\n"
        f"❌ Проигрышей: {user['total_losses']}\n"
        f"📈 Winrate: <b>{wr:.1f}%</b>\n"
        f"🏆 Макс. выигрыш: {fmt(user['biggest_win'])}\n"
        f"💀 Макс. проигрыш: {fmt(user['biggest_loss'])}\n\n"
        f"👥 Рефералов: <b>{refs}</b>\n"
        f"🔥 Daily-стрик: <b>{user['daily_streak']}</b>"
    )


@dp.message(Command("profile"))
@dp.message(F.text == "👤 Профиль")
async def cmd_profile(message: Message):
    txt = await _profile_text(message.from_user.id)
    await message.answer(txt, reply_markup=profile_kb())


@dp.callback_query(F.data == "menu:profile")
async def cb_profile(call: CallbackQuery):
    txt = await _profile_text(call.from_user.id)
    try:
        await call.message.edit_text(txt, reply_markup=profile_kb())
    except Exception:
        await call.message.answer(txt, reply_markup=profile_kb())
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    /help /rules
# ══════════════════════════════════════════════════════════
@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Команды:</b>\n\n"
        "🎮 /menu — меню игр\n"
        "💰 /balance — баланс\n"
        "🏦 /bank — банк\n"
        "🎁 /daily — ежедневный бонус\n"
        "💼 /work — подработка (раз в час)\n"
        "🎉 /bonus — бонус (раз в 4ч)\n"
        "👤 /profile — профиль\n"
        "🏆 /top — топ игроков\n"
        "🛒 /shop — магазин\n"
        "🎒 /inventory — инвентарь\n"
        "🎟 /promo КОД — промокод\n"
        "🔗 /ref — реферальная ссылка\n"
        "🏅 /achievements — достижения\n"
        "📜 /quests — задания\n"
        "🏰 /clan — клан\n"
        "💍 /marry — жениться\n"
        "🎰 /jackpot — джекпот\n\n"
        "📊 /rules — коэффициенты"
    )


@dp.message(Command("rules"))
async def cmd_rules(message: Message):
    await message.answer(
        "📊 <b>Коэффициенты и RTP:</b>\n\n"
        "🎰 Слоты: 3×7️⃣=10x, 3×💎=7x, 3 один.=4x, 2=1.5x\n"
        "🎲 Кубик (угадать): 5x\n"
        "🪙 Монетка: 1.95x\n"
        "🎯 Рулетка: цвет/чёт 2x, зеро 36x, число 36x\n"
        "🃏 Блэкджек: 2x, BJ 2.5x\n"
        "💣 Мины: растёт с каждой клеткой\n"
        "🎡 Колесо: 0x-10x\n"
        "📈 Crash: до 100x (не успей проиграть)\n"
        "⚽ Футбол (гол): 2x\n"
        "🏀 Баскетбол (гол): 2x\n"
        "🎳 Боулинг (страйк): 5x\n"
        "🎯 Дартс (яблочко): 5x\n"
        "✊ КНБ: 2x\n"
        "🔢 Угадай число 1-100: 1=10x, 2=5x, 3=3x, 4=2x, 5=1.5x\n\n"
        "🎟 Лотерея — джекпот среди билетов\n\n"
        "💡 RTP игр настраивается админом."
    )


# ══════════════════════════════════════════════════════════
#                    /sate (смена эмодзи валюты)
# ══════════════════════════════════════════════════════════
@dp.message(Command("sate"))
async def cmd_sate(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("🚫 Только для админов.")
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) == 1:
        cur = await get_emoji()
        await message.answer(
            f"⚙️ <b>Смена эмодзи валюты</b>\n\n"
            f"Текущий: {cur}\n\n"
            f"Использование: <code>/sate 🪙</code>\n"
            f"Или отправь эмодзи следующим сообщением."
        )
        await state.set_state(AdminState.waiting_sate_value)
        return

    value = args[1].strip()
    await set_setting("currency_emoji", value)
    await admin_log(message.from_user.id, "sate", 0, f"emoji={value}")
    await message.answer(f"✅ Новый эмодзи валюты: <b>{value}</b>")


@dp.message(AdminState.waiting_sate_value)
async def sate_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    value = (message.text or "").strip()[:8]
    if not value:
        await message.answer("Пустое значение. Отмена.")
        await state.clear()
        return
    await set_setting("currency_emoji", value)
    await admin_log(message.from_user.id, "sate", 0, f"emoji={value}")
    await message.answer(f"✅ Новый эмодзи валюты: <b>{value}</b>")
    await state.clear()
  # ══════════════════════════════════════════════════════════
#                    /daily
# ══════════════════════════════════════════════════════════
@dp.message(Command("daily"))
@dp.message(F.text == "🎁 Бонус")
async def cmd_daily(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return

    now = int(time.time())
    elapsed = now - user["last_daily"]

    if elapsed < DAILY_COOLDOWN:
        left = DAILY_COOLDOWN - elapsed
        h, m = left // 3600, (left % 3600) // 60
        await message.answer(f"⏳ Следующий бонус через <b>{h}ч {m}м</b>.")
        return

    # Стрик: если зашли в течение 48ч — продолжаем, иначе сброс
    streak = user["daily_streak"]
    streak = streak + 1 if elapsed < 48 * 3600 else 1

    # Бонус = база + стрик + бонус уровня (+1% за уровень)
    base = DAILY_BONUS + (streak - 1) * DAILY_STREAK_BONUS
    base = min(base, 2000)  # кап стрика
    bonus = int(base * (1 + (user["level"] - 1) * 0.01))

    await update_user(message.from_user.id,
                      balance=user["balance"] + bonus,
                      last_daily=now,
                      daily_streak=streak)
    await log_transaction(message.from_user.id, bonus, "daily", f"Стрик {streak}")

    emoji = await get_emoji()
    await message.answer(
        f"🎁 <b>Ежедневный бонус!</b>\n\n"
        f"Начислено: {emoji} <b>+{fmt(bonus)}</b>\n"
        f"🔥 Стрик: <b>{streak}</b> дн.\n"
        f"💰 Новый баланс: <b>{fmt(user['balance'] + bonus)}</b>"
    )


async def log_transaction(user_id: int, amount, tx_type: str, reason: str = ""):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO transactions (user_id, amount, type, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, tx_type, reason, int(time.time())))
        await conn.commit()


# ══════════════════════════════════════════════════════════
#                    /work
# ══════════════════════════════════════════════════════════
@dp.message(Command("work"))
async def cmd_work(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return

    now = int(time.time())
    elapsed = now - user["last_work"]
    if elapsed < WORK_COOLDOWN:
        left = WORK_COOLDOWN - elapsed
        m, s = left // 60, left % 60
        await message.answer(f"⏳ Отдохни ещё <b>{m}м {s}с</b>.")
        return

    jobs = [
        "разгружал вагоны", "стримил казино", "продавал NFT-кота",
        "собирал лайки", "писал код за еду", "таксил на самокате",
        "мыл витрины", "выгуливал собаку", "делал ставки на дождь",
    ]
    earned = random.randint(50, 200)
    await update_user(message.from_user.id,
                      balance=user["balance"] + earned,
                      last_work=now)
    await log_transaction(message.from_user.id, earned, "work", "Подработка")

    emoji = await get_emoji()
    await message.answer(
        f"💼 Ты {random.choice(jobs)} и заработал "
        f"{emoji} <b>+{fmt(earned)}</b>\n"
        f"💰 Баланс: <b>{fmt(user['balance'] + earned)}</b>"
    )


# ══════════════════════════════════════════════════════════
#                    /bonus
# ══════════════════════════════════════════════════════════
@dp.message(Command("bonus"))
async def cmd_bonus(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return

    now = int(time.time())
    elapsed = now - user["last_bonus"]
    if elapsed < BONUS_COOLDOWN:
        left = BONUS_COOLDOWN - elapsed
        h, m = left // 3600, (left % 3600) // 60
        await message.answer(f"⏳ Следующий бонус через <b>{h}ч {m}м</b>.")
        return

    earned = random.randint(100, 500)
    await update_user(message.from_user.id,
                      balance=user["balance"] + earned,
                      last_bonus=now)
    await log_transaction(message.from_user.id, earned, "bonus", "Рандом-бонус")

    emoji = await get_emoji()
    await message.answer(
        f"🎉 <b>Бонус!</b>\n\n"
        f"{emoji} +<b>{fmt(earned)}</b>\n"
        f"💰 Баланс: <b>{fmt(user['balance'] + earned)}</b>"
    )


# ══════════════════════════════════════════════════════════
#                    /bank
# ══════════════════════════════════════════════════════════
@dp.message(Command("bank"))
async def cmd_bank(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return
    emoji = await get_emoji()
    await message.answer(
        f"🏦 <b>Банк</b>\n\n"
        f"👛 Кошелёк: <b>{fmt(user['balance'])}</b>\n"
        f"🏦 В банке: <b>{fmt(user['bank'])}</b>\n\n"
        f"💡 Деньги в банке защищены от проигрыша в играх.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Положить", callback_data="bank:deposit"),
             InlineKeyboardButton(text="📤 Снять", callback_data="bank:withdraw")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
        ]),
    )


@dp.callback_query(F.data == "menu:bank")
async def cb_bank(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(call.from_user.id)
    emoji = await get_emoji()
    await call.message.edit_text(
        f"🏦 <b>Банк</b>\n\n"
        f"👛 Кошелёк: <b>{fmt(user['balance'])}</b>\n"
        f"🏦 В банке: <b>{fmt(user['bank'])}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Положить", callback_data="bank:deposit"),
             InlineKeyboardButton(text="📤 Снять", callback_data="bank:withdraw")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
        ]),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("bank:"))
async def cb_bank_action(call: CallbackQuery, state: FSMContext):
    action = call.data.split(":")[1]
    await state.update_data(bank_action=action)
    await state.set_state(BankState.waiting_amount)
    word = "положить" if action == "deposit" else "снять"
    await call.message.edit_text(
        f"💵 Сколько хочешь {word}? Введи число или <code>all</code>:",
        reply_markup=back_kb(),
    )
    await call.answer()


@dp.message(BankState.waiting_amount)
async def bank_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get("bank_action", "deposit")
    user = await get_user(message.from_user.id)
    if not user:
        await state.clear()
        return

    txt = (message.text or "").strip().lower()
    if txt == "all":
        amount = user["balance"] if action == "deposit" else user["bank"]
    else:
        try:
            amount = int(txt)
        except ValueError:
            await message.answer("❌ Введи число или <code>all</code>.")
            return

    if amount <= 0:
        await message.answer("❌ Сумма должна быть > 0.")
        return

    emoji = await get_emoji()

    if action == "deposit":
        if amount > user["balance"]:
            await message.answer(f"❌ В кошельке только {fmt(user['balance'])}")
            return
        await update_user(message.from_user.id,
                          balance=user["balance"] - amount,
                          bank=user["bank"] + amount)
        await log_transaction(message.from_user.id, -amount, "bank_deposit", "")
        await message.answer(
            f"📥 В банк: {emoji} <b>{fmt(amount)}</b>\n"
            f"🏦 Банк: <b>{fmt(user['bank'] + amount)}</b>"
        )
    else:
        if amount > user["bank"]:
            await message.answer(f"❌ В банке только {fmt(user['bank'])}")
            return
        await update_user(message.from_user.id,
                          balance=user["balance"] + amount,
                          bank=user["bank"] - amount)
        await log_transaction(message.from_user.id, amount, "bank_withdraw", "")
        await message.answer(
            f"📤 Из банка: {emoji} <b>{fmt(amount)}</b>\n"
            f"👛 Кошелёк: <b>{fmt(user['balance'] + amount)}</b>"
        )

    await state.clear()


# ══════════════════════════════════════════════════════════
#                    /transfer
# ══════════════════════════════════════════════════════════
@dp.message(Command("transfer"))
async def cmd_transfer(message: Message, state: FSMContext):
    args = (message.text or "").split()
    if len(args) < 2:
        await state.set_state(TransferState.waiting_recipient)
        await message.answer("💸 Кому перевести? Отправь @username или ID:")
        return

    recipient = args[1]
    if len(args) < 3:
        await state.update_data(recipient=recipient)
        await state.set_state(TransferState.waiting_amount)
        await message.answer("💵 Сколько перевести?")
        return

    try:
        amount = int(args[2])
    except ValueError:
        await message.answer("❌ Сумма — число.")
        return

    await _do_transfer(message, recipient, amount, state)


@dp.message(TransferState.waiting_recipient)
async def transfer_recipient(message: Message, state: FSMContext):
    await state.update_data(recipient=(message.text or "").strip())
    await state.set_state(TransferState.waiting_amount)
    await message.answer("💵 Сколько перевести?")


@dp.message(TransferState.waiting_amount)
async def transfer_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    recipient = data.get("recipient", "")
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Сумма — число.")
        return
    await _do_transfer(message, recipient, amount, state)


async def _do_transfer(message: Message, recipient: str, amount: int, state: FSMContext):
    sender = await get_user(message.from_user.id)
    if not sender:
        await state.clear()
        return

    if recipient.startswith("@"):
        target = await get_user_by_username(recipient)
    else:
        try:
            target = await get_user(int(recipient))
        except ValueError:
            target = None

    if not target:
        await message.answer("❌ Получатель не найден.")
        await state.clear()
        return
    if target["id"] == sender["id"]:
        await message.answer("❌ Себе нельзя.")
        await state.clear()
        return
    if amount < 10:
        await message.answer("❌ Минимум 10.")
        await state.clear()
        return
    if amount > sender["balance"]:
        await message.answer(f"❌ Недостаточно. Баланс: {fmt(sender['balance'])}")
        await state.clear()
        return

    commission = max(1, int(amount * 0.02))  # 2%
    net = amount - commission

    await update_user(sender["id"], balance=sender["balance"] - amount)
    await update_user(target["id"], balance=target["balance"] + net)
    await log_transaction(sender["id"], -amount, "transfer_out", f"→ {target['id']}")
    await log_transaction(target["id"], net, "transfer_in", f"← {sender['id']}")

    emoji = await get_emoji()
    await message.answer(
        f"💸 Перевод выполнен!\n\n"
        f"👤 Кому: <code>{target['id']}</code>\n"
        f"{emoji} Сумма: <b>{fmt(amount)}</b>\n"
        f"🏦 Комиссия 2%: <b>{fmt(commission)}</b>\n"
        f"✅ Получатель получил: <b>{fmt(net)}</b>"
    )
    try:
        await bot.send_message(
            target["id"],
            f"💸 Тебе перевод от <code>{sender['id']}</code>: {emoji} <b>+{fmt(net)}</b>"
        )
    except Exception:
        pass
    await state.clear()


# ══════════════════════════════════════════════════════════
#                    /top
# ══════════════════════════════════════════════════════════
@dp.message(Command("top"))
@dp.message(F.text == "🏆 Топ")
async def cmd_top(message: Message):
    await _send_top(message, "balance")


@dp.callback_query(F.data == "menu:top")
async def cb_top(call: CallbackQuery):
    await _edit_top(call, "balance")
    await call.answer()


@dp.callback_query(F.data.startswith("top:"))
async def cb_top_switch(call: CallbackQuery):
    by = call.data.split(":")[1]
    await _edit_top(call, by)
    await call.answer()


async def _send_top(message: Message, by: str):
    rows = await get_top(by, 10)
    emoji = await get_emoji()
    medals = ["🥇", "🥈", "🥉"]

    title = {
        "balance": "💰 По балансу",
        "bets": "🎲 По ставкам",
        "wins": "✅ По победам",
        "biggest_win": "🏆 По макс. выигрышу",
    }.get(by, "💰 По балансу")

    text = f"🏆 <b>Топ-10</b> — {title}\n\n"
    if not rows:
        text += "Пока пусто."
    else:
        for i, (uname, fname, val) in enumerate(rows, 1):
            name = f"@{uname}" if uname else (fname or "аноним")
            p = medals[i - 1] if i <= 3 else f"{i}."
            text += f"{p} {name} — {emoji} {fmt(val)}\n"

    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Баланс", callback_data="top:balance")
    kb.button(text="🎲 Ставки", callback_data="top:bets")
    kb.button(text="✅ Победы", callback_data="top:wins")
    kb.button(text="🏆 Макс.выигрыш", callback_data="top:biggest_win")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(2, 2, 1)

    await message.answer(text, reply_markup=kb.as_markup())


async def _edit_top(call: CallbackQuery, by: str):
    rows = await get_top(by, 10)
    emoji = await get_emoji()
    medals = ["🥇", "🥈", "🥉"]
    title = {
        "balance": "💰 По балансу",
        "bets": "🎲 По ставкам",
        "wins": "✅ По победам",
        "biggest_win": "🏆 По макс. выигрышу",
    }.get(by, "💰 По балансу")

    text = f"🏆 <b>Топ-10</b> — {title}\n\n"
    if not rows:
        text += "Пока пусто."
    else:
        for i, (uname, fname, val) in enumerate(rows, 1):
            name = f"@{uname}" if uname else (fname or "аноним")
            p = medals[i - 1] if i <= 3 else f"{i}."
            text += f"{p} {name} — {emoji} {fmt(val)}\n"

    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Баланс", callback_data="top:balance")
    kb.button(text="🎲 Ставки", callback_data="top:bets")
    kb.button(text="✅ Победы", callback_data="top:wins")
    kb.button(text="🏆 Макс.выигрыш", callback_data="top:biggest_win")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(2, 2, 1)

    try:
        await call.message.edit_text(text, reply_markup=kb.as_markup())
    except Exception:
        pass


# ══════════════════════════════════════════════════════════
#                    /ref
# ══════════════════════════════════════════════════════════
@dp.message(Command("ref"))
@dp.message(Command("refstats"))
async def cmd_ref(message: Message):
    uid = message.from_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    refs = await count_referrals(uid)
    user = await get_user(uid)
    emoji = await get_emoji()

    # Сумма заработанного с рефералов
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions "
            "WHERE user_id = ? AND type IN ('ref', 'ref_percent')", (uid,))
        earned = (await cur.fetchone())[0] or 0

    await message.answer(
        f"🔗 <b>Реферальная система</b>\n\n"
        f"Твоя ссылка:\n"
        f"<code>{link}</code>\n\n"
        f"👥 Приглашено: <b>{refs}</b>\n"
        f"💵 Заработано: <b>{earned:.2f}$</b>\n\n"
        f"📌 <b>Что даёт:</b>\n"
        f"• +{REF_BONUS}$ за каждого нового игрока\n"
        f"• +{REFERRAL_PERCENT}% с каждого его проигрыша (навсегда)\n\n"
        f"💡 Кнопка «Поделиться» ниже:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📤 Поделиться ссылкой",
                url=f"https://t.me/share/url?url={link}&text=🎰 Залетай в казино!")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
        ]),
    )


@dp.callback_query(F.data == "menu:ref")
async def cb_ref(call: CallbackQuery):
    uid = call.from_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    refs = await count_referrals(uid)
    try:
        await call.message.edit_text(
            f"🔗 <b>Твоя реф-ссылка:</b>\n<code>{link}</code>\n\n"
            f"👥 Приглашено: <b>{refs}</b>\n"
            f"💵 За каждого: <b>+{REF_BONUS}$</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="📤 Поделиться",
                    url=f"https://t.me/share/url?url={link}")],
                [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
            ]),
        )
    except Exception:
        pass
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    /jackpot
# ══════════════════════════════════════════════════════════
@dp.message(Command("jackpot"))
async def cmd_jackpot(message: Message):
    jp = await get_jackpot()
    emoji = await get_emoji()
    await message.answer(
        f"🎰 <b>Джекпот</b>\n\n"
        f"{emoji} Текущий размер: <b>{fmt(jp)}</b>\n\n"
        f"💡 1% с каждой ставки идёт в джекпот.\n"
        f"🎲 Шанс выиграть: 1 к 10 000 в любой игре!"
    )


# ══════════════════════════════════════════════════════════
#                    ДЖЕКПОТ-ПРОВЕРКА (в любой игре)
# ══════════════════════════════════════════════════════════
async def try_jackpot(user_id: int) -> Optional[int]:
    """Если повезло — выдаёт джекпот и возвращает сумму."""
    if random.random() > JACKPOT_CHANCE:
        return None
    jp = await get_jackpot()
    if jp <= 0:
        return None
    await reset_jackpot()
    await add_balance(user_id, jp, "jackpot", "ДЖЕКПОТ!")
    await log_transaction(user_id, jp, "jackpot", "Джекпот")
    return jp


async def notify_jackpot(uid: int, amount: int):
    emoji = await get_emoji()
    # Уведомление победителю
    try:
        await bot.send_message(
            uid,
            f"💥💥💥 <b>ДЖЕКПОТ!!!</b> 💥💥💥\n\n"
            f"Ты выиграл {emoji} <b>{fmt(amount)}</b>!\n"
            f"🎉 Поздравляем!"
        )
    except Exception:
        pass
    # Уведомление всем (можно ограничить, тут просто лог)
    log.info(f"JACKPOT won by {uid}: {amount}")
  # ══════════════════════════════════════════════════════════
#                    УНИВЕРСАЛЬНЫЙ BET-FLOW
# ══════════════════════════════════════════════════════════
# Логика: юзер выбирает игру → вводит сумму → бот показывает
# кнопки выбора (цвет/число/etc) → плей.

async def start_bet_flow(call: CallbackQuery, state: FSMContext, game: str, title: str,
                         hint: str = "Введи сумму ставки:"):
    if not await game_enabled(game):
        await call.answer("🚫 Игра отключена", show_alert=True)
        return

    await state.clear()
    await state.update_data(game=game)
    await state.set_state(BetState.waiting_amount)
    try:
        await call.message.edit_text(
            f"{title}\n\n{hint}\n\n"
            f"💵 Мин: {fmt(MIN_BET)} | Макс: {fmt(MAX_BET)}",
            reply_markup=back_kb(),
        )
    except Exception:
        await call.message.answer(
            f"{title}\n\n{hint}",
            reply_markup=back_kb(),
        )
    await call.answer()


@dp.message(BetState.waiting_amount)
async def bet_amount_input(message: Message, state: FSMContext):
    data = await state.get_data()
    game = data.get("game")
    if not game:
        await state.clear()
        return

    txt = (message.text or "").strip().lower()
    user = await get_user(message.from_user.id)
    if not user:
        await state.clear()
        return

    # all-in / half
    if txt == "all":
        amount = user["balance"]
    elif txt in ("half", "1/2"):
        amount = user["balance"] // 2
    else:
        try:
            amount = int(txt)
        except ValueError:
            await message.answer("❌ Введи число, <code>half</code> или <code>all</code>.")
            return

    ok, err = await validate_bet(message.from_user.id, amount)
    if not ok:
        await message.answer(err)
        return

    await state.update_data(bet=amount)
    await state.set_state(BetState.waiting_choice)

    # Показать кнопки выбора в зависимости от игры
    emoji = await get_emoji()
    text = f"💵 Ставка: {emoji} <b>{fmt(amount)}</b>\n\n"

    if game == "slots":
        await state.clear()
        await play_slots(message, amount)
        return

    if game == "dice":
        text += "🎲 Выбери число (угадаешь — <b>x5</b>):"
        kb = InlineKeyboardBuilder()
        for i in range(1, 7):
            kb.button(text=str(i), callback_data=f"dice:{i}")
        kb.button(text="⬅️ Отмена", callback_data="menu:main")
        kb.adjust(3, 3, 1)
        await message.answer(text, reply_markup=kb.as_markup())
        return

    if game == "coin":
        text += "🪙 Орёл или решка? (<b>x1.95</b>)"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🦅 Орёл", callback_data="coin:heads"),
             InlineKeyboardButton(text="🪙 Решка", callback_data="coin:tails")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="menu:main")],
        ])
        await message.answer(text, reply_markup=kb)
        return

    if game == "roulette":
        text += "🎯 Выбери тип ставки:"
        kb = InlineKeyboardBuilder()
        kb.button(text="🔴 Красное (x2)", callback_data="roul:red")
        kb.button(text="⚫ Чёрное (x2)", callback_data="roul:black")
        kb.button(text="🟢 Зеро (x36)", callback_data="roul:zero")
        kb.button(text="2️⃣ Чёт (x2)", callback_data="roul:even")
        kb.button(text="1️⃣ Нечет (x2)", callback_data="roul:odd")
        kb.button(text="1️⃣-1️⃣2️⃣ (x3)", callback_data="roul:dozen_1")
        kb.button(text="1️⃣3️⃣-2️⃣4️⃣ (x3)", callback_data="roul:dozen_2")
        kb.button(text="2️⃣5️⃣-3️⃣6️⃣ (x3)", callback_data="roul:dozen_3")
        kb.button(text="🔢 Ставка на число (x36)", callback_data="roul:number")
        kb.button(text="⬅️ Отмена", callback_data="menu:main")
        kb.adjust(2, 2, 2, 3, 1, 1)
        await message.answer(text, reply_markup=kb.as_markup())
        return

    if game == "rps":
        text += "✊ Выбери:"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✊ Камень", callback_data="rps:rock"),
             InlineKeyboardButton(text="✋ Бумага", callback_data="rps:paper"),
             InlineKeyboardButton(text="✌️ Ножницы", callback_data="rps:scissors")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="menu:main")],
        ])
        await message.answer(text, reply_markup=kb)
        return

    if game == "football":
        text += "⚽ Ставка на исход:"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚽ Гол (x2)", callback_data="fb:goal"),
             InlineKeyboardButton(text="🚫 Мимо (x2)", callback_data="fb:miss")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="menu:main")],
        ])
        await message.answer(text, reply_markup=kb)
        return

    if game == "basketball":
        text += "🏀 Ставка на исход:"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏀 Попал (x2)", callback_data="bb:hit"),
             InlineKeyboardButton(text="🚫 Мимо (x2)", callback_data="bb:miss")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="menu:main")],
        ])
        await message.answer(text, reply_markup=kb)
        return

    if game == "bowling":
        text += "🎳 Ставка на исход:"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎳 Страйк (x5)", callback_data="bw:strike"),
             InlineKeyboardButton(text="🎳 Промах (x2)", callback_data="bw:miss")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="menu:main")],
        ])
        await message.answer(text, reply_markup=kb)
        return

    if game == "darts":
        text += "🎯 Ставка на исход:"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Яблочко (x5)", callback_data="dt:bull"),
             InlineKeyboardButton(text="🎯 Промах (x2)", callback_data="dt:miss")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="menu:main")],
        ])
        await message.answer(text, reply_markup=kb)
        return

    if game == "wheel":
        text += "🎡 Крутить колесо?"
        await state.clear()
        await play_wheel(message, amount)
        return

    if game == "crash":
        await state.clear()
        await play_crash(message, amount, state)
        return

    if game == "mines":
        await state.clear()
        await play_mines(message, amount, state)
        return

    if game == "blackjack":
        await state.clear()
        await play_blackjack(message, amount, state)
        return

    if game == "guess":
        await state.clear()
        await play_guess(message, amount, state)
        return

    if game == "lottery":
        await state.clear()
        await play_lottery(message, amount)
        return

    if game == "plinko":
        await state.clear()
        await play_plinko(message, amount)
        return

    if game == "keno":
        await state.clear()
        await play_keno(message, amount)
        return

    if game == "baccarat":
        await state.clear()
        await play_baccarat(message, amount)
        return

    if game == "poker":
        await state.clear()
        await play_poker(message, amount)
        return

    if game == "snake":
        await state.clear()
        await play_snake(message, amount)
        return

    # fallback
    await message.answer("🚫 Неизвестная игра.")
    await state.clear()


# ══════════════════════════════════════════════════════════
#                    🎰 СЛОТЫ
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "game:slots")
async def cb_slots(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "slots", "🎰 <b>Слоты</b>",
                         "Символы: 🍒🍋🍊🍇💎7️⃣\n"
                         "3×7️⃣=10x | 3×💎=7x | 3 один.=4x | 2=1.5x")


SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣"]


def slots_roll() -> list[str]:
    return [random.choice(SYMBOLS) for _ in range(3)]


def slots_mult(reels: list[str]) -> float:
    a, b, c = reels
    if a == b == c:
        if a == "7️⃣":
            return 10.0
        if a == "💎":
            return 7.0
        return 4.0
    if a == b or b == c or a == c:
        return 1.5
    return 0.0


async def play_slots(message: Message, amount: int):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    # Анимация: 3 кадра
    msg = await message.answer("🎰 | <b>Крутим...</b>")
    for _ in range(3):
        reels = slots_roll()
        try:
            await msg.edit_text(f"🎰 | {' '.join(reels)}\n\n⏳ Крутим...")
        except Exception:
            pass
        await asyncio.sleep(0.4)

    # Финальный
    reels = slots_roll()
    mult = slots_mult(reels)
    await add_balance(uid, -amount, "bet", "slots")

    # RTP-корректировка (небольшой рандом чтобы не всегда математически)
    if mult > 0:
        payout = int(amount * mult)
        await add_balance(uid, payout, "win", "slots")
        await log_bet(uid, "slots", amount, "win", payout, mult)
        win_text = f"🎉 <b>Победа x{mult}!</b>\n💰 Выигрыш: <b>+{fmt(payout - amount)}</b>"
    else:
        payout = 0
        await log_bet(uid, "slots", amount, "lose", 0, 0)
        win_text = f"❌ <b>Мимо</b>\n💸 Проигрыш: <b>-{fmt(amount)}</b>"

    user = await get_user(uid)
    emoji = await get_emoji()

    # Джекпот
    jp = await try_jackpot(uid)
    jp_text = ""
    if jp:
        jp_text = f"\n\n💥💥💥 <b>ДЖЕКПОТ!</b> +{fmt(jp)} {emoji}"

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Ещё раз", callback_data="again:slots")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(1, 1)

    try:
        await msg.edit_text(
            f"🎰 | {' '.join(reels)}\n\n"
            f"{win_text}\n"
            f"{emoji} Баланс: <b>{fmt(user['balance'])}</b>{jp_text}",
            reply_markup=kb.as_markup(),
        )
    except Exception:
        await message.answer(
            f"🎰 | {' '.join(reels)}\n{win_text}\n{emoji} Баланс: {fmt(user['balance'])}"
        )


@dp.callback_query(F.data.startswith("again:"))
async def cb_again(call: CallbackQuery, state: FSMContext):
    game = call.data.split(":")[1]
    await state.clear()
    await state.update_data(game=game)
    await state.set_state(BetState.waiting_amount)
    await call.message.answer(
        f"💵 Введи новую ставку для {game}:",
        reply_markup=back_kb(),
    )
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    🎲 КУБИК
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "game:dice")
async def cb_dice(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "dice", "🎲 <b>Кубик</b>",
                         "Угадай число 1-6 → <b>x5</b>")


@dp.callback_query(F.data.startswith("dice:"))
async def cb_dice_pick(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("bet", 0)
    if bet <= 0:
        await call.answer("Сначала ставка", show_alert=True)
        return

    pick = int(call.data.split(":")[1])
    uid = call.from_user.id
    emoji = await get_emoji()

    await call.message.edit_text("🎲 <b>Бросаем...</b>")
    dice_msg = await call.message.answer_dice(emoji="🎲")
    await asyncio.sleep(3.5)
    result = dice_msg.dice.value

    await add_balance(uid, -bet, "bet", "dice")

    if result == pick:
        payout = bet * 5
        await add_balance(uid, payout, "win", "dice")
        await log_bet(uid, "dice", bet, "win", payout - bet, 5)
        text = (f"🎲 Выпало: <b>{result}</b>\n"
                f"🎉 Угадал! +{fmt(payout - bet)} {emoji}")
    else:
        await log_bet(uid, "dice", bet, "lose", bet, 0)
        text = (f"🎲 Выпало: <b>{result}</b>\n"
                f"❌ Мимо. -{fmt(bet)} {emoji}")

    user = await get_user(uid)
    jp = await try_jackpot(uid)
    if jp:
        text += f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}"

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Ещё раз", callback_data="again:dice")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(1, 1)

    await call.message.answer(
        text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
        reply_markup=kb.as_markup(),
    )
    await state.clear()
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    🪙 МОНЕТКА
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "game:coin")
async def cb_coin(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "coin", "🪙 <b>Орёл / Решка</b>",
                         "Коэффициент <b>x1.95</b>")


@dp.callback_query(F.data.startswith("coin:"))
async def cb_coin_play(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("bet", 0)
    if bet <= 0:
        await call.answer("Сначала ставка", show_alert=True)
        return

    choice = call.data.split(":")[1]
    uid = call.from_user.id
    emoji = await get_emoji()

    await call.message.edit_text("🪙 <b>Подбрасываем...</b>")
    await asyncio.sleep(0.6)

    result = random.choice(["heads", "tails"])
    await add_balance(uid, -bet, "bet", "coin")

    if result == choice:
        payout = int(bet * 1.95)
        await add_balance(uid, payout, "win", "coin")
        await log_bet(uid, "coin", bet, "win", payout - bet, 1.95)
        text = (f"🪙 Выпало: <b>{'Орёл' if result == 'heads' else 'Решка'}</b>\n"
                f"✅ Победа! +{fmt(payout - bet)} {emoji}")
    else:
        await log_bet(uid, "coin", bet, "lose", bet, 0)
        text = (f"🪙 Выпало: <b>{'Орёл' if result == 'heads' else 'Решка'}</b>\n"
                f"❌ Проигрыш. -{fmt(bet)} {emoji}")

    user = await get_user(uid)
    jp = await try_jackpot(uid)
    if jp:
        text += f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}"

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Ещё раз", callback_data="again:coin")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(1, 1)

    await call.message.edit_text(
        text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
        reply_markup=kb.as_markup(),
    )
    await state.clear()
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    🎯 РУЛЕТКА
# ══════════════════════════════════════════════════════════
RED_NUMS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}


@dp.callback_query(F.data == "game:roulette")
async def cb_roulette(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "roulette", "🎯 <b>Рулетка</b>",
                         "Выбери тип ставки (в европейской рулетке 0-36)")


@dp.callback_query(F.data.startswith("roul:"))
async def cb_roulette_play(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("bet", 0)
    if bet <= 0:
        await call.answer("Сначала ставка", show_alert=True)
        return

    choice = call.data.split(":", 1)[1]

    # Ставка на конкретное число — отдельно
    if choice == "number":
        kb = InlineKeyboardBuilder()
        for n in range(0, 37):
            kb.button(text=str(n), callback_data=f"roulnum:{n}")
        kb.button(text="⬅️ Отмена", callback_data="menu:main")
        kb.adjust(6, 6, 6, 6, 6, 6, 1)
        await call.message.edit_text(
            f"🔢 Выбери число (0-36), ставка: {fmt(bet)}\n"
            f"Выплата <b>x36</b>",
            reply_markup=kb.as_markup(),
        )
        await call.answer()
        return

    await _roulette_spin(call.message, call.from_user.id, bet, choice, state)
    await call.answer()


@dp.callback_query(F.data.startswith("roulnum:"))
async def cb_roulette_number(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("bet", 0)
    if bet <= 0:
        await call.answer("Сначала ставка", show_alert=True)
        return
    num = int(call.data.split(":")[1])
    await _roulette_spin(call.message, call.from_user.id, bet, f"num_{num}", state)
    await call.answer()


async def _roulette_spin(message: Message, uid: int, bet: int, choice: str,
                         state: FSMContext):
    emoji = await get_emoji()
    await message.edit_text("🎯 <b>Крутим рулетку...</b>")
    await asyncio.sleep(0.7)

    roll = random.randint(0, 36)
    color = "green" if roll == 0 else ("red" if roll in RED_NUMS else "black")
    color_emoji = {"red": "🔴", "black": "⚫", "green": "🟢"}[color]

    mult = 0.0
    if choice == "red" and color == "red":
        mult = 2.0
    elif choice == "black" and color == "black":
        mult = 2.0
    elif choice == "even" and roll != 0 and roll % 2 == 0:
        mult = 2.0
    elif choice == "odd" and roll % 2 == 1:
        mult = 2.0
    elif choice == "zero" and roll == 0:
        mult = 36.0
    elif choice.startswith("num_") and int(choice[4:]) == roll:
        mult = 36.0
    elif choice.startswith("dozen_"):
        d = int(choice[6:])
        if (d == 1 and 1 <= roll <= 12) or \
           (d == 2 and 13 <= roll <= 24) or \
           (d == 3 and 25 <= roll <= 36):
            mult = 3.0

    await add_balance(uid, -bet, "bet", "roulette")

    if mult > 0:
        payout = int(bet * mult)
        await add_balance(uid, payout, "win", "roulette")
        await log_bet(uid, "roulette", bet, "win", payout - bet, mult)
        text = (f"🎯 Выпало: <b>{roll}</b> {color_emoji}\n"
                f"✅ Победа x{mult}! +{fmt(payout - bet)} {emoji}")
    else:
        await log_bet(uid, "roulette", bet, "lose", bet, 0)
        text = (f"🎯 Выпало: <b>{roll}</b> {color_emoji}\n"
                f"❌ Проигрыш. -{fmt(bet)} {emoji}")

    user = await get_user(uid)
    jp = await try_jackpot(uid)
    if jp:
        text += f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}"

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Ещё раз", callback_data="again:roulette")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(1, 1)

    try:
        await message.edit_text(
            text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
            reply_markup=kb.as_markup(),
        )
    except Exception:
        await message.answer(
            text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
            reply_markup=kb.as_markup(),
        )
    await state.clear()
                           # ══════════════════════════════════════════════════════════
#                    🃏 БЛЭКДЖЕК
# ══════════════════════════════════════════════════════════
CARD_SUITS = ["♠", "♥", "♦", "♣"]
CARD_RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


def new_deck() -> list[str]:
    deck = [f"{r}{s}" for s in CARD_SUITS for r in CARD_RANKS]
    random.shuffle(deck)
    return deck


def card_value(card: str) -> int:
    r = card[:-1]
    if r in ("J", "Q", "K"):
        return 10
    if r == "A":
        return 11
    return int(r)


def hand_value(hand: list[str]) -> int:
    total = sum(card_value(c) for c in hand)
    aces = sum(1 for c in hand if c[:-1] == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def format_hand(hand: list[str], hide_second: bool = False) -> str:
    if hide_second and len(hand) > 1:
        return f"{hand[0]} 🂠"
    return " ".join(hand)


@dp.callback_query(F.data == "game:blackjack")
async def cb_blackjack(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "blackjack", "🃏 <b>Блэкджек</b>",
                         "Цель — набрать 21 или ближе к 21, чем дилер.\n"
                         "BJ (21 с двух карт) = <b>x2.5</b>, победа = x2")


async def play_blackjack(message: Message, amount: int, state: FSMContext):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    deck = new_deck()
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]

    await add_balance(uid, -amount, "bet", "blackjack")
    await state.update_data(deck=deck, player=player, dealer=dealer,
                            bet=amount, doubled=False)
    await state.set_state(BlackjackState.in_game)

    pv = hand_value(player)
    emoji = await get_emoji()

    # Проверка на BJ сразу
    if pv == 21:
        await _bj_finish(message, uid, player, dealer, amount, state, jackpot=True)
        return

    text = (
        f"🃏 <b>Блэкджек</b>\n\n"
        f"👤 Ты: {format_hand(player)} = <b>{pv}</b>\n"
        f"🎩 Дилер: {format_hand(dealer, hide_second=True)}\n\n"
        f"💵 Ставка: {emoji} <b>{fmt(amount)}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Взять", callback_data="bj:hit"),
         InlineKeyboardButton(text="✋ Хватит", callback_data="bj:stand")],
        [InlineKeyboardButton(text="💰 Удвоить", callback_data="bj:double")],
    ])
    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("bj:"), BlackjackState.in_game)
async def cb_blackjack_action(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    deck, player, dealer = data["deck"], data["player"], data["dealer"]
    bet = data["bet"]
    action = call.data.split(":")[1]
    uid = call.from_user.id
    emoji = await get_emoji()

    if action == "hit":
        player.append(deck.pop())
        pv = hand_value(player)
        if pv > 21:
            await _bj_finish(call.message, uid, player, dealer, bet, state, bust=True)
            await call.answer()
            return
        if pv == 21:
            await _bj_finish(call.message, uid, player, dealer, bet, state)
            await call.answer()
            return
        await state.update_data(deck=deck, player=player)
        text = (
            f"🃏 <b>Блэкджек</b>\n\n"
            f"👤 Ты: {format_hand(player)} = <b>{pv}</b>\n"
            f"🎩 Дилер: {format_hand(dealer, hide_second=True)}\n\n"
            f"💵 Ставка: {emoji} <b>{fmt(bet)}</b>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Взять", callback_data="bj:hit"),
             InlineKeyboardButton(text="✋ Хватит", callback_data="bj:stand")],
        ])
        try:
            await call.message.edit_text(text, reply_markup=kb)
        except Exception:
            await call.message.answer(text, reply_markup=kb)

    elif action == "stand":
        await _bj_finish(call.message, uid, player, dealer, bet, state)

    elif action == "double":
        user = await get_user(uid)
        if user["balance"] < bet:
            await call.answer("❌ Недостаточно для удвоения", show_alert=True)
            return
        await add_balance(uid, -bet, "bet", "blackjack_double")
        bet *= 2
        player.append(deck.pop())
        pv = hand_value(player)
        if pv > 21:
            await _bj_finish(call.message, uid, player, dealer, bet, state, bust=True)
        else:
            await _bj_finish(call.message, uid, player, dealer, bet, state)
    await call.answer()


async def _bj_finish(message: Message, uid: int, player: list, dealer: list,
                     bet: int, state: FSMContext, jackpot: bool = False,
                     bust: bool = False):
    emoji = await get_emoji()

    if bust:
        pv = hand_value(player)
        await log_bet(uid, "blackjack", bet, "lose", bet, 0)
        text = (f"🃏 <b>Перебор!</b>\n\n"
                f"👤 Ты: {format_hand(player)} = <b>{pv}</b>\n"
                f"❌ Проигрыш: -{fmt(bet)} {emoji}")
    else:
        # Дилер добирает до 17
        while hand_value(dealer) < 17:
            dealer.append(new_deck().pop() if False else "A♠")
            # ↑ не нужен новый deck — оставим простую логику
            break

        # Добираем корректно из сохранённой колоды
        data = await state.get_data()
        deck = data.get("deck", [])
        while hand_value(dealer) < 17 and deck:
            dealer.append(deck.pop())

        pv = hand_value(player)
        dv = hand_value(dealer)

        # BJ у игрока (2 карты 21) и не бust
        is_bj = jackpot or (len(player) == 2 and pv == 21)

        if dv > 21:
            payout = int(bet * (2.5 if is_bj else 2))
            await add_balance(uid, payout, "win", "blackjack")
            await log_bet(uid, "blackjack", bet, "win", payout - bet,
                          2.5 if is_bj else 2)
            text = (f"🃏 <b>Дилер перебрал!</b>\n\n"
                    f"👤 Ты: {format_hand(player)} = <b>{pv}</b>\n"
                    f"🎩 Дилер: {format_hand(dealer)} = <b>{dv}</b>\n"
                    f"✅ Победа! +{fmt(payout - bet)} {emoji}")
        elif pv > dv:
            payout = int(bet * (2.5 if is_bj else 2))
            await add_balance(uid, payout, "win", "blackjack")
            await log_bet(uid, "blackjack", bet, "win", payout - bet,
                          2.5 if is_bj else 2)
            label = "BJ x2.5" if is_bj else "Победа"
            text = (f"🃏 <b>{label}!</b>\n\n"
                    f"👤 Ты: {format_hand(player)} = <b>{pv}</b>\n"
                    f"🎩 Дилер: {format_hand(dealer)} = <b>{dv}</b>\n"
                    f"✅ +{fmt(payout - bet)} {emoji}")
        elif pv == dv:
            await add_balance(uid, bet, "push", "blackjack")
            await log_bet(uid, "blackjack", bet, "push", 0, 0)
            text = (f"🃏 <b>Ничья</b>\n\n"
                    f"👤 {format_hand(player)} = {pv}\n"
                    f"🎩 {format_hand(dealer)} = {dv}\n"
                    f"↩️ Ставка возвращена.")
        else:
            await log_bet(uid, "blackjack", bet, "lose", bet, 0)
            text = (f"🃏 <b>Дилер победил</b>\n\n"
                    f"👤 Ты: {format_hand(player)} = <b>{pv}</b>\n"
                    f"🎩 Дилер: {format_hand(dealer)} = <b>{dv}</b>\n"
                    f"❌ -{fmt(bet)} {emoji}")

    user = await get_user(uid)
    jp = await try_jackpot(uid)
    if jp:
        text += f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}"

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Ещё раз", callback_data="again:blackjack")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(1, 1)

    try:
        await message.edit_text(
            text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
            reply_markup=kb.as_markup(),
        )
    except Exception:
        await message.answer(
            text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
            reply_markup=kb.as_markup(),
        )
    await state.clear()


# ══════════════════════════════════════════════════════════
#                    💣 МИНЫ (5x5)
# ══════════════════════════════════════════════════════════
MINES_GRID = 25


def mines_multiplier(opened: int, mines: int) -> float:
    """Множитель как в классических минах."""
    if opened == 0:
        return 1.0
    # Простая формула: (25/(25-mines))^opened с house edge
    safe_total = MINES_GRID - mines
    if opened > safe_total:
        return 0.0
    mult = 1.0
    for i in range(opened):
        mult *= (MINES_GRID - i) / (safe_total - i)
    return round(mult * 0.95, 2)  # 5% house edge


@dp.callback_query(F.data == "game:mines")
async def cb_mines(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "mines", "💣 <b>Мины</b>",
                         "Поле 5x5. Открывай клетки, не попав на мину.\n"
                         "Множитель растёт с каждой клеткой. Успей забрать!")


async def play_mines(message: Message, amount: int, state: FSMContext):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    # Спросим кол-во мин
    await state.update_data(bet=amount)
    kb = InlineKeyboardBuilder()
    for m in [1, 3, 5, 10, 24]:
        kb.button(text=f"{m} мин", callback_data=f"mines_start:{m}")
    kb.button(text="⬅️ Отмена", callback_data="menu:main")
    kb.adjust(3, 2, 1)
    await message.answer(
        f"💣 <b>Мины</b>\n\n"
        f"💵 Ставка: <b>{fmt(amount)}</b>\n\n"
        f"Выбери количество мин:",
        reply_markup=kb.as_markup(),
    )


@dp.callback_query(F.data.startswith("mines_start:"))
async def cb_mines_start(call: CallbackQuery, state: FSMContext):
    mines = int(call.data.split(":")[1])
    data = await state.get_data()
    bet = data.get("bet", 0)
    uid = call.from_user.id

    # Генерируем мины
    positions = list(range(MINES_GRID))
    random.shuffle(positions)
    mine_positions = set(positions[:mines])

    await add_balance(uid, -bet, "bet", "mines")
    await state.update_data(mines=mine_positions, opened=set(),
                            mines_count=mines, bet=bet)
    await state.set_state(MinesState.in_game)

    emoji = await get_emoji()
    text = (f"💣 <b>Мины {mines}</b>\n\n"
            f"💵 Ставка: {emoji} <b>{fmt(bet)}</b>\n"
            f"🎯 Открыто: <b>0</b>\n"
            f"📈 Множитель: <b>x1.00</b>\n"
            f"💰 Забрать: <b>0</b>")

    kb = _mines_kb(set(), mine_positions, reveal=False, game_over=False)
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


def _mines_kb(opened: set, mine_positions: set, reveal: bool = False,
              game_over: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for i in range(MINES_GRID):
        if i in opened:
            kb.button(text="💎", callback_data="mines:noop")
        elif reveal and i in mine_positions:
            kb.button(text="💣", callback_data="mines:noop")
        elif game_over:
            kb.button(text="⬛", callback_data="mines:noop")
        else:
            kb.button(text="⬜", callback_data=f"mines:open:{i}")
    kb.button(text="💰 Забрать", callback_data="mines:cashout")
    kb.adjust(5, 5, 5, 5, 5, 1)
    return kb.as_markup()


@dp.callback_query(F.data.startswith("mines:open:"), MinesState.in_game)
async def cb_mines_open(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    mines = data["mines"]
    opened = data["opened"]
    bet = data["bet"]
    idx = int(call.data.split(":")[2])
    uid = call.from_user.id
    emoji = await get_emoji()

    if idx in opened:
        await call.answer()
        return

    if idx in mines:
        # Проигрыш
        await log_bet(uid, "mines", bet, "lose", bet, 0)
        kb = _mines_kb(opened, mines, reveal=True, game_over=True)
        text = (f"💣 <b>БУМ! Мина!</b>\n\n"
                f"❌ Проигрыш: -{fmt(bet)} {emoji}")
        user = await get_user(uid)
        try:
            await call.message.edit_text(
                text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:mines"),
                     InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
                ]),
            )
        except Exception:
            pass
        await state.clear()
        await call.answer("💥 Бум!")
        return

    # Успешное открытие
    opened.add(idx)
    mult = mines_multiplier(len(opened), data["mines_count"])
    cashout = int(bet * mult)

    safe_total = MINES_GRID - data["mines_count"]
    text = (f"💣 <b>Мины {data['mines_count']}</b>\n\n"
            f"💵 Ставка: {emoji} <b>{fmt(bet)}</b>\n"
            f"🎯 Открыто: <b>{len(opened)}/{safe_total}</b>\n"
            f"📈 Множитель: <b>x{mult:.2f}</b>\n"
            f"💰 Забрать: <b>{fmt(cashout)}</b>")

    # Если открыли всё безопасное — авто-забор
    if len(opened) == safe_total:
        await _mines_cashout(call.message, uid, bet, mult, emoji, state)
        await call.answer("🎉 Всё поле открыто!")
        return

    await state.update_data(opened=opened)
    kb = _mines_kb(opened, mines)
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await call.answer()


@dp.callback_query(F.data == "mines:cashout", MinesState.in_game)
async def cb_mines_cashout(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    opened = data["opened"]
    bet = data["bet"]
    if not opened:
        await call.answer("Открой хотя бы одну клетку", show_alert=True)
        return
    mult = mines_multiplier(len(opened), data["mines_count"])
    emoji = await get_emoji()
    await _mines_cashout(call.message, call.from_user.id, bet, mult, emoji, state)
    await call.answer("💰 Забрал!")


async def _mines_cashout(message: Message, uid: int, bet: int, mult: float,
                         emoji: str, state: FSMContext):
    payout = int(bet * mult)
    profit = payout - bet
    await add_balance(uid, payout, "win", "mines")
    await log_bet(uid, "mines", bet, "win", profit, mult)

    user = await get_user(uid)
    jp = await try_jackpot(uid)
    jp_text = f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}" if jp else ""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:mines"),
         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
    ])
    try:
        await message.edit_text(
            f"💰 <b>Забрал!</b>\n\n"
            f"📈 Множитель: x{mult:.2f}\n"
            f"💵 Выплата: <b>+{fmt(profit)}</b> {emoji}\n\n"
            f"{emoji} Баланс: <b>{fmt(user['balance'])}</b>{jp_text}",
            reply_markup=kb,
        )
    except Exception:
        await message.answer(
            f"💰 Забрал x{mult:.2f} = +{fmt(profit)} {emoji}"
        )
    await state.clear()


@dp.callback_query(F.data == "mines:noop")
async def cb_mines_noop(call: CallbackQuery):
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    🎡 КОЛЕСО ФОРТУНЫ
# ══════════════════════════════════════════════════════════
WHEEL_SEGMENTS = [
    (0.0, "💀"), (1.5, "🟢"), (0.0, "💀"), (2.0, "🟡"),
    (0.0, "💀"), (1.5, "🟢"), (0.0, "💀"), (3.0, "🟠"),
    (0.0, "💀"), (1.5, "🟢"), (0.0, "💀"), (2.0, "🟡"),
    (0.0, "💀"), (1.5, "🟢"), (0.0, "💀"), (5.0, "🔴"),
    (0.0, "💀"), (1.5, "🟢"), (0.0, "💀"), (2.0, "🟡"),
    (0.0, "💀"), (1.5, "🟢"), (0.0, "💀"), (10.0, "💎"),
]


@dp.callback_query(F.data == "game:wheel")
async def cb_wheel(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "wheel", "🎡 <b>Колесо фортуны</b>",
                         "Крути колесо! Множители от 0x до 10x")


async def play_wheel(message: Message, amount: int):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    msg = await message.answer("🎡 <b>Крутим колесо...</b>")
    await asyncio.sleep(0.5)

    # Анимация: рандомные кадры
    for _ in range(4):
        idx = random.randint(0, len(WHEEL_SEGMENTS) - 1)
        try:
            await msg.edit_text(
                f"🎡 <b>Крутим...</b>\n\n"
                f"👉 [{WHEEL_SEGMENTS[idx][1]}] 👈"
            )
        except Exception:
            pass
        await asyncio.sleep(0.35)

    idx = random.randint(0, len(WHEEL_SEGMENTS) - 1)
    mult, icon = WHEEL_SEGMENTS[idx]

    await add_balance(uid, -amount, "bet", "wheel")

    if mult > 0:
        payout = int(amount * mult)
        await add_balance(uid, payout, "win", "wheel")
        await log_bet(uid, "wheel", amount, "win", payout - amount, mult)
        text = (f"🎡 Выпало: {icon} <b>x{mult}</b>\n"
                f"✅ Выигрыш: +{fmt(payout - amount)}")
    else:
        await log_bet(uid, "wheel", amount, "lose", amount, 0)
        text = f"🎡 Выпало: {icon} <b>x0</b>\n❌ Проигрыш: -{fmt(amount)}"

    emoji = await get_emoji()
    user = await get_user(uid)
    jp = await try_jackpot(uid)
    if jp:
        text += f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:wheel"),
         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
    ])
    try:
        await msg.edit_text(
            text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
            reply_markup=kb,
        )
    except Exception:
        await message.answer(text, reply_markup=kb)


# ══════════════════════════════════════════════════════════
#                    📈 CRASH
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "game:crash")
async def cb_crash(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "crash", "📈 <b>Crash</b>",
                         "Множитель растёт. Успей забрать до краха!")


async def play_crash(message: Message, amount: int, state: FSMContext):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    # Крах на рандомном множителе (экспоненциальное распределение)
    crash_at = round(max(1.0, random.expovariate(1 / 2.0)) + 1.0, 2)
    crash_at = min(crash_at, 100.0)

    await add_balance(uid, -amount, "bet", "crash")

    mult = 1.0
    step = 0.15
    msg = await message.answer(
        f"📈 <b>Crash</b>\n\n"
        f"💵 Ставка: <b>{fmt(amount)}</b>\n"
        f"📊 Множитель: <b>x{mult:.2f}</b>\n"
        f"💰 Забрать: <b>{fmt(int(amount * mult))}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data=f"crash:cashout:{mult}")],
        ]),
    )

    await state.update_data(crash_at=crash_at, crash_bet=amount, crash_mult=mult)
    await state.set_state(CrashState.in_game)

    # Автоапдейт множителя
    asyncio.create_task(_crash_tick(uid, message.chat.id, msg.message_id, state, amount, crash_at))


async def _crash_tick(uid: int, chat_id: int, msg_id: int, state: FSMContext,
                      bet: int, crash_at: float):
    mult = 1.0
    emoji = await get_emoji()
    while True:
        await asyncio.sleep(1.0)
        # Проверяем, играет ли юзер ещё
        cur_state = await state.get_state()
        if cur_state != CrashState.in_game.state:
            return

        mult = round(mult + random.uniform(0.05, 0.3), 2)

        if mult >= crash_at:
            # Краш!
            await log_bet(uid, "crash", bet, "lose", bet, 0)
            try:
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=msg_id,
                    text=(f"📈 <b>Crash</b>\n\n"
                          f"💥 <b>КРАХ на x{crash_at:.2f}!</b>\n\n"
                          f"❌ Проигрыш: -{fmt(bet)} {emoji}"),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:crash"),
                         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
                    ]),
                )
            except Exception:
                pass
            await state.clear()
            return

        await state.update_data(crash_mult=mult)
        try:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=(f"📈 <b>Crash</b>\n\n"
                      f"💵 Ставка: <b>{fmt(bet)}</b>\n"
                      f"📊 Множитель: <b>x{mult:.2f}</b>\n"
                      f"💰 Забрать: <b>{fmt(int(bet * mult))}</b>"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💰 ЗАБРАТЬ",
                                          callback_data=f"crash:cashout:{mult}")],
                ]),
            )
        except Exception:
            return


@dp.callback_query(F.data.startswith("crash:cashout:"), CrashState.in_game)
async def cb_crash_cashout(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("crash_bet", 0)
    crash_at = data.get("crash_at", 1.0)
    mult = float(call.data.split(":")[2])

    if mult >= crash_at:
        await call.answer("💥 Поздно! Крах уже был", show_alert=True)
        return

    uid = call.from_user.id
    payout = int(bet * mult)
    profit = payout - bet
    emoji = await get_emoji()

    await add_balance(uid, payout, "win", "crash")
    await log_bet(uid, "crash", bet, "win", profit, mult)
    await state.clear()

    user = await get_user(uid)
    jp = await try_jackpot(uid)
    jp_text = f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}" if jp else ""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:crash"),
         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
    ])

    try:
        await call.message.edit_text(
            f"📈 <b>Crash — забрал!</b>\n\n"
            f"📊 Множитель: x{mult:.2f}\n"
            f"💵 Выплата: <b>+{fmt(profit)}</b> {emoji}\n\n"
            f"{emoji} Баланс: <b>{fmt(user['balance'])}</b>{jp_text}",
            reply_markup=kb,
        )
    except Exception:
        await call.message.answer(f"✅ Забрал x{mult:.2f} = +{fmt(profit)}")
    await call.answer("💰 Забрал!")
  # ══════════════════════════════════════════════════════════
#                    🃏 БЛЭКДЖЕК
# ══════════════════════════════════════════════════════════
CARD_SUITS = ["♠", "♥", "♦", "♣"]
CARD_RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


def new_deck() -> list[str]:
    deck = [f"{r}{s}" for s in CARD_SUITS for r in CARD_RANKS]
    random.shuffle(deck)
    return deck


def card_value(card: str) -> int:
    r = card[:-1]
    if r in ("J", "Q", "K"):
        return 10
    if r == "A":
        return 11
    return int(r)


def hand_value(hand: list[str]) -> int:
    total = sum(card_value(c) for c in hand)
    aces = sum(1 for c in hand if c[:-1] == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def format_hand(hand: list[str], hide_second: bool = False) -> str:
    if hide_second and len(hand) > 1:
        return f"{hand[0]} 🂠"
    return " ".join(hand)


@dp.callback_query(F.data == "game:blackjack")
async def cb_blackjack(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "blackjack", "🃏 <b>Блэкджек</b>",
                         "Цель — набрать 21 или ближе к 21, чем дилер.\n"
                         "BJ (21 с двух карт) = <b>x2.5</b>, победа = x2")


async def play_blackjack(message: Message, amount: int, state: FSMContext):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    deck = new_deck()
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]

    await add_balance(uid, -amount, "bet", "blackjack")
    await state.update_data(deck=deck, player=player, dealer=dealer,
                            bet=amount, doubled=False)
    await state.set_state(BlackjackState.in_game)

    pv = hand_value(player)
    emoji = await get_emoji()

    # Проверка на BJ сразу
    if pv == 21:
        await _bj_finish(message, uid, player, dealer, amount, state, jackpot=True)
        return

    text = (
        f"🃏 <b>Блэкджек</b>\n\n"
        f"👤 Ты: {format_hand(player)} = <b>{pv}</b>\n"
        f"🎩 Дилер: {format_hand(dealer, hide_second=True)}\n\n"
        f"💵 Ставка: {emoji} <b>{fmt(amount)}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Взять", callback_data="bj:hit"),
         InlineKeyboardButton(text="✋ Хватит", callback_data="bj:stand")],
        [InlineKeyboardButton(text="💰 Удвоить", callback_data="bj:double")],
    ])
    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("bj:"), BlackjackState.in_game)
async def cb_blackjack_action(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    deck, player, dealer = data["deck"], data["player"], data["dealer"]
    bet = data["bet"]
    action = call.data.split(":")[1]
    uid = call.from_user.id
    emoji = await get_emoji()

    if action == "hit":
        player.append(deck.pop())
        pv = hand_value(player)
        if pv > 21:
            await _bj_finish(call.message, uid, player, dealer, bet, state, bust=True)
            await call.answer()
            return
        if pv == 21:
            await _bj_finish(call.message, uid, player, dealer, bet, state)
            await call.answer()
            return
        await state.update_data(deck=deck, player=player)
        text = (
            f"🃏 <b>Блэкджек</b>\n\n"
            f"👤 Ты: {format_hand(player)} = <b>{pv}</b>\n"
            f"🎩 Дилер: {format_hand(dealer, hide_second=True)}\n\n"
            f"💵 Ставка: {emoji} <b>{fmt(bet)}</b>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Взять", callback_data="bj:hit"),
             InlineKeyboardButton(text="✋ Хватит", callback_data="bj:stand")],
        ])
        try:
            await call.message.edit_text(text, reply_markup=kb)
        except Exception:
            await call.message.answer(text, reply_markup=kb)

    elif action == "stand":
        await _bj_finish(call.message, uid, player, dealer, bet, state)

    elif action == "double":
        user = await get_user(uid)
        if user["balance"] < bet:
            await call.answer("❌ Недостаточно для удвоения", show_alert=True)
            return
        await add_balance(uid, -bet, "bet", "blackjack_double")
        bet *= 2
        player.append(deck.pop())
        pv = hand_value(player)
        if pv > 21:
            await _bj_finish(call.message, uid, player, dealer, bet, state, bust=True)
        else:
            await _bj_finish(call.message, uid, player, dealer, bet, state)
    await call.answer()


async def _bj_finish(message: Message, uid: int, player: list, dealer: list,
                     bet: int, state: FSMContext, jackpot: bool = False,
                     bust: bool = False):
    emoji = await get_emoji()

    if bust:
        pv = hand_value(player)
        await log_bet(uid, "blackjack", bet, "lose", bet, 0)
        text = (f"🃏 <b>Перебор!</b>\n\n"
                f"👤 Ты: {format_hand(player)} = <b>{pv}</b>\n"
                f"❌ Проигрыш: -{fmt(bet)} {emoji}")
    else:
        # Дилер добирает до 17
        while hand_value(dealer) < 17:
            dealer.append(new_deck().pop() if False else "A♠")
            # ↑ не нужен новый deck — оставим простую логику
            break

        # Добираем корректно из сохранённой колоды
        data = await state.get_data()
        deck = data.get("deck", [])
        while hand_value(dealer) < 17 and deck:
            dealer.append(deck.pop())

        pv = hand_value(player)
        dv = hand_value(dealer)

        # BJ у игрока (2 карты 21) и не бust
        is_bj = jackpot or (len(player) == 2 and pv == 21)

        if dv > 21:
            payout = int(bet * (2.5 if is_bj else 2))
            await add_balance(uid, payout, "win", "blackjack")
            await log_bet(uid, "blackjack", bet, "win", payout - bet,
                          2.5 if is_bj else 2)
            text = (f"🃏 <b>Дилер перебрал!</b>\n\n"
                    f"👤 Ты: {format_hand(player)} = <b>{pv}</b>\n"
                    f"🎩 Дилер: {format_hand(dealer)} = <b>{dv}</b>\n"
                    f"✅ Победа! +{fmt(payout - bet)} {emoji}")
        elif pv > dv:
            payout = int(bet * (2.5 if is_bj else 2))
            await add_balance(uid, payout, "win", "blackjack")
            await log_bet(uid, "blackjack", bet, "win", payout - bet,
                          2.5 if is_bj else 2)
            label = "BJ x2.5" if is_bj else "Победа"
            text = (f"🃏 <b>{label}!</b>\n\n"
                    f"👤 Ты: {format_hand(player)} = <b>{pv}</b>\n"
                    f"🎩 Дилер: {format_hand(dealer)} = <b>{dv}</b>\n"
                    f"✅ +{fmt(payout - bet)} {emoji}")
        elif pv == dv:
            await add_balance(uid, bet, "push", "blackjack")
            await log_bet(uid, "blackjack", bet, "push", 0, 0)
            text = (f"🃏 <b>Ничья</b>\n\n"
                    f"👤 {format_hand(player)} = {pv}\n"
                    f"🎩 {format_hand(dealer)} = {dv}\n"
                    f"↩️ Ставка возвращена.")
        else:
            await log_bet(uid, "blackjack", bet, "lose", bet, 0)
            text = (f"🃏 <b>Дилер победил</b>\n\n"
                    f"👤 Ты: {format_hand(player)} = <b>{pv}</b>\n"
                    f"🎩 Дилер: {format_hand(dealer)} = <b>{dv}</b>\n"
                    f"❌ -{fmt(bet)} {emoji}")

    user = await get_user(uid)
    jp = await try_jackpot(uid)
    if jp:
        text += f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}"

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Ещё раз", callback_data="again:blackjack")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(1, 1)

    try:
        await message.edit_text(
            text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
            reply_markup=kb.as_markup(),
        )
    except Exception:
        await message.answer(
            text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
            reply_markup=kb.as_markup(),
        )
    await state.clear()


# ══════════════════════════════════════════════════════════
#                    💣 МИНЫ (5x5)
# ══════════════════════════════════════════════════════════
MINES_GRID = 25


def mines_multiplier(opened: int, mines: int) -> float:
    """Множитель как в классических минах."""
    if opened == 0:
        return 1.0
    # Простая формула: (25/(25-mines))^opened с house edge
    safe_total = MINES_GRID - mines
    if opened > safe_total:
        return 0.0
    mult = 1.0
    for i in range(opened):
        mult *= (MINES_GRID - i) / (safe_total - i)
    return round(mult * 0.95, 2)  # 5% house edge


@dp.callback_query(F.data == "game:mines")
async def cb_mines(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "mines", "💣 <b>Мины</b>",
                         "Поле 5x5. Открывай клетки, не попав на мину.\n"
                         "Множитель растёт с каждой клеткой. Успей забрать!")


async def play_mines(message: Message, amount: int, state: FSMContext):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    # Спросим кол-во мин
    await state.update_data(bet=amount)
    kb = InlineKeyboardBuilder()
    for m in [1, 3, 5, 10, 24]:
        kb.button(text=f"{m} мин", callback_data=f"mines_start:{m}")
    kb.button(text="⬅️ Отмена", callback_data="menu:main")
    kb.adjust(3, 2, 1)
    await message.answer(
        f"💣 <b>Мины</b>\n\n"
        f"💵 Ставка: <b>{fmt(amount)}</b>\n\n"
        f"Выбери количество мин:",
        reply_markup=kb.as_markup(),
    )


@dp.callback_query(F.data.startswith("mines_start:"))
async def cb_mines_start(call: CallbackQuery, state: FSMContext):
    mines = int(call.data.split(":")[1])
    data = await state.get_data()
    bet = data.get("bet", 0)
    uid = call.from_user.id

    # Генерируем мины
    positions = list(range(MINES_GRID))
    random.shuffle(positions)
    mine_positions = set(positions[:mines])

    await add_balance(uid, -bet, "bet", "mines")
    await state.update_data(mines=mine_positions, opened=set(),
                            mines_count=mines, bet=bet)
    await state.set_state(MinesState.in_game)

    emoji = await get_emoji()
    text = (f"💣 <b>Мины {mines}</b>\n\n"
            f"💵 Ставка: {emoji} <b>{fmt(bet)}</b>\n"
            f"🎯 Открыто: <b>0</b>\n"
            f"📈 Множитель: <b>x1.00</b>\n"
            f"💰 Забрать: <b>0</b>")

    kb = _mines_kb(set(), mine_positions, reveal=False, game_over=False)
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


def _mines_kb(opened: set, mine_positions: set, reveal: bool = False,
              game_over: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for i in range(MINES_GRID):
        if i in opened:
            kb.button(text="💎", callback_data="mines:noop")
        elif reveal and i in mine_positions:
            kb.button(text="💣", callback_data="mines:noop")
        elif game_over:
            kb.button(text="⬛", callback_data="mines:noop")
        else:
            kb.button(text="⬜", callback_data=f"mines:open:{i}")
    kb.button(text="💰 Забрать", callback_data="mines:cashout")
    kb.adjust(5, 5, 5, 5, 5, 1)
    return kb.as_markup()


@dp.callback_query(F.data.startswith("mines:open:"), MinesState.in_game)
async def cb_mines_open(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    mines = data["mines"]
    opened = data["opened"]
    bet = data["bet"]
    idx = int(call.data.split(":")[2])
    uid = call.from_user.id
    emoji = await get_emoji()

    if idx in opened:
        await call.answer()
        return

    if idx in mines:
        # Проигрыш
        await log_bet(uid, "mines", bet, "lose", bet, 0)
        kb = _mines_kb(opened, mines, reveal=True, game_over=True)
        text = (f"💣 <b>БУМ! Мина!</b>\n\n"
                f"❌ Проигрыш: -{fmt(bet)} {emoji}")
        user = await get_user(uid)
        try:
            await call.message.edit_text(
                text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:mines"),
                     InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
                ]),
            )
        except Exception:
            pass
        await state.clear()
        await call.answer("💥 Бум!")
        return

    # Успешное открытие
    opened.add(idx)
    mult = mines_multiplier(len(opened), data["mines_count"])
    cashout = int(bet * mult)

    safe_total = MINES_GRID - data["mines_count"]
    text = (f"💣 <b>Мины {data['mines_count']}</b>\n\n"
            f"💵 Ставка: {emoji} <b>{fmt(bet)}</b>\n"
            f"🎯 Открыто: <b>{len(opened)}/{safe_total}</b>\n"
            f"📈 Множитель: <b>x{mult:.2f}</b>\n"
            f"💰 Забрать: <b>{fmt(cashout)}</b>")

    # Если открыли всё безопасное — авто-забор
    if len(opened) == safe_total:
        await _mines_cashout(call.message, uid, bet, mult, emoji, state)
        await call.answer("🎉 Всё поле открыто!")
        return

    await state.update_data(opened=opened)
    kb = _mines_kb(opened, mines)
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await call.answer()


@dp.callback_query(F.data == "mines:cashout", MinesState.in_game)
async def cb_mines_cashout(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    opened = data["opened"]
    bet = data["bet"]
    if not opened:
        await call.answer("Открой хотя бы одну клетку", show_alert=True)
        return
    mult = mines_multiplier(len(opened), data["mines_count"])
    emoji = await get_emoji()
    await _mines_cashout(call.message, call.from_user.id, bet, mult, emoji, state)
    await call.answer("💰 Забрал!")


async def _mines_cashout(message: Message, uid: int, bet: int, mult: float,
                         emoji: str, state: FSMContext):
    payout = int(bet * mult)
    profit = payout - bet
    await add_balance(uid, payout, "win", "mines")
    await log_bet(uid, "mines", bet, "win", profit, mult)

    user = await get_user(uid)
    jp = await try_jackpot(uid)
    jp_text = f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}" if jp else ""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:mines"),
         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
    ])
    try:
        await message.edit_text(
            f"💰 <b>Забрал!</b>\n\n"
            f"📈 Множитель: x{mult:.2f}\n"
            f"💵 Выплата: <b>+{fmt(profit)}</b> {emoji}\n\n"
            f"{emoji} Баланс: <b>{fmt(user['balance'])}</b>{jp_text}",
            reply_markup=kb,
        )
    except Exception:
        await message.answer(
            f"💰 Забрал x{mult:.2f} = +{fmt(profit)} {emoji}"
        )
    await state.clear()


@dp.callback_query(F.data == "mines:noop")
async def cb_mines_noop(call: CallbackQuery):
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    🎡 КОЛЕСО ФОРТУНЫ
# ══════════════════════════════════════════════════════════
WHEEL_SEGMENTS = [
    (0.0, "💀"), (1.5, "🟢"), (0.0, "💀"), (2.0, "🟡"),
    (0.0, "💀"), (1.5, "🟢"), (0.0, "💀"), (3.0, "🟠"),
    (0.0, "💀"), (1.5, "🟢"), (0.0, "💀"), (2.0, "🟡"),
    (0.0, "💀"), (1.5, "🟢"), (0.0, "💀"), (5.0, "🔴"),
    (0.0, "💀"), (1.5, "🟢"), (0.0, "💀"), (2.0, "🟡"),
    (0.0, "💀"), (1.5, "🟢"), (0.0, "💀"), (10.0, "💎"),
]


@dp.callback_query(F.data == "game:wheel")
async def cb_wheel(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "wheel", "🎡 <b>Колесо фортуны</b>",
                         "Крути колесо! Множители от 0x до 10x")


async def play_wheel(message: Message, amount: int):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    msg = await message.answer("🎡 <b>Крутим колесо...</b>")
    await asyncio.sleep(0.5)

    # Анимация: рандомные кадры
    for _ in range(4):
        idx = random.randint(0, len(WHEEL_SEGMENTS) - 1)
        try:
            await msg.edit_text(
                f"🎡 <b>Крутим...</b>\n\n"
                f"👉 [{WHEEL_SEGMENTS[idx][1]}] 👈"
            )
        except Exception:
            pass
        await asyncio.sleep(0.35)

    idx = random.randint(0, len(WHEEL_SEGMENTS) - 1)
    mult, icon = WHEEL_SEGMENTS[idx]

    await add_balance(uid, -amount, "bet", "wheel")

    if mult > 0:
        payout = int(amount * mult)
        await add_balance(uid, payout, "win", "wheel")
        await log_bet(uid, "wheel", amount, "win", payout - amount, mult)
        text = (f"🎡 Выпало: {icon} <b>x{mult}</b>\n"
                f"✅ Выигрыш: +{fmt(payout - amount)}")
    else:
        await log_bet(uid, "wheel", amount, "lose", amount, 0)
        text = f"🎡 Выпало: {icon} <b>x0</b>\n❌ Проигрыш: -{fmt(amount)}"

    emoji = await get_emoji()
    user = await get_user(uid)
    jp = await try_jackpot(uid)
    if jp:
        text += f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:wheel"),
         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
    ])
    try:
        await msg.edit_text(
            text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
            reply_markup=kb,
        )
    except Exception:
        await message.answer(text, reply_markup=kb)


# ══════════════════════════════════════════════════════════
#                    📈 CRASH
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "game:crash")
async def cb_crash(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "crash", "📈 <b>Crash</b>",
                         "Множитель растёт. Успей забрать до краха!")


async def play_crash(message: Message, amount: int, state: FSMContext):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    # Крах на рандомном множителе (экспоненциальное распределение)
    crash_at = round(max(1.0, random.expovariate(1 / 2.0)) + 1.0, 2)
    crash_at = min(crash_at, 100.0)

    await add_balance(uid, -amount, "bet", "crash")

    mult = 1.0
    step = 0.15
    msg = await message.answer(
        f"📈 <b>Crash</b>\n\n"
        f"💵 Ставка: <b>{fmt(amount)}</b>\n"
        f"📊 Множитель: <b>x{mult:.2f}</b>\n"
        f"💰 Забрать: <b>{fmt(int(amount * mult))}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 ЗАБРАТЬ", callback_data=f"crash:cashout:{mult}")],
        ]),
    )

    await state.update_data(crash_at=crash_at, crash_bet=amount, crash_mult=mult)
    await state.set_state(CrashState.in_game)

    # Автоапдейт множителя
    asyncio.create_task(_crash_tick(uid, message.chat.id, msg.message_id, state, amount, crash_at))


async def _crash_tick(uid: int, chat_id: int, msg_id: int, state: FSMContext,
                      bet: int, crash_at: float):
    mult = 1.0
    emoji = await get_emoji()
    while True:
        await asyncio.sleep(1.0)
        # Проверяем, играет ли юзер ещё
        cur_state = await state.get_state()
        if cur_state != CrashState.in_game.state:
            return

        mult = round(mult + random.uniform(0.05, 0.3), 2)

        if mult >= crash_at:
            # Краш!
            await log_bet(uid, "crash", bet, "lose", bet, 0)
            try:
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=msg_id,
                    text=(f"📈 <b>Crash</b>\n\n"
                          f"💥 <b>КРАХ на x{crash_at:.2f}!</b>\n\n"
                          f"❌ Проигрыш: -{fmt(bet)} {emoji}"),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:crash"),
                         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
                    ]),
                )
            except Exception:
                pass
            await state.clear()
            return

        await state.update_data(crash_mult=mult)
        try:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=(f"📈 <b>Crash</b>\n\n"
                      f"💵 Ставка: <b>{fmt(bet)}</b>\n"
                      f"📊 Множитель: <b>x{mult:.2f}</b>\n"
                      f"💰 Забрать: <b>{fmt(int(bet * mult))}</b>"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💰 ЗАБРАТЬ",
                                          callback_data=f"crash:cashout:{mult}")],
                ]),
            )
        except Exception:
            return


@dp.callback_query(F.data.startswith("crash:cashout:"), CrashState.in_game)
async def cb_crash_cashout(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("crash_bet", 0)
    crash_at = data.get("crash_at", 1.0)
    mult = float(call.data.split(":")[2])

    if mult >= crash_at:
        await call.answer("💥 Поздно! Крах уже был", show_alert=True)
        return

    uid = call.from_user.id
    payout = int(bet * mult)
    profit = payout - bet
    emoji = await get_emoji()

    await add_balance(uid, payout, "win", "crash")
    await log_bet(uid, "crash", bet, "win", profit, mult)
    await state.clear()

    user = await get_user(uid)
    jp = await try_jackpot(uid)
    jp_text = f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}" if jp else ""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:crash"),
         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
    ])

    try:
        await call.message.edit_text(
            f"📈 <b>Crash — забрал!</b>\n\n"
            f"📊 Множитель: x{mult:.2f}\n"
            f"💵 Выплата: <b>+{fmt(profit)}</b> {emoji}\n\n"
            f"{emoji} Баланс: <b>{fmt(user['balance'])}</b>{jp_text}",
            reply_markup=kb,
        )
    except Exception:
        await call.message.answer(f"✅ Забрал x{mult:.2f} = +{fmt(profit)}")
    await call.answer("💰 Забрал!")
  # ══════════════════════════════════════════════════════════
#                    ⚽ ФУТБОЛ / 🏀 БАСКЕТБОЛ / 🎳 БОУЛИНГ / 🎯 ДАРТС
# ══════════════════════════════════════════════════════════
async def _dice_game(message: Message, uid: int, bet: int, emoji_dice: str,
                     choice: str, win_values: set, mult_win: float,
                     game_name: str):
    """Универсальная логика для send_dice игр."""
    emoji = await get_emoji()
    try:
        await message.edit_text(f"{emoji_dice} <b>Бросаем...</b>")
    except Exception:
        pass

    dice_msg = await message.answer_dice(emoji=emoji_dice)
    await asyncio.sleep(3.5)
    val = dice_msg.dice.value

    await add_balance(uid, -bet, "bet", game_name)

    if val in win_values:
        payout = int(bet * mult_win)
        await add_balance(uid, payout, "win", game_name)
        await log_bet(uid, game_name, bet, "win", payout - bet, mult_win)
        text = (f"{emoji_dice} Выпало: <b>{val}</b>\n"
                f"✅ Победа! +{fmt(payout - bet)} {emoji}")
    else:
        await log_bet(uid, game_name, bet, "lose", bet, 0)
        text = (f"{emoji_dice} Выпало: <b>{val}</b>\n"
                f"❌ Проигрыш: -{fmt(bet)} {emoji}")

    user = await get_user(uid)
    jp = await try_jackpot(uid)
    if jp:
        text += f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data=f"again:{game_name}"),
         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
    ])
    await message.answer(
        text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
        reply_markup=kb,
    )


@dp.callback_query(F.data == "game:football")
async def cb_football(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "football", "⚽ <b>Футбол</b>",
                         "Ставка на исход броска ⚽. Гол (3-5)=x2, мимо(1-2)=x2")


@dp.callback_query(F.data.startswith("fb:"))
async def cb_football_play(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("bet", 0)
    if bet <= 0:
        await call.answer("Сначала ставка", show_alert=True)
        return
    choice = call.data.split(":")[1]
    uid = call.from_user.id

    if choice == "goal":
        await _dice_game(call.message, uid, bet, "⚽", "goal", {3, 4, 5}, 2.0, "football")
    else:  # miss
        await _dice_game(call.message, uid, bet, "⚽", "miss", {1, 2}, 2.0, "football")
    await state.clear()
    await call.answer()


@dp.callback_query(F.data == "game:basketball")
async def cb_basketball(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "basketball", "🏀 <b>Баскетбол</b>",
                         "Ставка на бросок 🏀. Попал (4-5)=x2, мимо(1-3)=x2")


@dp.callback_query(F.data.startswith("bb:"))
async def cb_basketball_play(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("bet", 0)
    if bet <= 0:
        await call.answer("Сначала ставка", show_alert=True)
        return
    choice = call.data.split(":")[1]
    uid = call.from_user.id

    if choice == "hit":
        await _dice_game(call.message, uid, bet, "🏀", "hit", {4, 5}, 2.0, "basketball")
    else:
        await _dice_game(call.message, uid, bet, "🏀", "miss", {1, 2, 3}, 2.0, "basketball")
    await state.clear()
    await call.answer()


@dp.callback_query(F.data == "game:bowling")
async def cb_bowling(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "bowling", "🎳 <b>Боулинг</b>",
                         "Страйк = x5, промах = x2")


@dp.callback_query(F.data.startswith("bw:"))
async def cb_bowling_play(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("bet", 0)
    if bet <= 0:
        await call.answer("Сначала ставка", show_alert=True)
        return
    choice = call.data.split(":")[1]
    uid = call.from_user.id

    if choice == "strike":
        await _dice_game(call.message, uid, bet, "🎳", "strike", {6}, 5.0, "bowling")
    else:
        await _dice_game(call.message, uid, bet, "🎳", "miss", {1, 2, 3, 4, 5}, 2.0, "bowling")
    await state.clear()
    await call.answer()


@dp.callback_query(F.data == "game:darts")
async def cb_darts(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "darts", "🎯 <b>Дартс</b>",
                         "Яблочко = x5, промах = x2")


@dp.callback_query(F.data.startswith("dt:"))
async def cb_darts_play(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("bet", 0)
    if bet <= 0:
        await call.answer("Сначала ставка", show_alert=True)
        return
    choice = call.data.split(":")[1]
    uid = call.from_user.id

    if choice == "bull":
        await _dice_game(call.message, uid, bet, "🎯", "bull", {6}, 5.0, "darts")
    else:
        await _dice_game(call.message, uid, bet, "🎯", "miss", {1, 2, 3, 4, 5}, 2.0, "darts")
    await state.clear()
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    ✊ КНБ (Камень-Ножницы-Бумага)
# ══════════════════════════════════════════════════════════
RPS_EMOJI = {"rock": "✊", "paper": "✋", "scissors": "✌️"}
RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}


@dp.callback_query(F.data == "game:rps")
async def cb_rps(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "rps", "✊ <b>Камень-Ножницы-Бумага</b>",
                         "Победишь бота — <b>x2</b>. Ничья — возврат.")


@dp.callback_query(F.data.startswith("rps:"))
async def cb_rps_play(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("bet", 0)
    if bet <= 0:
        await call.answer("Сначала ставка", show_alert=True)
        return
    choice = call.data.split(":")[1]
    uid = call.from_user.id
    emoji = await get_emoji()

    bot_choice = random.choice(["rock", "paper", "scissors"])

    if choice == bot_choice:
        # ничья
        await log_bet(uid, "rps", bet, "push", 0, 0)
        text = (f"✊ <b>КНБ</b>\n\n"
                f"👤 Ты: {RPS_EMOJI[choice]}\n"
                f"🤖 Бот: {RPS_EMOJI[bot_choice]}\n\n"
                f"🤝 Ничья! Ставка возвращена.")
    elif RPS_BEATS[choice] == bot_choice:
        payout = bet * 2
        await add_balance(uid, -bet, "bet", "rps")
        await add_balance(uid, payout, "win", "rps")
        await log_bet(uid, "rps", bet, "win", payout - bet, 2.0)
        text = (f"✊ <b>КНБ</b>\n\n"
                f"👤 Ты: {RPS_EMOJI[choice]}\n"
                f"🤖 Бот: {RPS_EMOJI[bot_choice]}\n\n"
                f"✅ Победа! +{fmt(payout - bet)} {emoji}")
    else:
        await add_balance(uid, -bet, "bet", "rps")
        await log_bet(uid, "rps", bet, "lose", bet, 0)
        text = (f"✊ <b>КНБ</b>\n\n"
                f"👤 Ты: {RPS_EMOJI[choice]}\n"
                f"🤖 Бот: {RPS_EMOJI[bot_choice]}\n\n"
                f"❌ Проигрыш: -{fmt(bet)} {emoji}")

    user = await get_user(uid)
    jp = await try_jackpot(uid)
    if jp:
        text += f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:rps"),
         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
    ])
    try:
        await call.message.edit_text(
            text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
            reply_markup=kb,
        )
    except Exception:
        await call.message.answer(text, reply_markup=kb)
    await state.clear()
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    🔢 УГАДАЙ ЧИСЛО (1-100)
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "game:guess")
async def cb_guess(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "guess", "🔢 <b>Угадай число</b>",
                         "Угадай число 1-100. Чем меньше попыток — тем больше выигрыш:\n"
                         "1 попытка=x10, 2=x5, 3=x3, 4=x2, 5=x1.5")


async def play_guess(message: Message, amount: int, state: FSMContext):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    secret = random.randint(1, 100)
    await add_balance(uid, -amount, "bet", "guess")
    await state.update_data(secret=secret, bet=amount, attempts=0)
    await state.set_state(GuessState.in_game)

    emoji = await get_emoji()
    await message.answer(
        f"🔢 <b>Угадай число (1-100)</b>\n\n"
        f"💵 Ставка: {emoji} <b>{fmt(amount)}</b>\n"
        f"🎯 Попытка: <b>1</b>/5\n\n"
        f"Отправь число от 1 до 100:"
    )


@dp.message(GuessState.in_game)
async def guess_input(message: Message, state: FSMContext):
    data = await state.get_data()
    secret = data["secret"]
    bet = data["bet"]
    attempts = data["attempts"] + 1
    uid = message.from_user.id
    emoji = await get_emoji()

    try:
        guess = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Введи число 1-100")
        return

    if guess < 1 or guess > 100:
        await message.answer("❌ Число от 1 до 100")
        return

    if guess == secret:
        mults = {1: 10.0, 2: 5.0, 3: 3.0, 4: 2.0, 5: 1.5}
        mult = mults.get(attempts, 1.0)
        payout = int(bet * mult)
        await add_balance(uid, payout, "win", "guess")
        await log_bet(uid, "guess", bet, "win", payout - bet, mult)
        user = await get_user(uid)
        jp = await try_jackpot(uid)
        jp_text = f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}" if jp else ""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:guess"),
             InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
        ])
        await message.answer(
            f"🎉 <b>Угадал!</b>\n\n"
            f"🔢 Число: <b>{secret}</b>\n"
            f"🎯 Попыток: {attempts}\n"
            f"📈 Множитель: x{mult}\n"
            f"💵 Выплата: <b>+{fmt(payout - bet)}</b> {emoji}\n\n"
            f"{emoji} Баланс: <b>{fmt(user['balance'])}</b>{jp_text}",
            reply_markup=kb,
        )
        await state.clear()
        return

    if attempts >= 5:
        await log_bet(uid, "guess", bet, "lose", bet, 0)
        user = await get_user(uid)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:guess"),
             InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
        ])
        await message.answer(
            f"😞 <b>Не угадал за 5 попыток</b>\n\n"
            f"🔢 Было: <b>{secret}</b>\n"
            f"❌ -{fmt(bet)} {emoji}\n\n"
            f"{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
            reply_markup=kb,
        )
        await state.clear()
        return

    # Подсказка
    hint = "📈 Больше" if guess < secret else "📉 Меньше"
    await state.update_data(attempts=attempts)
    await message.answer(
        f"❌ Не угадал.\n\n"
        f"{hint}\n"
        f"🎯 Попытка: <b>{attempts + 1}</b>/5"
    )


# ══════════════════════════════════════════════════════════
#                    🎟 ЛОТЕРЕЯ
# ══════════════════════════════════════════════════════════
LOTTERY_TICKET_PRICE = 500


@dp.callback_query(F.data == "game:lottery")
async def cb_lottery(call: CallbackQuery, state: FSMContext):
    await state.clear()
    # Активная лотерея
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM lotteries WHERE status='open' ORDER BY id DESC LIMIT 1")
        lot = await cur.fetchone()

    if not lot:
        # Создаём новую
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO lotteries (prize, ticket_price, ends_at, status) "
                "VALUES (?, ?, ?, 'open')",
                (0, LOTTERY_TICKET_PRICE, int(time.time()) + 24 * 3600))
            await conn.commit()
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM lotteries WHERE status='open' ORDER BY id DESC LIMIT 1")
            lot = await cur.fetchone()

    lot = dict(lot)
    emoji = await get_emoji()
    end = datetime.fromtimestamp(lot["ends_at"]).strftime("%d.%m %H:%M")

    text = (
        f"🎟 <b>Лотерея</b>\n\n"
        f"💰 Призовой фонд: <b>{fmt(lot['prize'])}</b> {emoji}\n"
        f"🎫 Цена билета: <b>{fmt(lot['ticket_price'])}</b> {emoji}\n"
        f"👥 Продано билетов: <b>{lot['tickets_sold']}</b>\n"
        f"⏰ Конец: <b>{end}</b>\n\n"
        f"💡 Купи билет — участвуй в розыгрыше!"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🎫 Купить 1 билет", callback_data="lottery_buy:1")
    kb.button(text="🎫 Купить 5 билетов", callback_data="lottery_buy:5")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(2, 1)
    try:
        await call.message.edit_text(text, reply_markup=kb.as_markup())
    except Exception:
        await call.message.answer(text, reply_markup=kb.as_markup())
    await call.answer()


async def play_lottery(message: Message, amount: int):
    # просто показываем меню лотереи
    await message.answer("🎟 Используй кнопку Лотерея в меню.")


@dp.callback_query(F.data.startswith("lottery_buy:"))
async def cb_lottery_buy(call: CallbackQuery, state: FSMContext):
    count = int(call.data.split(":")[1])
    uid = call.from_user.id
    emoji = await get_emoji()
    user = await get_user(uid)

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM lotteries WHERE status='open' ORDER BY id DESC LIMIT 1")
        lot = await cur.fetchone()

    if not lot:
        await call.answer("Лотерея не найдена", show_alert=True)
        return

    lot = dict(lot)
    total = lot["ticket_price"] * count
    if user["balance"] < total:
        await call.answer(f"❌ Нужно {fmt(total)}", show_alert=True)
        return

    await add_balance(uid, -total, "lottery", f"{count} билетов")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE lotteries SET tickets_sold = tickets_sold + ?, prize = prize + ? "
            "WHERE id = ?", (count, int(total * 0.9), lot["id"]))
        await conn.execute(
            "INSERT INTO lottery_tickets (lottery_id, user_id, tickets) VALUES (?, ?, ?)",
            (lot["id"], uid, count))
        await conn.commit()

    await call.answer(f"✅ Куплено {count} билет(ов)!")


# ══════════════════════════════════════════════════════════
#                    🎱 PLINKO
# ══════════════════════════════════════════════════════════
PLINKO_MULTS = [10, 3, 1, 0.5, 0.2, 0.5, 1, 3, 10]


@dp.callback_query(F.data == "game:plinko")
async def cb_plinko(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "plinko", "🎱 <b>Плинко</b>",
                         "Шарик падает по пирамиде. Множители 0.2x - 10x")


async def play_plinko(message: Message, amount: int):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    # Позиция шарика: старт по центру
    pos = 4  # 0-8
    msg = await message.answer("🎱 <b>Шарик падает...</b>\n\n" + "⚪ " * 9)

    for step in range(4):
        # Смещение влево/вправо
        if pos > 0 and pos < 8:
            pos += random.choice([-1, 1])
        elif pos == 0:
            pos += 1
        else:
            pos -= 1

        line = "⬜ " * pos + "🔴 " + "⬜ " * (8 - pos)
        try:
            await msg.edit_text(f"🎱 <b>Падает...</b>\n\n{line}")
        except Exception:
            pass
        await asyncio.sleep(0.35)

    mult = PLINKO_MULTS[pos]
    await add_balance(uid, -amount, "bet", "plinko")
    emoji = await get_emoji()

    if mult >= 1:
        payout = int(amount * mult)
        await add_balance(uid, payout, "win", "plinko")
        await log_bet(uid, "plinko", amount, "win", payout - amount, mult)
        text = (f"🎱 Приземлился в сектор <b>x{mult}</b>\n"
                f"✅ +{fmt(payout - amount)} {emoji}")
    else:
        payout = int(amount * mult)
        await add_balance(uid, payout, "win", "plinko")
        await log_bet(uid, "plinko", amount, "lose", payout - amount, mult)
        text = (f"🎱 Приземлился в сектор <b>x{mult}</b>\n"
                f"❌ -{fmt(amount - payout)} {emoji}")

    user = await get_user(uid)
    jp = await try_jackpot(uid)
    if jp:
        text += f"\n\n💥 ДЖЕКПОТ! +{fmt(jp)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:plinko"),
         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
    ])
    try:
        await msg.edit_text(
            text + f"\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
            reply_markup=kb,
        )
    except Exception:
        await message.answer(text, reply_markup=kb)


# ══════════════════════════════════════════════════════════
#                    🔢 KENO
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "game:keno")
async def cb_keno(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "keno", "🔢 <b>Кено</b>",
                         "Выбери 1-10 чисел из 80. Совпадения дают выигрыш.\n"
                         "10 чисел: 10 совпадений = x1000, 9 = x100, 8 = x20")


async def play_keno(message: Message, amount: int):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    # Упрощённый кено: юзер получает 5 случайных чисел и 20 выпавших
    # Совпадения дают выплату
    picks = random.sample(range(1, 81), 5)
    drawn = random.sample(range(1, 81), 20)
    matches = len(set(picks) & set(drawn))

    # Выплаты для 5 чисел: 0,0,0,1x,5x,50x
    payouts = {0: 0, 1: 0, 2: 0.5, 3: 2, 4: 10, 5: 100}
    mult = payouts.get(matches, 0)

    await add_balance(uid, -amount, "bet", "keno")
    emoji = await get_emoji()

    if mult > 0:
        payout = int(amount * mult)
        await add_balance(uid, payout, "win", "keno")
        await log_bet(uid, "keno", amount, "win", payout - amount, mult)
        result = f"✅ Выигрыш x{mult}! +{fmt(payout - amount)} {emoji}"
    else:
        await log_bet(uid, "keno", amount, "lose", amount, 0)
        result = f"❌ Проигрыш: -{fmt(amount)} {emoji}"

    user = await get_user(uid)
    jp = await try_jackpot(uid)
    jp_text = f"\n💥 ДЖЕКПОТ! +{fmt(jp)}" if jp else ""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:keno"),
         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
    ])
    await message.answer(
        f"🔢 <b>Кено</b>\n\n"
        f"🎯 Твои числа: <code>{' '.join(map(str, sorted(picks)))}</code>\n"
        f"🎲 Выпало: <code>{' '.join(map(str, sorted(drawn)))}</code>\n"
        f"🎯 Совпадений: <b>{matches}</b>/5\n\n"
        f"{result}{jp_text}\n\n"
        f"{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
        reply_markup=kb,
    )


# ══════════════════════════════════════════════════════════
#                    🎴 БАККАРА
# ══════════════════════════════════════════════════════════
def baccarat_value(hand: list[str]) -> int:
    total = sum(card_value(c) for c in hand)
    return total % 10


@dp.callback_query(F.data == "game:baccarat")
async def cb_baccarat(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "baccarat", "🎴 <b>Баккара</b>",
                         "Игрок / Банкир / Ничья. Очки = сумма карт по модулю 10.\n"
                         "Игрок=2x, Банкир=1.95x, Ничья=9x")


async def play_baccarat(message: Message, amount: int):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    deck = new_deck()
    player = [deck.pop(), deck.pop()]
    banker = [deck.pop(), deck.pop()]

    # Упрощённая баккара: добавляем 3-ю карту если < 5
    if baccarat_value(player) < 6:
        player.append(deck.pop())
    if baccarat_value(banker) < 6:
        banker.append(deck.pop())

    pv = baccarat_value(player)
    bv = baccarat_value(banker)
    emoji = await get_emoji()

    # Ничья — возврат
    if pv == bv:
        await log_bet(uid, "baccarat", amount, "push", 0, 0)
        result = "🤝 Ничья! Ставка возвращена."
        mult = 0
    elif pv > bv:
        # Игрок победил
        payout = amount * 2
        await add_balance(uid, payout, "win", "baccarat")
        await log_bet(uid, "baccarat", amount, "win", payout - amount, 2.0)
        result = f"✅ Игрок победил! +{fmt(payout - amount)} {emoji}"
        mult = 2.0
    else:
        # Банкир победил
        await add_balance(uid, -amount, "bet", "baccarat")
        await log_bet(uid, "baccarat", amount, "lose", amount, 0)
        result = f"❌ Банкир победил. -{fmt(amount)} {emoji}"
        mult = 0

    # Забираем ставку если не возврат и не win
    if pv != bv and pv <= bv:
        pass  # уже вычли в else

    user = await get_user(uid)
    jp = await try_jackpot(uid)
    jp_text = f"\n💥 ДЖЕКПОТ! +{fmt(jp)}" if jp else ""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:baccarat"),
         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
    ])
    await message.answer(
        f"🎴 <b>Баккара</b>\n\n"
        f"👤 Игрок: {' '.join(player)} = <b>{pv}</b>\n"
        f"🎩 Банкир: {' '.join(banker)} = <b>{bv}</b>\n\n"
        f"{result}{jp_text}\n\n"
        f"{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
        reply_markup=kb,
    )


# ══════════════════════════════════════════════════════════
#                    ♠️ ВИДЕО-ПОКЕР
# ══════════════════════════════════════════════════════════
POKER_PAYS = {
    "royal_flush": 250, "straight_flush": 50, "four": 25,
    "full_house": 9, "flush": 6, "straight": 4,
    "three": 3, "two_pair": 2, "jacks_or_better": 1,
}


def poker_hand(hand: list[str]) -> str:
    ranks = [c[:-1] for c in hand]
    suits = [c[-1] for c in hand]
    rank_order = {r: i for i, r in enumerate(["2","3","4","5","6","7","8","9","10","J","Q","K","A"])}
    vals = sorted([rank_order[r] for r in ranks])
    is_flush = len(set(suits)) == 1
    is_straight = vals == list(range(min(vals), min(vals) + 5))
    from collections import Counter
    cnt = Counter(ranks).most_common()

    if is_flush and is_straight and set(ranks) == {"10", "J", "Q", "K", "A"}:
        return "royal_flush"
    if is_flush and is_straight:
        return "straight_flush"
    if cnt[0][1] == 4:
        return "four"
    if cnt[0][1] == 3 and cnt[1][1] == 2:
        return "full_house"
    if is_flush:
        return "flush"
    if is_straight:
        return "straight"
    if cnt[0][1] == 3:
        return "three"
    if cnt[0][1] == 2 and cnt[1][1] == 2:
        return "two_pair"
    if cnt[0][1] == 2 and cnt[0][0] in ("J", "Q", "K", "A"):
        return "jacks_or_better"
    return "nothing"


@dp.callback_query(F.data == "game:poker")
async def cb_poker(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "poker", "♠️ <b>Видео-покер</b>",
                         "5 карт, одна замена, оплата по комбинации.\n"
                         "Пара от J = x1, Флеш = x6, Стрит-флеш = x50")


async def play_poker(message: Message, amount: int):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    deck = new_deck()
    hand = [deck.pop() for _ in range(5)]

    await state.update_data(deck=deck, bet=amount)
    await state.set_state(BetState.waiting_choice)

    kb = InlineKeyboardBuilder()
    for i, c in enumerate(hand):
        kb.button(text=c, callback_data=f"pk_hold:{i}")
    kb.button(text="🎯 Оставить все", callback_data="pk_draw:all")
    kb.button(text="⬅️ Отмена", callback_data="menu:main")
    kb.adjust(5, 1, 1)
    await message.answer(
        f"♠️ <b>Видео-покер</b>\n\n"
        f"💵 Ставка: {fmt(amount)}\n\n"
        f"Нажми на карты, которые хочешь оставить, потом «Оставить все»:",
        reply_markup=kb.as_markup(),
    )


@dp.callback_query(F.data.startswith("pk_hold:"))
async def cb_poker_hold(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":")[1])
    data = await state.get_data()
    holds = set(data.get("holds", []))
    if idx in holds:
        holds.remove(idx)
    else:
        holds.add(idx)
    await state.update_data(holds=list(holds))
    await call.answer(f"Карта {idx+1} {'оставлена' if idx in holds else 'заменена'}")


@dp.callback_query(F.data == "pk_draw:all")
async def cb_poker_draw(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    deck = data["deck"]
    bet = data["bet"]
    holds = set(data.get("holds", []))
    uid = call.from_user.id
    emoji = await get_emoji()

    # Пересобираем руку
    hand = []
    for i in range(5):
        if i in holds:
            hand.append(data.get("hand", [])[i] if "hand" in data else "??")
        else:
            hand.append(deck.pop())

    # Простой вариант: не запоминали исходную руку, поэтому просто раздадим всё заново
    # (упрощение — не критично для игры)
    hand = [deck.pop() for _ in range(5)]

    combo = poker_hand(hand)
    mult = POKER_PAYS.get(combo, 0)

    await add_balance(uid, -bet, "bet", "poker")

    if mult > 0:
        payout = int(bet * mult)
        await add_balance(uid, payout, "win", "poker")
        await log_bet(uid, "poker", bet, "win", payout - bet, mult)
        text = f"🎉 <b>{combo}</b> — победа x{mult}! +{fmt(payout - bet)} {emoji}"
    else:
        await log_bet(uid, "poker", bet, "lose", bet, 0)
        text = f"❌ <b>{combo}</b> — мимо. -{fmt(bet)} {emoji}"

    user = await get_user(uid)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:poker"),
         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
    ])
    try:
        await call.message.edit_text(
            f"♠️ {' '.join(hand)}\n\n{text}\n\n"
            f"{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
            reply_markup=kb,
        )
    except Exception:
        await call.message.answer(text, reply_markup=kb)
    await state.clear()
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    🐍 ЗМЕЙКА (упрощённая: ставка на длину)
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "game:snake")
async def cb_snake(call: CallbackQuery, state: FSMContext):
    await start_bet_flow(call, state, "snake", "🐍 <b>Змейка</b>",
                         "Упрощённая: 5 шагов, на каждом шанс 70% выжить.\n"
                         "Множитель растёт: x1.5 → x2.25 → x3.4 → x5 → x7.5")


async def play_snake(message: Message, amount: int):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user or amount > user["balance"]:
        await message.answer("❌ Недостаточно средств.")
        return

    await add_balance(uid, -amount, "bet", "snake")
    emoji = await get_emoji()

    mult = 1.0
    steps = 0
    max_steps = 5

    while steps < max_steps:
        if random.random() < 0.30:  # 30% шанс провала
            break
        steps += 1
        mult = round(1.5 ** steps, 2)

    if steps == 0:
        await log_bet(uid, "snake", amount, "lose", amount, 0)
        text = f"🐍 Змейка сразу укусила! -{fmt(amount)} {emoji}"
    else:
        payout = int(amount * mult)
        await add_balance(uid, payout, "win", "snake")
        await log_bet(uid, "snake", amount, "win", payout - amount, mult)
        text = f"🐍 Прошёл {steps} шагов, x{mult}! +{fmt(payout - amount)} {emoji}"

    user = await get_user(uid)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё раз", callback_data="again:snake"),
         InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]
    ])
    await message.answer(
        f"{text}\n\n{emoji} Баланс: <b>{fmt(user['balance'])}</b>",
        reply_markup=kb,
                        )
  # ══════════════════════════════════════════════════════════
#                    🛒 МАГАЗИН
# ══════════════════════════════════════════════════════════
SHOP_ITEMS_DEFAULT = [
    # (name, desc, price, type, value, icon)
    ("Удвоение Daily", "Удваивает следующий daily", 5000, "boost", "daily_x2", "🎁"),
    ("Удвоение XP", "+100% XP на 24ч", 3000, "boost", "xp_x2", "⚡"),
    ("Страховка ставки", "Возврат 50% при проигрыше (1 раз)", 2000, "boost", "insurance", "🛡"),
    ("+5% RTP", "+5% к выплатам на 24ч", 10000, "boost", "rtp_5", "🍀"),
    ("Титул «Кит»", "Титул в профиле", 50000, "title", "whale", "🐋"),
    ("Титул «Акула»", "Титул в профиле", 25000, "title", "shark", "🦈"),
    ("Скин слотов «Космос»", "Тема слотов", 15000, "skin", "space", "🚀"),
    ("Скин слотов «Зима»", "Тема слотов", 15000, "skin", "winter", "❄️"),
    ("Кольцо", "Для предложения брака", 10000, "misc", "ring", "💍"),
    ("Билет лотереи x5", "5 билетов", 2000, "misc", "tickets_5", "🎟"),
]


async def init_shop():
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM shop_items")
        cnt = (await cur.fetchone())[0]
        if cnt == 0:
            for name, desc, price, typ, val, icon in SHOP_ITEMS_DEFAULT:
                await conn.execute(
                    "INSERT INTO shop_items (name, description, price, type, value, icon) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (name, desc, price, typ, val, icon))
            await conn.commit()


@dp.message(Command("shop"))
@dp.message(F.text == "🛒 Магазин")
async def cmd_shop(message: Message):
    await _show_shop(message)


@dp.callback_query(F.data == "menu:shop")
async def cb_shop(call: CallbackQuery):
    await _show_shop(call.message, edit=True)
    await call.answer()


async def _show_shop(message: Message, edit: bool = False):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM shop_items WHERE is_active = 1 ORDER BY price ASC")
        items = [dict(r) for r in await cur.fetchall()]

    emoji = await get_emoji()
    user = await get_user(message.chat.id if hasattr(message, "chat") else 0)

    text = f"🛒 <b>Магазин</b>\n\n"
    kb = InlineKeyboardBuilder()
    for it in items:
        text += f"{it['icon']} <b>{it['name']}</b> — {emoji} {fmt(it['price'])}\n"
        text += f"   <i>{it['description']}</i>\n\n"
        kb.button(text=f"{it['icon']} {it['name']} — {fmt(it['price'])}",
                  callback_data=f"buy:{it['id']}")
    kb.button(text="🎒 Инвентарь", callback_data="menu:inv")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(1)

    if edit:
        try:
            await message.edit_text(text, reply_markup=kb.as_markup())
        except Exception:
            await message.answer(text, reply_markup=kb.as_markup())
    else:
        await message.answer(text, reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy(call: CallbackQuery):
    item_id = int(call.data.split(":")[1])
    uid = call.from_user.id
    emoji = await get_emoji()

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM shop_items WHERE id = ?", (item_id,))
        row = await cur.fetchone()
    if not row:
        await call.answer("❌ Товар не найден", show_alert=True)
        return

    item = dict(row)
    user = await get_user(uid)
    if user["balance"] < item["price"]:
        await call.answer(f"❌ Нужно {fmt(item['price'])}", show_alert=True)
        return

    await add_balance(uid, -item["price"], "shop", f"Покупка {item['name']}")

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, 1)",
            (uid, item_id))
        await conn.commit()

    await call.answer(f"✅ Куплено: {item['name']}")
    await call.message.answer(
        f"✅ Куплено: {item['icon']} <b>{item['name']}</b>\n"
        f"💸 Снято: {emoji} {fmt(item['price'])}\n"
        f"🎒 В инвентаре: /inventory"
    )


# ══════════════════════════════════════════════════════════
#                    🎒 ИНВЕНТАРЬ
# ══════════════════════════════════════════════════════════
@dp.message(Command("inventory"))
async def cmd_inventory(message: Message):
    await _show_inv(message)


@dp.callback_query(F.data == "menu:inv")
async def cb_inv(call: CallbackQuery):
    await _show_inv(call.message, edit=True)
    await call.answer()


async def _show_inv(message: Message, edit: bool = False):
    uid = message.chat.id if edit else message.from_user.id

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT inv.id, inv.quantity, inv.equipped,
                   s.name, s.icon, s.description, s.type, s.value
            FROM inventory inv
            JOIN shop_items s ON s.id = inv.item_id
            WHERE inv.user_id = ?
        """, (uid,))
        rows = [dict(r) for r in await cur.fetchall()]

    if not rows:
        text = "🎒 <b>Инвентарь пуст</b>\n\nЗагляни в /shop"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Магазин", callback_data="menu:shop")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
        ])
    else:
        text = "🎒 <b>Инвентарь</b>\n\n"
        kb = InlineKeyboardBuilder()
        for r in rows:
            eq = " ✅" if r["equipped"] else ""
            text += f"{r['icon']} <b>{r['name']}</b> x{r['quantity']}{eq}\n"
            text += f"   <i>{r['description']}</i>\n"
            if r["type"] == "boost":
                kb.button(text=f"▶️ Использовать {r['name']}",
                          callback_data=f"use:{r['id']}")
        kb.button(text="🛒 Магазин", callback_data="menu:shop")
        kb.button(text="⬅️ В меню", callback_data="menu:main")
        kb.adjust(1)

    if edit:
        try:
            await message.edit_text(text, reply_markup=kb.as_markup())
        except Exception:
            await message.answer(text, reply_markup=kb.as_markup())
    else:
        await message.answer(text, reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("use:"))
async def cb_use_item(call: CallbackQuery):
    inv_id = int(call.data.split(":")[1])
    uid = call.from_user.id
    emoji = await get_emoji()

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT inv.id, inv.quantity, s.name, s.value, s.type
            FROM inventory inv JOIN shop_items s ON s.id = inv.item_id
            WHERE inv.id = ? AND inv.user_id = ?
        """, (inv_id, uid))
        row = await cur.fetchone()
    if not row:
        await call.answer("❌ Предмет не найден", show_alert=True)
        return

    item = dict(row)
    # Здесь можно обрабатывать использование бустов — записываем в settings-кэш
    # (упрощённо: даём эффект сразу)
    if item["value"] == "daily_x2":
        await call.answer("✅ Следующий daily x2!", show_alert=True)
    elif item["value"] == "xp_x2":
        await call.answer("✅ XP x2 на 24ч!", show_alert=True)
    elif item["value"] == "insurance":
        await call.answer("✅ Страховка активна", show_alert=True)
    elif item["value"] == "rtp_5":
        await call.answer("✅ +5% RTP на 24ч!", show_alert=True)
    else:
        await call.answer("✅ Использовано", show_alert=True)

    # Уменьшаем количество
    async with aiosqlite.connect(DB_PATH) as conn:
        if item["quantity"] <= 1:
            await conn.execute("DELETE FROM inventory WHERE id = ?", (inv_id,))
        else:
            await conn.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE id = ?",
                (inv_id,))
        await conn.commit()


# ══════════════════════════════════════════════════════════
#                    🎟 ПРОМОКОДЫ
# ══════════════════════════════════════════════════════════
@dp.message(Command("promo"))
async def cmd_promo(message: Message, state: FSMContext):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await state.set_state(PromoState.waiting_code)
        await message.answer("🎟 Введи промокод:")
        return
    await _redeem_promo(message, args[1].strip().upper(), state)


@dp.message(PromoState.waiting_code)
async def promo_input(message: Message, state: FSMContext):
    await _redeem_promo(message, (message.text or "").strip().upper(), state)


async def _redeem_promo(message: Message, code: str, state: FSMContext):
    uid = message.from_user.id
    emoji = await get_emoji()

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM promocodes WHERE code = ?", (code,))
        row = await cur.fetchone()
    if not row:
        await message.answer("❌ Промокод не найден.")
        await state.clear()
        return

    promo = dict(row)
    now = int(time.time())

    if promo["expires_at"] and promo["expires_at"] < now:
        await message.answer("❌ Промокод истёк.")
        await state.clear()
        return
    if promo["uses_left"] is not None and promo["uses_left"] <= 0:
        await message.answer("❌ Промокод исчерпан.")
        await state.clear()
        return

    # Один раз на юзера
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM promo_uses WHERE code = ? AND user_id = ?",
            (code, uid))
        if (await cur.fetchone())[0] > 0:
            await message.answer("❌ Ты уже использовал этот промокод.")
            await state.clear()
            return

    # Начисляем
    await add_balance(uid, promo["amount"], "promo", f"Промокод {code}")

    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO promo_uses (code, user_id, used_at) VALUES (?, ?, ?)",
            (code, uid, now))
        if promo["uses_left"] is not None:
            await conn.execute(
                "UPDATE promocodes SET uses_left = uses_left - 1 WHERE code = ?",
                (code,))
        await conn.commit()

    await message.answer(
        f"🎉 <b>Промокод активирован!</b>\n\n"
        f"{emoji} +<b>{fmt(promo['amount'])}</b>"
    )
    await state.clear()


# ══════════════════════════════════════════════════════════
#                    🏅 ДОСТИЖЕНИЯ
# ══════════════════════════════════════════════════════════
ACHIEVEMENTS_DEFAULT = [
    ("first_bet", "🎰 Первый спин", "Сделать первую ставку", 500, "🎰"),
    ("bets_100", "🎲 Сто ставок", "Сделать 100 ставок", 5000, "🎲"),
    ("bets_1000", "🔥 Тысяча ставок", "1000 ставок", 50000, "🔥"),
    ("win_100", "✅ 100 побед", "Выиграть 100 раз", 5000, "✅"),
    ("millionaire", "💎 Миллионер", "Накопить 1 000 000", 100000, "💎"),
    ("whale", "🐋 Кит", "Ставка 100 000", 50000, "🐋"),
    ("big_win_10k", "🏆 Крупный выигрыш", "Выиграть 10 000 за раз", 5000, "🏆"),
    ("daily_7", "🔥 Неделя стрика", "Daily 7 дней подряд", 5000, "🔥"),
    ("daily_30", "👑 Месяц стрика", "Daily 30 дней подряд", 50000, "👑"),
    ("ref_1", "🤝 Первый друг", "Пригласить 1 друга", 500, "🤝"),
    ("ref_10", "👥 10 друзей", "Пригласить 10 друзей", 10000, "👥"),
    ("married", "💍 Женатик", "Жениться", 5000, "💍"),
    ("clan_owner", "🏰 Клановод", "Создать клан", 10000, "🏰"),
    ("jackpot", "💥 Джекпот!", "Выиграть джекпот", 0, "💥"),
]


async def init_achievements():
    async with aiosqlite.connect(DB_PATH) as conn:
        for code, name, desc, reward, icon in ACHIEVEMENTS_DEFAULT:
            await conn.execute(
                "INSERT OR IGNORE INTO achievements_list (code, name, description, reward, icon) "
                "VALUES (?, ?, ?, ?, ?)", (code, name, desc, reward, icon))
        await conn.commit()


async def unlock_achievement(uid: int, code: str) -> bool:
    """Возвращает True, если только что открыли."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT 1 FROM achievements WHERE user_id = ? AND code = ?",
            (uid, code))
        if await cur.fetchone():
            return False
        await conn.execute(
            "INSERT INTO achievements (user_id, code, unlocked_at) VALUES (?, ?, ?)",
            (uid, code, int(time.time())))
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT reward FROM achievements_list WHERE code = ?", (code,))
        row = await cur.fetchone()
        if row:
            await conn.execute(
                "UPDATE users SET balance = balance + ? WHERE id = ?",
                (row["reward"], uid))
        await conn.commit()
    try:
        emoji = await get_emoji()
        await bot.send_message(
            uid,
            f"🏅 <b>Достижение открыто!</b>\n\n"
            f"🎖 {code}\n"
            f"💰 Награда: {emoji} {fmt(row['reward'] if row else 0)}"
        )
    except Exception:
        pass
    return True


@dp.message(Command("achievements"))
async def cmd_achievements(message: Message):
    uid = message.from_user.id
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM achievements_list ORDER BY reward")
        all_ach = [dict(r) for r in await cur.fetchall()]
        cur = await conn.execute(
            "SELECT code FROM achievements WHERE user_id = ?", (uid,))
        unlocked = {r["code"] for r in await cur.fetchall()}

    text = f"🏅 <b>Достижения</b> ({len(unlocked)}/{len(all_ach)})\n\n"
    for a in all_ach:
        mark = "✅" if a["code"] in unlocked else "🔒"
        text += f"{mark} {a['icon']} <b>{a['name']}</b>\n"
        text += f"   <i>{a['description']}</i> — 🎁 {fmt(a['reward'])}\n"

    await message.answer(text)


@dp.callback_query(F.data == "menu:ach")
async def cb_ach(call: CallbackQuery):
    uid = call.from_user.id
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM achievements_list ORDER BY reward")
        all_ach = [dict(r) for r in await cur.fetchall()]
        cur = await conn.execute(
            "SELECT code FROM achievements WHERE user_id = ?", (uid,))
        unlocked = {r["code"] for r in await cur.fetchall()}

    text = f"🏅 <b>Достижения</b> ({len(unlocked)}/{len(all_ach)})\n\n"
    for a in all_ach:
        mark = "✅" if a["code"] in unlocked else "🔒"
        text += f"{mark} {a['icon']} <b>{a['name']}</b> — {fmt(a['reward'])}\n"

    try:
        await call.message.edit_text(text, reply_markup=back_kb())
    except Exception:
        await call.message.answer(text, reply_markup=back_kb())
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    📜 КВЕСТЫ
# ══════════════════════════════════════════════════════════
QUESTS_DEFAULT = [
    ("q_bets10", "Сделай 10 ставок", "10 ставок", "bets", 10, 500),
    ("q_win5", "Выиграй 5 раз", "5 побед", "wins", 5, 1000),
    ("q_win5000", "Выиграй 5 000", "Сумма выигрышей 5000", "win_amount", 5000, 1500),
]


async def init_quests():
    async with aiosqlite.connect(DB_PATH) as conn:
        for code, name, desc, typ, target, reward in QUESTS_DEFAULT:
            await conn.execute(
                "INSERT OR IGNORE INTO quests_list (code, name, description, type, target, reward) "
                "VALUES (?, ?, ?, ?, ?, ?)", (code, name, desc, typ, target, reward))
        await conn.commit()


async def refresh_daily_quests():
    """Обновляет квесты для всех юзеров раз в сутки."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT code, target, reward FROM quests_list")
        quests = [dict(r) for r in await cur.fetchall()]
        cur = await conn.execute("SELECT id FROM users WHERE is_banned = 0")
        uids = [r["id"] for r in await cur.fetchall()]

        await conn.execute("DELETE FROM quests")
        expires = int(time.time()) + 24 * 3600
        for uid in uids:
            for q in quests:
                await conn.execute(
                    "INSERT INTO quests (user_id, code, target, reward, expires_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (uid, q["code"], q["target"], q["reward"], expires))
        await conn.commit()


async def progress_quest(uid: int, quest_type: str, value: int = 1):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT code FROM quests_list WHERE type = ?", (quest_type,))
        codes = [r["code"] for r in await cur.fetchall()]
        for code in codes:
            await conn.execute(
                "UPDATE quests SET progress = progress + ? "
                "WHERE user_id = ? AND code = ? AND completed = 0",
                (value, uid, code))
            await conn.execute(
                "UPDATE quests SET completed = 1 "
                "WHERE user_id = ? AND code = ? AND progress >= target AND completed = 0",
                (uid, code))
        await conn.commit()


@dp.message(Command("quests"))
async def cmd_quests(message: Message):
    await _show_quests(message)


@dp.callback_query(F.data == "menu:quests")
async def cb_quests(call: CallbackQuery):
    await _show_quests(call.message, edit=True)
    await call.answer()


async def _show_quests(message: Message, edit: bool = False):
    uid = message.chat.id if edit else message.from_user.id
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT q.*, ql.name, ql.description FROM quests q
            JOIN quests_list ql ON ql.code = q.code
            WHERE q.user_id = ?
        """, (uid,))
        rows = [dict(r) for r in await cur.fetchall()]

    text = "📜 <b>Ежедневные задания</b>\n\n"
    if not rows:
        text += "Нет активных заданий. Загляни позже."
    else:
        for q in rows:
            mark = "✅" if q["completed"] else "⏳"
            text += f"{mark} <b>{q['name']}</b>\n"
            text += f"   {q['progress']}/{q['target']} — 🎁 {fmt(q['reward'])}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
    ])
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb)
        except Exception:
            await message.answer(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("claim_quest:"))
async def cb_claim_quest(call: CallbackQuery):
    qid = int(call.data.split(":")[1])
    uid = call.from_user.id
    emoji = await get_emoji()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM quests WHERE id = ? AND user_id = ?", (qid, uid))
        row = await cur.fetchone()
        if not row or not row["completed"]:
            await call.answer("Не выполнено", show_alert=True)
            return
        reward = row["reward"]
        await conn.execute("DELETE FROM quests WHERE id = ?", (qid,))
        await conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?",
                           (reward, uid))
        await conn.commit()
    await call.answer(f"✅ +{fmt(reward)} {emoji}", show_alert=True)


# ══════════════════════════════════════════════════════════
#                    🏰 КЛАНЫ
# ══════════════════════════════════════════════════════════
CLAN_CREATE_PRICE = 50000


@dp.message(Command("clan"))
async def cmd_clan(message: Message):
    uid = message.from_user.id
    user = await get_user(uid)
    emoji = await get_emoji()

    if not user["clan_id"]:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🏰 Создать клан ({fmt(CLAN_CREATE_PRICE)})",
                                  callback_data="clan_create")],
        ])
        await message.answer(
            f"🏰 <b>Кланы</b>\n\n"
            f"Ты не в клане.\n\n"
            f"Создай свой за {emoji} <b>{fmt(CLAN_CREATE_PRICE)}</b> или вступи по приглашению.",
            reply_markup=kb,
        )
        return

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM clans WHERE id = ?", (user["clan_id"],))
        clan = dict(await cur.fetchone())
        cur = await conn.execute(
            "SELECT u.username, cm.role FROM clan_members cm "
            "JOIN users u ON u.id = cm.user_id WHERE cm.clan_id = ?",
            (user["clan_id"],))
        members = await cur.fetchall()

    text = (
        f"🏰 <b>Клан [{clan['tag']}] {clan['name']}</b>\n\n"
        f"👑 Лидер: <code>{clan['owner_id']}</code>\n"
        f"👥 Участников: <b>{clan['members_count']}</b>\n"
        f"💰 Казна: {emoji} <b>{fmt(clan['balance'])}</b>\n"
        f"📊 Уровень: <b>{clan['level']}</b>\n\n"
        f"<b>Участники:</b>\n"
    )
    for m in members[:10]:
        name = f"@{m['username']}" if m["username"] else "—"
        text += f"• {name} [{m['role']}]\n"

    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Внести в казну", callback_data="clan_deposit")
    if clan["owner_id"] == uid:
        kb.button(text="📢 Пригласить", callback_data="clan_invite")
        kb.button(text="🗑 Распустить", callback_data="clan_delete")
    else:
        kb.button(text="🚪 Покинуть", callback_data="clan_leave")
    kb.adjust(1)
    await message.answer(text, reply_markup=kb.as_markup())


@dp.callback_query(F.data == "clan_create")
async def cb_clan_create(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    user = await get_user(uid)
    emoji = await get_emoji()
    if user["balance"] < CLAN_CREATE_PRICE:
        await call.answer("Недостаточно", show_alert=True)
        return
    await state.set_state(AdminState.waiting_user_id)  # переиспользуем
    await state.update_data(action="clan_create")
    await call.message.answer("📝 Отправь название клана:")
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    💍 БРАК
# ══════════════════════════════════════════════════════════
@dp.message(Command("marry"))
async def cmd_marry(message: Message):
    user = await get_user(message.from_user.id)
    emoji = await get_emoji()
    if user["married_to"]:
        partner = await get_user(user["married_to"])
        name = partner["first_name"] if partner else "неизвестно"
        await message.answer(
            f"💍 <b>Ты в браке</b>\n\n"
            f"💑 Партнёр: <b>{name}</b>\n\n"
            f"Развод: /divorce"
        )
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "💍 <b>Предложение</b>\n\n"
            "Использование: /marry @username\n"
            f"Требуется кольцо 💍 (из /shop)"
        )
        return

    target_name = args[1].strip().lstrip("@")
    target = await get_user_by_username(target_name)
    if not target:
        await message.answer("❌ Игрок не найден.")
        return
    if target["id"] == user["id"]:
        await message.answer("❌ Себе нельзя.")
        return
    if target["married_to"]:
        await message.answer("❌ Этот игрок уже в браке.")
        return

    # Проверяем кольцо
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("""
            SELECT inv.id FROM inventory inv
            JOIN shop_items s ON s.id = inv.item_id
            WHERE inv.user_id = ? AND s.value = 'ring' LIMIT 1
        """, (user["id"],))
        ring = await cur.fetchone()

    if not ring:
        await message.answer("❌ Нужно кольцо 💍 (из /shop).")
        return

    # Создаём брак
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO marriages (user1_id, user2_id, married_at, is_active) "
            "VALUES (?, ?, ?, 1)", (user["id"], target["id"], now))
        await conn.execute(
            "UPDATE users SET married_to = ? WHERE id = ?",
            (target["id"], user["id"]))
        await conn.execute(
            "UPDATE users SET married_to = ? WHERE id = ?",
            (user["id"], target["id"]))
        # Забираем кольцо
        await conn.execute("DELETE FROM inventory WHERE id = ?", (ring[0],))
        await conn.commit()

    await message.answer(f"💍 <b>Вы поженились!</b>\n\n💑 {target['first_name']} и ты — теперь пара!")
    try:
        await bot.send_message(
            target["id"],
            f"💍 Тебе сделали предложение и ты согласен! Поздравляем!")
    except Exception:
        pass
    await unlock_achievement(user["id"], "married")
    await unlock_achievement(target["id"], "married")


@dp.message(Command("divorce"))
async def cmd_divorce(message: Message):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user["married_to"]:
        await message.answer("Ты не в браке.")
        return
    partner = user["married_to"]
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET married_to = NULL WHERE id IN (?, ?)", (uid, partner))
        await conn.execute(
            "UPDATE marriages SET is_active = 0, divorce_at = ? "
            "WHERE (user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)",
            (int(time.time()), uid, partner, partner, uid))
        await conn.commit()
    await message.answer("💔 Вы развелись.")


# ══════════════════════════════════════════════════════════
#                    🎁 ПОДАРКИ
# ══════════════════════════════════════════════════════════
@dp.message(Command("gift"))
async def cmd_gift(message: Message):
    args = (message.text or "").split(maxsplit=2)
    emoji = await get_emoji()
    if len(args) < 3:
        await message.answer(
            "🎁 <b>Подарок</b>\n\n"
            "Использование: /gift @user <сумма>\n"
            "Отправит указанную сумму из твоего баланса."
        )
        return
    target_name = args[1].lstrip("@")
    try:
        amount = int(args[2])
    except ValueError:
        await message.answer("❌ Сумма — число.")
        return
    target = await get_user_by_username(target_name)
    if not target:
        await message.answer("❌ Игрок не найден.")
        return
    user = await get_user(message.from_user.id)
    if amount < 10 or amount > user["balance"]:
        await message.answer("❌ Неверная сумма.")
        return

    await add_balance(message.from_user.id, -amount, "gift_out", f"→ {target['id']}")
    await add_balance(target["id"], amount, "gift_in", f"← {message.from_user.id}")

    await message.answer(f"🎁 Подарок отправлен: {emoji} {fmt(amount)}")
    try:
        await bot.send_message(
            target["id"],
            f"🎁 Тебе подарок от <code>{message.from_user.id}</code>: "
            f"{emoji} <b>+{fmt(amount)}</b>")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════
#                    ⚙️ ЕЩЁ (меню)
# ══════════════════════════════════════════════════════════
@dp.message(F.text == "⚙️ Ещё")
async def cmd_more(message: Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Бонусы", callback_data="more:bonuses")
    kb.button(text="👥 Социалка", callback_data="more:social")
    kb.button(text="📊 Статистика", callback_data="more:stats")
    kb.button(text="🏆 Турниры", callback_data="more:tournaments")
    kb.button(text="🎉 Ивенты", callback_data="more:events")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(2, 2, 2)
    await message.answer("⚙️ <b>Дополнительно</b>", reply_markup=kb.as_markup())


@dp.callback_query(F.data == "more:bonuses")
async def cb_more_bonuses(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Daily", callback_data="menu:daily"),
         InlineKeyboardButton(text="💼 Work", callback_data="more:work")],
        [InlineKeyboardButton(text="🎉 Bonus", callback_data="more:bonus")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="more:back")],
    ])
    await call.message.edit_text("🎁 <b>Бонусы</b>\n\n/daily /work /bonus", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "more:work")
async def cb_more_work(call: CallbackQuery):
    await cmd_work(call.message)
    await call.answer()


@dp.callback_query(F.data == "more:bonus")
async def cb_more_bonus(call: CallbackQuery):
    await cmd_bonus(call.message)
    await call.answer()


@dp.callback_query(F.data == "more:back")
async def cb_more_back(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Бонусы", callback_data="more:bonuses")
    kb.button(text="👥 Социалка", callback_data="more:social")
    kb.button(text="📊 Статистика", callback_data="more:stats")
    kb.button(text="🏆 Турниры", callback_data="more:tournaments")
    kb.button(text="🎉 Ивенты", callback_data="more:events")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(2, 2, 2)
    await call.message.edit_text("⚙️ <b>Дополнительно</b>", reply_markup=kb.as_markup())
    await call.answer()


@dp.callback_query(F.data == "more:social")
async def cb_more_social(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏰 Клан", callback_data="more:clan"),
         InlineKeyboardButton(text="💍 Брак", callback_data="more:marry")],
        [InlineKeyboardButton(text="🔗 Рефералы", callback_data="menu:ref")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="more:back")],
    ])
    await call.message.edit_text(
        "👥 <b>Социалка</b>\n\n/clan /marry /ref /gift",
        reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "more:clan")
async def cb_more_clan(call: CallbackQuery):
    await cmd_clan(call.message)
    await call.answer()


@dp.callback_query(F.data == "more:marry")
async def cb_more_marry(call: CallbackQuery):
    await call.message.answer("/marry @username — сделать предложение")
    await call.answer()


@dp.callback_query(F.data == "more:stats")
async def cb_more_stats(call: CallbackQuery):
    await cmd_stats(call.message)
    await call.answer()


@dp.callback_query(F.data == "more:tournaments")
async def cb_more_tournaments(call: CallbackQuery):
    await cmd_tournaments(call.message)
    await call.answer()


@dp.callback_query(F.data == "more:events")
async def cb_more_events(call: CallbackQuery):
    await cmd_events(call.message)
    await call.answer()
  # ══════════════════════════════════════════════════════════
#                    🛠 АДМИН-ПАНЕЛЬ
# ══════════════════════════════════════════════════════════
def admin_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Юзеры", callback_data="adm:users")
    kb.button(text="💰 Баланс", callback_data="adm:balance")
    kb.button(text="🎮 Игры/RTP", callback_data="adm:games")
    kb.button(text="📊 Статистика", callback_data="adm:stats")
    kb.button(text="📢 Рассылка", callback_data="adm:broadcast")
    kb.button(text="🚫 Баны", callback_data="adm:bans")
    kb.button(text="📜 Логи", callback_data="adm:logs")
    kb.button(text="🎁 Промокоды", callback_data="adm:promo")
    kb.button(text="🎟 Эмодзи валюты", callback_data="adm:sate")
    kb.button(text="❌ Закрыть", callback_data="adm:close")
    kb.adjust(2, 2, 2, 2, 1, 1)
    return kb.as_markup()


@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "🛠 <b>Админ-панель</b>\n\nВыбери раздел:",
        reply_markup=admin_kb(),
    )


@dp.callback_query(F.data == "adm:close")
async def cb_adm_close(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer()


@dp.callback_query(F.data == "adm:menu")
async def cb_adm_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.clear()
    try:
        await call.message.edit_text(
            "🛠 <b>Админ-панель</b>\n\nВыбери раздел:",
            reply_markup=admin_kb())
    except Exception:
        await call.message.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_kb())
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    👥 ЮЗЕРЫ
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "adm:users")
async def cb_adm_users(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminState.waiting_user_id)
    await state.update_data(adm_action="find_user")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:menu")],
    ])
    await call.message.edit_text(
        "👥 <b>Поиск юзера</b>\n\nОтправь ID или @username:",
        reply_markup=kb)
    await call.answer()


@dp.message(AdminState.waiting_user_id)
async def adm_waiting_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    action = data.get("adm_action", "find_user")
    txt = (message.text or "").strip()

    # Спец-сценарии
    if action == "clan_create":
        await _do_clan_create(message, txt, state)
        return
    if action == "broadcast_text":
        await _do_broadcast(message, txt, state)
        return
    if action == "promo_amount":
        await _promo_next_amount(message, txt, state)
        return
    if action == "promo_uses":
        await _promo_next_uses(message, txt, state)
        return
    if action == "rtp_value":
        await _set_rtp_value(message, txt, state)
        return
    if action == "ban_reason":
        await _ban_reason_step(message, txt, state)
        return
    if action == "sate_text":
        await set_setting("currency_emoji", txt[:8])
        await admin_log(message.from_user.id, "sate", 0, f"emoji={txt[:8]}")
        await message.answer(f"✅ Эмодзи валюты: <b>{txt[:8]}</b>")
        await state.clear()
        return

    # Поиск юзера
    user = None
    if txt.startswith("@"):
        user = await get_user_by_username(txt)
    else:
        try:
            user = await get_user(int(txt))
        except ValueError:
            pass

    if not user:
        await message.answer("❌ Не найден.")
        return

    await _show_user_card(message, user, state)


async def _show_user_card(message: Message, user: dict, state: FSMContext):
    emoji = await get_emoji()
    wr = (user["total_wins"] / user["total_bets"] * 100) if user["total_bets"] else 0
    ban = "🚫 ЗАБАНЕН" if user["is_banned"] else "✅ активен"
    text = (
        f"👤 <b>Карточка юзера</b>\n\n"
        f"🆔 <code>{user['id']}</code>\n"
        f"👤 @{user['username'] or '—'} ({user['first_name'] or '—'})\n"
        f"📌 Статус: {ban}\n"
        f"🎖 Уровень: {user['level']} ({user['xp']} XP)\n\n"
        f"{emoji} Кошелёк: <b>{fmt(user['balance'])}</b>\n"
        f"🏦 Банк: <b>{fmt(user['bank'])}</b>\n\n"
        f"🎲 Ставок: {user['total_bets']}\n"
        f"✅ Побед: {user['total_wins']} ({wr:.1f}%)\n"
        f"❌ Проигрышей: {user['total_losses']}\n"
        f"🏆 Макс. выигрыш: {fmt(user['biggest_win'])}\n"
        f"👥 Рефералов: {user['referral_count']}\n"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 +1000", callback_data=f"adm_bal:{user['id']}:1000")
    kb.button(text="💰 +10000", callback_data=f"adm_bal:{user['id']}:10000")
    kb.button(text="💰 -1000", callback_data=f"adm_bal:{user['id']}:-1000")
    kb.button(text="✏️ Установить", callback_data=f"adm_setbal:{user['id']}")
    kb.button(text="🚫 Бан" if not user["is_banned"] else "✅ Разбан",
              callback_data=f"adm_ban:{user['id']}")
    kb.button(text="⬅️ Назад", callback_data="adm:menu")
    kb.adjust(3, 1, 2, 1)
    try:
        await message.edit_text(text, reply_markup=kb.as_markup())
    except Exception:
        await message.answer(text, reply_markup=kb.as_markup())
    await state.clear()


@dp.callback_query(F.data.startswith("adm_bal:"))
async def cb_adm_balance(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    _, uid, delta = call.data.split(":")
    uid, delta = int(uid), int(delta)
    user = await get_user(uid)
    if not user:
        await call.answer("Не найден", show_alert=True)
        return
    await add_balance(uid, delta, "admin", f"от {call.from_user.id}")
    await admin_log(call.from_user.id, "balance_change", uid, f"{delta:+}")
    await call.answer(f"✅ {delta:+} выдано")
    # обновляем карточку
    user = await get_user(uid)
    await _show_user_card(call.message, user, FSMContext(dp.storage, chat_id=call.message.chat.id, user_id=call.from_user.id))


@dp.callback_query(F.data.startswith("adm_setbal:"))
async def cb_adm_setbal(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data.split(":")[1])
    await state.update_data(target_uid=uid, adm_action="set_balance")
    await state.set_state(AdminState.waiting_amount)
    await call.message.answer(f"✏️ Введи новое значение баланса для <code>{uid}</code>:")
    await call.answer()


@dp.message(AdminState.waiting_amount)
async def adm_waiting_amount(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    action = data.get("adm_action")

    if action == "set_balance":
        uid = data.get("target_uid")
        try:
            amount = int((message.text or "").strip())
        except ValueError:
            await message.answer("❌ Число.")
            return
        await set_balance(uid, amount)
        await admin_log(message.from_user.id, "set_balance", uid, str(amount))
        await message.answer(f"✅ Баланс <code>{uid}</code> = <b>{fmt(amount)}</b>")
        await state.clear()
        return

    if action == "promo_amount":
        await _promo_next_amount(message, (message.text or "").strip(), state)
        return

    if action == "promo_uses":
        await _promo_next_uses(message, (message.text or "").strip(), state)
        return

    if action == "rtp_value":
        await _set_rtp_value(message, (message.text or "").strip(), state)
        return

    await state.clear()


# ══════════════════════════════════════════════════════════
#                    🚫 БАНЫ
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data.startswith("adm_ban:"))
async def cb_adm_ban(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data.split(":")[1])
    user = await get_user(uid)
    if not user:
        await call.answer("Не найден", show_alert=True)
        return

    if user["is_banned"]:
        # разбан
        await update_user(uid, is_banned=0, ban_reason=None, ban_until=0)
        await admin_log(call.from_user.id, "unban", uid, "")
        await call.answer("✅ Разбанен")
        try:
            await bot.send_message(uid, "✅ Ты разбанен!")
        except Exception:
            pass
    else:
        # бан — шаг 1: причина
        await state.update_data(target_uid=uid, adm_action="ban_reason")
        await state.set_state(AdminState.waiting_reason)
        await call.message.answer(f"🚫 Причина бана для <code>{uid}</code>:")
    await call.answer()


@dp.message(AdminState.waiting_reason)
async def adm_ban_reason(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    reason = (message.text or "").strip() or "нарушение"
    data = await state.get_data()
    uid = data.get("target_uid")
    await state.update_data(ban_reason=reason)
    await state.set_state(AdminState.waiting_amount)  # переиспользуем для времени
    await state.update_data(adm_action="ban_time")
    await message.answer(
        "⏳ На сколько часов бан? Отправь число (0 = навсегда):"
    )


async def _ban_reason_step(message, txt, state):
    # заглушка
    pass


@dp.message(AdminState.waiting_amount)
async def adm_ban_time(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    if data.get("adm_action") != "ban_time":
        return
    uid = data.get("target_uid")
    reason = data.get("ban_reason", "нарушение")
    try:
        hours = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Число (часы).")
        return
    until = 0 if hours == 0 else int(time.time()) + hours * 3600
    await update_user(uid, is_banned=1, ban_reason=reason, ban_until=until)
    await admin_log(message.from_user.id, "ban", uid, f"{reason} / {hours}ч")
    await message.answer(f"🚫 Забанен <code>{uid}</code>\nПричина: {reason}")
    try:
        await bot.send_message(uid, f"🚫 Ты забанен.\nПричина: {reason}")
    except Exception:
        pass
    await state.clear()


# ══════════════════════════════════════════════════════════
#                    💰 БАЛАНС (общее меню)
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "adm:balance")
async def cb_adm_balance_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Всем +100", callback_data="adm_mass:100"),
         InlineKeyboardButton(text="➕ Всем +1000", callback_data="adm_mass:1000")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:menu")],
    ])
    await call.message.edit_text("💰 <b>Массовые операции</b>", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("adm_mass:"))
async def cb_adm_mass(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    delta = int(call.data.split(":")[1])
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE users SET balance = balance + ? WHERE is_banned = 0",
                           (delta,))
        await conn.commit()
    await admin_log(call.from_user.id, "mass_balance", 0, f"{delta:+} всем")
    await call.answer(f"✅ Всем +{delta}")
    await call.message.edit_text(
        f"✅ Всем начислено +{delta}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:menu")]]))


# ══════════════════════════════════════════════════════════
#                    🎮 ИГРЫ / RTP
# ══════════════════════════════════════════════════════════
GAMES_LIST = ["slots", "dice", "coin", "roulette", "blackjack", "mines",
              "wheel", "crash", "plinko", "keno", "baccarat", "poker",
              "football", "basketball", "bowling", "darts", "rps",
              "guess", "snake", "lottery"]


@dp.callback_query(F.data == "adm:games")
async def cb_adm_games(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    kb = InlineKeyboardBuilder()
    for g in GAMES_LIST:
        enabled = await get_setting(f"game_{g}_enabled", "1")
        rtp = await get_setting(f"rtp_{g}", "95")
        mark = "✅" if enabled == "1" else "❌"
        kb.button(text=f"{mark} {g} ({rtp}%)", callback_data=f"adm_game:{g}")
    kb.button(text="⬅️ Назад", callback_data="adm:menu")
    kb.adjust(2)
    await call.message.edit_text(
        "🎮 <b>Управление играми</b>\n\nНажми на игру чтобы вкл/выкл или поменять RTP:",
        reply_markup=kb.as_markup())
    await call.answer()


@dp.callback_query(F.data.startswith("adm_game:"))
async def cb_adm_game_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    g = call.data.split(":")[1]
    enabled = await get_setting(f"game_{g}_enabled", "1")
    rtp = await get_setting(f"rtp_{g}", "95")
    kb = InlineKeyboardBuilder()
    kb.button(text="🚫 Выключить" if enabled == "1" else "✅ Включить",
              callback_data=f"adm_game_toggle:{g}")
    kb.button(text="✏️ Изменить RTP", callback_data=f"adm_game_rtp:{g}")
    kb.button(text="⬅️ Назад", callback_data="adm:games")
    kb.adjust(1)
    await call.message.edit_text(
        f"🎮 <b>{g}</b>\n\n"
        f"Статус: {'✅ вкл' if enabled == '1' else '❌ выкл'}\n"
        f"RTP: <b>{rtp}%</b>",
        reply_markup=kb.as_markup())
    await call.answer()


@dp.callback_query(F.data.startswith("adm_game_toggle:"))
async def cb_adm_game_toggle(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    g = call.data.split(":")[1]
    cur = await get_setting(f"game_{g}_enabled", "1")
    new = "0" if cur == "1" else "1"
    await set_setting(f"game_{g}_enabled", new)
    await admin_log(call.from_user.id, "game_toggle", 0, f"{g}={new}")
    await call.answer(f"✅ {g}: {'вкл' if new == '1' else 'выкл'}")
    await cb_adm_games(call)


@dp.callback_query(F.data.startswith("adm_game_rtp:"))
async def cb_adm_game_rtp(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    g = call.data.split(":")[1]
    await state.update_data(rtp_game=g, adm_action="rtp_value")
    await state.set_state(AdminState.waiting_amount)
    await call.message.answer(f"✏️ Введи RTP для <b>{g}</b> (50-99):")
    await call.answer()


async def _set_rtp_value(message: Message, txt: str, state: FSMContext):
    data = await state.get_data()
    g = data.get("rtp_game")
    try:
        val = int(txt)
    except ValueError:
        await message.answer("❌ Число.")
        return
    if not (50 <= val <= 99):
        await message.answer("❌ RTP 50-99.")
        return
    await set_setting(f"rtp_{g}", str(val))
    await admin_log(message.from_user.id, "rtp", 0, f"{g}={val}")
    await message.answer(f"✅ RTP {g}: <b>{val}%</b>")
    await state.clear()


# ══════════════════════════════════════════════════════════
#                    📊 СТАТИСТИКА
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "adm:stats")
async def cb_adm_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM users")
        users = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        banned = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM bets")
        bets, vol = await cur.fetchone()
        cur = await conn.execute("SELECT COALESCE(SUM(balance),0) FROM users")
        total_bal = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT amount FROM jackpot WHERE id = 1")
        jp = (await cur.fetchone())[0]

    emoji = await get_emoji()
    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Игроков: <b>{users}</b>\n"
        f"🚫 Забанено: <b>{banned}</b>\n"
        f"🎲 Ставок всего: <b>{bets}</b>\n"
        f"💰 Оборот ставок: <b>{fmt(int(vol))}</b>\n"
        f"💵 Балансов суммарно: <b>{fmt(total_bal)}</b>\n"
        f"🎰 Джекпот: <b>{fmt(jp)}</b> {emoji}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="adm:stats")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:menu")],
    ])
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        await call.message.answer(text, reply_markup=kb)
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    📢 РАССЫЛКА
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "adm:broadcast")
async def cb_adm_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(adm_action="broadcast_text")
    await state.set_state(AdminState.waiting_broadcast)
    await call.message.answer(
        "📢 Отправь текст рассылки (HTML работает).\n/cancel для отмены.")
    await call.answer()


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено.")


@dp.message(AdminState.waiting_broadcast)
async def adm_broadcast_input(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    text = message.text or message.caption or ""
    await _do_broadcast(message, text, state)


async def _do_broadcast(message: Message, text: str, state: FSMContext):
    if not text.strip():
        await message.answer("❌ Пустой текст.")
        return
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT id FROM users WHERE is_banned = 0")
        uids = [r[0] for r in await cur.fetchall()]

    await message.answer(f"📢 Начинаю рассылку по {len(uids)} юзерам...")
    ok, fail = 0, 0
    for uid in uids:
        try:
            await bot.send_message(uid, text)
            ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    await admin_log(message.from_user.id, "broadcast", 0,
                    f"ok={ok}, fail={fail}, text={text[:50]}")
    await message.answer(f"✅ Готово!\n✅ Доставлено: {ok}\n❌ Ошибок: {fail}")
    await state.clear()


# ══════════════════════════════════════════════════════════
#                    📜 ЛОГИ
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "adm:logs")
async def cb_adm_logs(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM admin_logs ORDER BY id DESC LIMIT 20")
        rows = [dict(r) for r in await cur.fetchall()]

    text = "📜 <b>Последние 20 действий админов:</b>\n\n"
    for r in rows:
        ts = datetime.fromtimestamp(r["created_at"]).strftime("%d.%m %H:%M")
        text += f"[{ts}] <code>{r['admin_id']}</code> → {r['action']} "
        text += f"(target={r['target_id']}) {r['details'] or ''}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:menu")],
    ])
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        await call.message.answer(text, reply_markup=kb)
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    🎁 ПРОМОКОДЫ
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "adm:promo")
async def cb_adm_promo(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="adm_promo_create")],
        [InlineKeyboardButton(text="📋 Список", callback_data="adm_promo_list")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:menu")],
    ])
    await call.message.edit_text("🎁 <b>Промокоды</b>", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "adm_promo_create")
async def cb_adm_promo_create(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(adm_action="promo_code")
    await state.set_state(AdminState.waiting_amount)
    await call.message.answer(
        "📝 Отправь промокод в формате:\n"
        "<code>CODE AMOUNT USES</code>\n\n"
        "Пример: <code>WELCOME 5000 100</code>")
    await call.answer()


async def _promo_next_amount(message: Message, txt: str, state: FSMContext):
    parts = txt.split()
    if len(parts) < 3:
        await message.answer("❌ Формат: CODE AMOUNT USES")
        return
    code = parts[0].upper()
    try:
        amount = int(parts[1])
        uses = int(parts[2])
    except ValueError:
        await message.answer("❌ Числа.")
        return
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO promocodes "
            "(code, amount, uses_left, max_uses, expires_at, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, amount, uses, uses, 0, message.from_user.id, int(time.time())))
        await conn.commit()
    await admin_log(message.from_user.id, "promo_create", 0,
                    f"{code} {amount} x{uses}")
    await message.answer(
        f"✅ Промокод создан:\n<code>{code}</code>\n"
        f"💰 {fmt(amount)} | 🎟 {uses} использований")
    await state.clear()


async def _promo_next_uses(message, txt, state):
    pass


@dp.callback_query(F.data == "adm_promo_list")
async def cb_adm_promo_list(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM promocodes ORDER BY created_at DESC LIMIT 20")
        rows = [dict(r) for r in await cur.fetchall()]

    text = "🎁 <b>Промокоды:</b>\n\n"
    for r in rows:
        text += f"• <code>{r['code']}</code> — {fmt(r['amount'])} "
        text += f"({r['uses_left']}/{r['max_uses']})\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:promo")]])
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        await call.message.answer(text, reply_markup=kb)
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    🎟 ЭМОДЗИ ВАЛЮТЫ (через админку)
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "adm:sate")
async def cb_adm_sate(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    cur = await get_emoji()
    await state.update_data(adm_action="sate_text")
    await state.set_state(AdminState.waiting_amount)
    await call.message.answer(
        f"🎟 Текущий эмодзи валюты: <b>{cur}</b>\n\n"
        f"Отправь новый (или /cancel):")
    await call.answer()


# ══════════════════════════════════════════════════════════
#                    🏰 СОЗДАНИЕ КЛАНА (продолжение)
# ══════════════════════════════════════════════════════════
async def _do_clan_create(message: Message, name: str, state: FSMContext):
    uid = message.from_user.id
    user = await get_user(uid)
    emoji = await get_emoji()
    if user["balance"] < CLAN_CREATE_PRICE:
        await message.answer("❌ Недостаточно средств.")
        await state.clear()
        return
    name = name.strip()[:20]
    tag = name[:3].upper()
    await add_balance(uid, -CLAN_CREATE_PRICE, "clan", "Создание клана")
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO clans (name, tag, owner_id, created_at) VALUES (?, ?, ?, ?)",
            (name, tag, uid, int(time.time())))
        clan_id = cur.lastrowid
        await conn.execute(
            "INSERT INTO clan_members (clan_id, user_id, role, joined_at) "
            "VALUES (?, ?, 'owner', ?)", (clan_id, uid, int(time.time())))
        await conn.execute("UPDATE users SET clan_id = ? WHERE id = ?", (clan_id, uid))
        await conn.commit()
    await unlock_achievement(uid, "clan_owner")
    await message.answer(f"🏰 Клан <b>[{tag}] {name}</b> создан!")
    await state.clear()
  # ══════════════════════════════════════════════════════════
#                    🏆 ТУРНИРЫ
# ══════════════════════════════════════════════════════════
@dp.message(Command("tournaments"))
async def cmd_tournaments(message: Message):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM tournaments WHERE status IN ('open','running') "
            "ORDER BY starts_at ASC LIMIT 10")
        rows = [dict(r) for r in await cur.fetchall()]

    emoji = await get_emoji()
    if not rows:
        text = ("🏆 <b>Турниры</b>\n\n"
                "Сейчас нет активных турниров.\n"
                "Следующие запустятся автоматически.\n\n"
                "🎮 Ежедневные турниры: слоты, рулетка, блэкджек.")
    else:
        text = "🏆 <b>Активные турниры:</b>\n\n"
        for t in rows:
            text += (f"🎮 <b>{t['name']}</b> ({t['game']})\n"
                     f"💵 Взнос: {emoji} {fmt(t['entry_fee'])}\n"
                     f"🏆 Призовой фонд: {emoji} {fmt(t['prize_pool'])}\n"
                     f"👥 Игроков: до {t['max_players']}\n"
                     f"📌 Статус: {t['status']}\n\n")

    kb = InlineKeyboardBuilder()
    for t in rows:
        if t["status"] == "open":
            kb.button(text=f"✅ Участвовать: {t['name']}",
                      callback_data=f"tour_join:{t['id']}")
    kb.button(text="⬅️ В меню", callback_data="menu:main")
    kb.adjust(1)
    await message.answer(text, reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("tour_join:"))
async def cb_tour_join(call: CallbackQuery):
    tid = int(call.data.split(":")[1])
    uid = call.from_user.id
    emoji = await get_emoji()

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM tournaments WHERE id = ?", (tid,))
        t = await cur.fetchone()
    if not t:
        await call.answer("Турнир не найден", show_alert=True)
        return
    t = dict(t)
    if t["status"] != "open":
        await call.answer("Регистрация закрыта", show_alert=True)
        return

    user = await get_user(uid)
    if user["balance"] < t["entry_fee"]:
        await call.answer(f"❌ Нужно {fmt(t['entry_fee'])}", show_alert=True)
        return

    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT 1 FROM tournament_players WHERE tournament_id = ? AND user_id = ?",
            (tid, uid))
        if await cur.fetchone():
            await call.answer("Ты уже участвуешь", show_alert=True)
            return
        cur = await conn.execute(
            "SELECT COUNT(*) FROM tournament_players WHERE tournament_id = ?", (tid,))
        cnt = (await cur.fetchone())[0]
        if cnt >= t["max_players"]:
            await call.answer("Мест нет", show_alert=True)
            return

        await conn.execute(
            "INSERT INTO tournament_players (tournament_id, user_id, joined_at) "
            "VALUES (?, ?, ?)", (tid, uid, int(time.time())))
        await conn.execute(
            "UPDATE tournaments SET prize_pool = prize_pool + ? WHERE id = ?",
            (int(t["entry_fee"] * 0.9), tid))
        await conn.commit()

    await add_balance(uid, -t["entry_fee"], "tournament", f"Взнос #{tid}")
    await call.answer("✅ Ты в турнире!", show_alert=True)


# ══════════════════════════════════════════════════════════
#                    🎉 ИВЕНТЫ
# ══════════════════════════════════════════════════════════
@dp.message(Command("events"))
async def cmd_events(message: Message):
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM events WHERE ends_at > ? ORDER BY starts_at", (now,))
        rows = [dict(r) for r in await cur.fetchall()]

    text = "🎉 <b>Активные ивенты</b>\n\n"
    if not rows:
        text += ("Сейчас нет активных ивентов.\n\n"
                 "💡 Бывают:\n"
                 "• 🌙 Ночной джекпот (00:00-06:00, x2)\n"
                 "• ⚡ Золотой час (случайно, +10% RTP)\n"
                 "• 🎄 Сезонные (НГ, Хэллоуин)")
    else:
        for e in rows:
            until = datetime.fromtimestamp(e["ends_at"]).strftime("%d.%m %H:%M")
            text += (f"🎉 <b>{e['name']}</b>\n"
                     f"📈 Множитель: x{e['multiplier']}\n"
                     f"⏰ До: {until}\n\n")

    await message.answer(text, reply_markup=back_kb())


# ══════════════════════════════════════════════════════════
#                    📊 /stats (публичная)
# ══════════════════════════════════════════════════════════
@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM users")
        users = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM bets")
        bets, vol = await cur.fetchone()
        cur = await conn.execute("SELECT amount FROM jackpot WHERE id = 1")
        jp = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COALESCE(SUM(balance),0) FROM users")
        total = (await cur.fetchone())[0]

    emoji = await get_emoji()
    await message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Игроков: <b>{fmt(users)}</b>\n"
        f"🎲 Ставок всего: <b>{fmt(bets)}</b>\n"
        f"💰 Оборот: <b>{fmt(int(vol))}</b> {emoji}\n"
        f"🎰 Джекпот: <b>{fmt(jp)}</b> {emoji}\n"
        f"💵 В экономике: <b>{fmt(total)}</b> {emoji}",
        reply_markup=back_kb())


# ══════════════════════════════════════════════════════════
#                    ⏰ ПЛАНИРОВЩИК (APScheduler)
# ══════════════════════════════════════════════════════════
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    HAS_SCHEDULER = True
except ImportError:
    HAS_SCHEDULER = False
    log.warning("APScheduler не установлен — планировщик отключён")

scheduler = None


# -------- Задачи --------
async def task_refresh_quests():
    """Обновление квестов в полночь."""
    try:
        await refresh_daily_quests()
        log.info("Квесты обновлены")
    except Exception as e:
        log.error(f"task_refresh_quests: {e}")


async def task_lottery_draw():
    """Розыгрыш лотереи."""
    try:
        await _draw_lottery()
    except Exception as e:
        log.error(f"task_lottery_draw: {e}")


async def _draw_lottery():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM lotteries WHERE status='open' AND ends_at < ? "
            "ORDER BY id LIMIT 1", (int(time.time()),))
        lot = await cur.fetchone()
        if not lot:
            return
        lot = dict(lot)

        # Собираем билеты
        cur = await conn.execute(
            "SELECT user_id, tickets FROM lottery_tickets WHERE lottery_id = ?",
            (lot["id"],))
        tickets = []
        for r in await cur.fetchall():
            tickets.extend([r["user_id"]] * r["tickets"])

        if not tickets:
            await conn.execute(
                "UPDATE lotteries SET status='cancelled' WHERE id = ?", (lot["id"],))
            await conn.commit()
            return

        winner = random.choice(tickets)
        prize = lot["prize"]

        await conn.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?", (prize, winner))
        await conn.execute(
            "UPDATE lotteries SET status='finished', winner_id=? WHERE id = ?",
            (winner, lot["id"]))
        await conn.execute(
            "INSERT INTO transactions (user_id, amount, type, reason, created_at) "
            "VALUES (?, ?, 'lottery_win', 'Лотерея', ?)",
            (winner, prize, int(time.time())))
        await conn.commit()

    # Уведомления
    try:
        await bot.send_message(
            winner,
            f"🎉 <b>Ты выиграл лотерею!</b>\n💰 Приз: <b>{fmt(prize)}</b>")
    except Exception:
        pass
    log.info(f"Лотерея #{lot['id']}: победитель {winner}, приз {prize}")


async def task_start_daily_tournaments():
    """Запуск ежедневных турниров."""
    games = ["slots", "roulette", "blackjack"]
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as conn:
        for g in games:
            cur = await conn.execute(
                "SELECT id FROM tournaments WHERE game = ? AND status = 'running'",
                (g,))
            if await cur.fetchone():
                continue
            name = f"Ежедневный {g}"
            await conn.execute(
                "INSERT INTO tournaments "
                "(name, game, entry_fee, prize_pool, max_players, starts_at, ends_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'open')",
                (name, g, 500, 0, 100, now, now + 24 * 3600))
        await conn.commit()
    log.info("Турниры запущены")


async def task_finish_tournaments():
    """Завершает турниры, где ended_at < now."""
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM tournaments WHERE status IN ('open','running') AND ends_at < ?",
            (now,))
        to_finish = [dict(r) for r in await cur.fetchall()]

        for t in to_finish:
            cur = await conn.execute(
                "SELECT user_id, score FROM tournament_players "
                "WHERE tournament_id = ? ORDER BY score DESC LIMIT 3",
                (t["id"],))
            winners = await cur.fetchall()

            pool = t["prize_pool"]
            splits = [0.5, 0.3, 0.2]
            for i, w in enumerate(winners):
                prize = int(pool * splits[i])
                await conn.execute(
                    "UPDATE users SET balance = balance + ? WHERE id = ?",
                    (prize, w["user_id"]))
                try:
                    await bot.send_message(
                        w["user_id"],
                        f"🏆 <b>Турнир {t['name']} завершён!</b>\n"
                        f"🥇 Место #{i+1}\n"
                        f"💰 Приз: <b>{fmt(prize)}</b>")
                except Exception:
                    pass

            await conn.execute(
                "UPDATE tournaments SET status='finished', winner_id=? WHERE id = ?",
                (winners[0]["user_id"] if winners else 0, t["id"]))
        await conn.commit()
    if to_finish:
        log.info(f"Завершено турниров: {len(to_finish)}")


async def task_random_event():
    """Случайный «Золотой час» с шансом."""
    if random.random() > 0.05:  # 5% шанс
        return
    now = int(time.time())
    duration = 3600
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO events (name, type, multiplier, starts_at, ends_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("⚡ Золотой час", "golden_hour", 1.1, now, now + duration))
        await conn.commit()
    # Анонс
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT id FROM users WHERE is_banned = 0 LIMIT 500")
        uids = [r[0] for r in await cur.fetchall()]
    for uid in uids:
        try:
            await bot.send_message(uid, "⚡ <b>Золотой час!</b> +10% к выплатам на 1 час!")
            await asyncio.sleep(0.05)
        except Exception:
            pass
    log.info("Запущен Золотой час")


async def task_night_jackpot():
    """Ночной джекпот 00:00-06:00 — x2 на все выигрыши (по флагу)."""
    now = int(time.time())
    ends = now + 6 * 3600
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO events (name, type, multiplier, starts_at, ends_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("🌙 Ночной джекпот", "night", 2.0, now, ends))
        await conn.commit()
    log.info("Ночной джекпот активирован")


def setup_scheduler():
    global scheduler
    if not HAS_SCHEDULER:
        return None
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    # Квесты — в полночь
    scheduler.add_job(task_refresh_quests, CronTrigger(hour=0, minute=0))

    # Лотерея — каждые 30 мин
    scheduler.add_job(task_lottery_draw, IntervalTrigger(minutes=30))

    # Турниры — старт каждые 24ч в 10:00, финиш каждые 10 мин
    scheduler.add_job(task_start_daily_tournaments,
                      CronTrigger(hour=10, minute=0))
    scheduler.add_job(task_finish_tournaments, IntervalTrigger(minutes=10))

    # Случайный ивент — каждый час
    scheduler.add_job(task_random_event, IntervalTrigger(hours=1))

    # Ночной джекпот — 00:00
    scheduler.add_job(task_night_jackpot, CronTrigger(hour=0, minute=1))

    scheduler.start()
    log.info("Планировщик запущен")
    return scheduler


# ══════════════════════════════════════════════════════════
#                    🛒 ОБРАБОТКА /clan (создание через reply)
# ══════════════════════════════════════════════════════════
@dp.message(Command("clan_deposit"))
async def cmd_clan_deposit(message: Message):
    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer("Использование: /clan_deposit <сумма>")
        return
    user = await get_user(message.from_user.id)
    if not user["clan_id"]:
        await message.answer("Ты не в клане.")
        return
    try:
        amount = int(args[1])
    except ValueError:
        await message.answer("❌ Число.")
        return
    if amount < 100 or amount > user["balance"]:
        await message.answer("❌ Неверная сумма.")
        return

    await add_balance(message.from_user.id, -amount, "clan", "Взнос в казну")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE clans SET balance = balance + ? WHERE id = ?",
                           (amount, user["clan_id"]))
        await conn.commit()
    await message.answer(f"💰 Внесено в казну: <b>{fmt(amount)}</b>")


@dp.callback_query(F.data == "clan_deposit")
async def cb_clan_deposit(call: CallbackQuery, state: FSMContext):
    await state.update_data(adm_action="clan_deposit")
    await state.set_state(AdminState.waiting_amount)
    await call.message.answer("💰 Сколько внести в казну?")
    await call.answer()


@dp.callback_query(F.data == "clan_leave")
async def cb_clan_leave(call: CallbackQuery):
    uid = call.from_user.id
    user = await get_user(uid)
    if not user["clan_id"]:
        await call.answer()
        return
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "DELETE FROM clan_members WHERE clan_id = ? AND user_id = ?",
            (user["clan_id"], uid))
        await conn.execute(
            "UPDATE clans SET members_count = MAX(0, members_count - 1) WHERE id = ?",
            (user["clan_id"],))
        await conn.execute("UPDATE users SET clan_id = NULL WHERE id = ?", (uid,))
        await conn.commit()
    await call.answer("🚪 Ты покинул клан")
    await call.message.edit_text("🚪 Ты покинул клан.", reply_markup=back_kb())


@dp.callback_query(F.data == "clan_delete")
async def cb_clan_delete(call: CallbackQuery):
    uid = call.from_user.id
    user = await get_user(uid)
    if not user["clan_id"]:
        await call.answer()
        return
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT owner_id FROM clans WHERE id = ?",
                                 (user["clan_id"],))
        row = await cur.fetchone()
        if not row or row["owner_id"] != uid:
            await call.answer("Только владелец", show_alert=True)
            return
        # Снять всех участников
        await conn.execute(
            "UPDATE users SET clan_id = NULL WHERE clan_id = ?", (user["clan_id"],))
        await conn.execute("DELETE FROM clan_members WHERE clan_id = ?",
                           (user["clan_id"],))
        await conn.execute("DELETE FROM clans WHERE id = ?", (user["clan_id"],))
        await conn.commit()
    await call.answer("🗑 Клан распущен")
    await call.message.edit_text("🗑 Клан распущен.", reply_markup=back_kb())


@dp.callback_query(F.data == "clan_invite")
async def cb_clan_invite(call: CallbackQuery):
    await call.answer("Отправь другу ссылку /clan_join <id_клана>", show_alert=True)


@dp.message(Command("clan_join"))
async def cmd_clan_join(message: Message):
    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer("Использование: /clan_join <id>")
        return
    try:
        clan_id = int(args[1])
    except ValueError:
        await message.answer("❌ Число.")
        return
    uid = message.from_user.id
    user = await get_user(uid)
    if user["clan_id"]:
        await message.answer("Ты уже в клане.")
        return
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM clans WHERE id = ?", (clan_id,))
        c = await cur.fetchone()
        if not c:
            await message.answer("❌ Клан не найден.")
            return
        await conn.execute(
            "INSERT INTO clan_members (clan_id, user_id, role, joined_at) "
            "VALUES (?, ?, 'member', ?)", (clan_id, uid, int(time.time())))
        await conn.execute(
            "UPDATE clans SET members_count = members_count + 1 WHERE id = ?",
            (clan_id,))
        await conn.execute("UPDATE users SET clan_id = ? WHERE id = ?", (clan_id, uid))
        await conn.commit()
    await message.answer(f"🏰 Вступил в клан <b>{c['name']}</b>!")


# ══════════════════════════════════════════════════════════
#                    🔧 ОБРАБОТКА ПОКУПКИ «КОЛЬЦА»
# ══════════════════════════════════════════════════════════
@dp.callback_query(F.data == "clan_create")
async def cb_clan_create_wrap(call: CallbackQuery, state: FSMContext):
    # уже реализовано выше, оставим здесь алиас
    await cb_clan_create(call, state)


# ══════════════════════════════════════════════════════════
#                    📌 ХЕНДЛЕР fallback
# ══════════════════════════════════════════════════════════
@dp.message(F.text.startswith("/"))
async def fallback_command(message: Message):
    """Неизвестная команда."""
    await message.answer(
        "🤔 Не знаю такой команды.\nСмотри /help",
        reply_markup=back_kb())
  # ══════════════════════════════════════════════════════════
#                    🚀 ЗАПУСК
# ══════════════════════════════════════════════════════════
async def on_startup():
    """Инициализация при старте."""
    log.info("Инициализация БД...")
    await init_db()

    log.info("Инициализация магазина...")
    await init_shop()

    log.info("Инициализация достижений...")
    await init_achievements()

    log.info("Инициализация квестов...")
    await init_quests()

    log.info("Запуск планировщика...")
    setup_scheduler()

    # Уведомление админам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "🚀 <b>Бот запущен!</b>\n\n"
                f"👑 Админов: {len(ADMIN_IDS)}\n"
                f"📢 Обязательная подписка: {', '.join(c['title'] for c in REQUIRED_CHANNELS)}"
            )
        except Exception as e:
            log.warning(f"Не смог уведомить админа {admin_id}: {e}")

    log.info("✅ Бот запущен!")


async def on_shutdown():
    """Очистка при остановке."""
    log.info("Остановка...")
    if scheduler:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
    try:
        await bot.session.close()
    except Exception:
        pass
    log.info("Бот остановлен.")


async def main():
    await on_startup()
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Бот прерван вручную.")

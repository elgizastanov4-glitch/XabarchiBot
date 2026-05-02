import asyncio
import json
import os
from datetime import datetime

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.types import *
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler


# ================= CONFIG =================
BOT_TOKEN = "8608111715:AAF0WAFMAeSebO0ketA9rhgkNVDw7lIFPMk"
ADMIN_ID = 6884014716

DB = "/tmp/bot.db"
REQUIRED_CHANNEL = "@your_channel"   # 🔥 majburiy kanal

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()


# ================= DB =================
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            ref INTEGER DEFAULT NULL
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS channels(
            channel_id TEXT UNIQUE
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS ads(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            text TEXT,
            photo TEXT,
            buttons TEXT,
            views INTEGER DEFAULT 0,
            sent INTEGER DEFAULT 0,
            premium INTEGER DEFAULT 0
        )
        """)
        await db.commit()


# ================= STATES =================
class AdState(StatesGroup):
    name = State()
    text = State()
    photo = State()
    ask_buttons = State()
    buttons = State()
    schedule = State()


# ================= CHECK JOIN =================
async def check_sub(user_id: int):
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False


# ================= MENU =================
def menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Reklama yaratish")],
            [KeyboardButton(text="📋 Reklamalarim")],
            [KeyboardButton(text="📡 Kanallar")],
            [KeyboardButton(text="📊 Statistika")]
        ],
        resize_keyboard=True
    )


# ================= START =================
@dp.message(F.text == "/start")
async def start(message: Message):
    if not await check_sub(message.from_user.id):
        return await message.answer(f"❌ Botdan foydalanish uchun {REQUIRED_CHANNEL} ga a’zo bo‘ling")

    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)",
                         (message.from_user.id,))
        await db.commit()

    if message.from_user.id != ADMIN_ID:
        return await message.answer("Botga xush kelibsiz")

    await message.answer("🚀 ADMIN PANEL", reply_markup=menu())


# ================= CREATE AD =================
@dp.message(F.text == "📝 Reklama yaratish")
async def create(m: Message, state: FSMContext):
    await state.set_state(AdState.name)
    await m.answer("Nom kiriting:")


@dp.message(AdState.name)
async def name(m: Message, state: FSMContext):
    await state.update_data(name=m.text)
    await state.set_state(AdState.text)
    await m.answer("Matn kiriting:")


@dp.message(AdState.text)
async def text(m: Message, state: FSMContext):
    await state.update_data(text=m.text)
    await state.set_state(AdState.photo)
    await m.answer("Rasm yoki /skip")


@dp.message(AdState.photo, F.photo)
async def photo(m: Message, state: FSMContext):
    await state.update_data(photo=m.photo[-1].file_id)
    await state.set_state(AdState.ask_buttons)
    await m.answer("Tugma? ha/yo‘q")


@dp.message(AdState.photo, F.text == "/skip")
async def skip(m: Message, state: FSMContext):
    await state.update_data(photo=None)
    await state.set_state(AdState.ask_buttons)
    await m.answer("Tugma? ha/yo‘q")


@dp.message(AdState.ask_buttons)
async def ask(m: Message, state: FSMContext):
    if "ha" in m.text.lower():
        await state.set_state(AdState.buttons)
        await m.answer("Nomi|Link")
    else:
        await save(m, state, [])


@dp.message(AdState.buttons)
async def buttons(m: Message, state: FSMContext):
    btns = []
    for i in m.text.split("\n"):
        if "|" in i:
            n, l = i.split("|", 1)
            btns.append({"name": n, "link": l})
    await save(m, state, btns)


# ================= SAVE =================
async def save(m, state, buttons):
    data = await state.get_data()

    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("""
        INSERT INTO ads(name,text,photo,buttons)
        VALUES(?,?,?,?)
        """, (
            data["name"],
            data["text"],
            data.get("photo"),
            json.dumps(buttons)
        ))
        await db.commit()
        ad_id = cur.lastrowid

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Yuborish", callback_data=f"send_{ad_id}")],
        [InlineKeyboardButton(text="⏰ Schedule", callback_data=f"schedule_{ad_id}")],
    ])

    await m.answer("Preview tayyor", reply_markup=kb)
    await state.clear()


# ================= SEND =================
async def send(ad_id):
    async with aiosqlite.connect(DB) as db:
        ad = await (await db.execute("SELECT * FROM ads WHERE id=?", (ad_id,))).fetchone()
        channels = await (await db.execute("SELECT channel_id FROM channels")).fetchall()

    buttons = json.loads(ad[4]) if ad[4] else []

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=b["name"], url=b["link"])]
        for b in buttons
    ]) if buttons else None

    for ch in channels:
        try:
            if ad[3]:
                await bot.send_photo(ch[0], ad[3], caption=ad[2], reply_markup=markup)
            else:
                await bot.send_message(ch[0], ad[2], reply_markup=markup)
        except:
            pass


# ================= STATS =================
@dp.message(F.text == "📊 Statistika")
async def stats(m: Message):
    async with aiosqlite.connect(DB) as db:
        users = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
        ads = await (await db.execute("SELECT COUNT(*) FROM ads")).fetchone()

    await m.answer(f"""
📊 STATISTIKA

👤 Users: {users[0]}
📢 Ads: {ads[0]}
""")


# ================= RUN =================
async def main():
    await init_db()
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

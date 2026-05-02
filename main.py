import asyncio
import json
from datetime import datetime

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.bot import Bot, DefaultBotProperties
from aiogram.types import *
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= CONFIG =================
BOT_TOKEN = "8608111715:AAF0WAFMAeSebO0ketA9rhgkNVDw7lIFPMk"
ADMIN_ID = 6884014716

DB = "bot.db"

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
        CREATE TABLE IF NOT EXISTS channels(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            sent INTEGER DEFAULT 0
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


# ================= ADMIN =================
def is_admin(user_id):
    return user_id == ADMIN_ID


# ================= START =================
@dp.message(F.text == "/start")
async def start(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ruxsat yo‘q")

    await message.answer("🚀 PRO Admin Panel", reply_markup=menu())


# ================= CREATE AD =================
@dp.message(F.text == "📝 Reklama yaratish")
async def create(message: Message, state: FSMContext):
    await state.set_state(AdState.name)
    await message.answer("1️⃣ Nom:")


@dp.message(AdState.name)
async def name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AdState.text)
    await message.answer("2️⃣ Matn:")


@dp.message(AdState.text)
async def text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(AdState.photo)
    await message.answer("3️⃣ Rasm yoki /skip")


@dp.message(AdState.photo, F.photo)
async def photo(message: Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await state.set_state(AdState.ask_buttons)
    await message.answer("4️⃣ Tugma? ha/yo‘q")


@dp.message(AdState.photo, F.text == "/skip")
async def skip(message: Message, state: FSMContext):
    await state.update_data(photo=None)
    await state.set_state(AdState.ask_buttons)
    await message.answer("4️⃣ Tugma? ha/yo‘q")


@dp.message(AdState.ask_buttons)
async def ask(message: Message, state: FSMContext):
    if "ha" in message.text.lower():
        await state.set_state(AdState.buttons)
        await message.answer("Format:\nNomi|Link")
    else:
        await save(message, state, [])


@dp.message(AdState.buttons)
async def buttons(message: Message, state: FSMContext):
    btns = []
    for i in message.text.split("\n"):
        if "|" in i:
            n, l = i.split("|", 1)
            btns.append({"name": n, "link": l})

    await save(message, state, btns)


# ================= SAVE =================
async def save(message, state, buttons):
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
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")]
    ])

    if data.get("photo"):
        await message.answer_photo(data["photo"], caption=data["text"], reply_markup=kb)
    else:
        await message.answer(data["text"], reply_markup=kb)

    await state.clear()


# ================= SEND =================
async def send(ad_id):
    async with aiosqlite.connect(DB) as db:
        ad = await (await db.execute("SELECT * FROM ads WHERE id=?", (ad_id,))).fetchone()
        channels = await (await db.execute("SELECT channel_id FROM channels")).fetchall()

    buttons = json.loads(ad[4]) if ad[4] else []

    markup = None
    if buttons:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=b["name"], url=b["link"])]
            for b in buttons
        ])

    for ch in channels:
        try:
            if ad[3]:
                await bot.send_photo(ch[0], ad[3], caption=ad[2], reply_markup=markup)
            else:
                await bot.send_message(ch[0], ad[2], reply_markup=markup)

            async with aiosqlite.connect(DB) as db:
                await db.execute("UPDATE ads SET sent = sent + 1 WHERE id=?", (ad_id,))
                await db.commit()

        except:
            pass


# ================= SEND CALLBACK =================
@dp.callback_query(F.data.startswith("send_"))
async def send_now(call: CallbackQuery):
    ad_id = int(call.data.split("_")[1])
    await send(ad_id)
    await call.message.answer("📤 Yuborildi")


# ================= SCHEDULE =================
@dp.callback_query(F.data.startswith("schedule_"))
async def schedule(call: CallbackQuery, state: FSMContext):
    await state.update_data(ad_id=int(call.data.split("_")[1]))
    await state.set_state(AdState.schedule)
    await call.message.answer("📅 YYYY-MM-DD HH:MM")


@dp.message(AdState.schedule)
async def set_time(message: Message, state: FSMContext):
    try:
        dt = datetime.strptime(message.text, "%Y-%m-%d %H:%M")
    except:
        return await message.answer("❌ Xato format")

    data = await state.get_data()

    scheduler.add_job(send, "date", run_date=dt, args=[data["ad_id"]])

    await message.answer("⏰ Rejalandi")
    await state.clear()


# ================= ADS LIST + STATS =================
@dp.message(F.text == "📋 Reklamalarim")
async def ads(message: Message):
    async with aiosqlite.connect(DB) as db:
        rows = await (await db.execute("SELECT id,name,views,sent FROM ads")).fetchall()

    for r in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👁 Ko‘rish", callback_data=f"view_{r[0]}"),
             InlineKeyboardButton(text="📤 Yuborish", callback_data=f"send_{r[0]}")]
        ])

        await message.answer(
            f"📢 {r[1]}\n👁 {r[2]} | 📤 {r[3]}",
            reply_markup=kb
        )


@dp.callback_query(F.data.startswith("view_"))
async def view(call: CallbackQuery):
    ad_id = int(call.data.split("_")[1])

    async with aiosqlite.connect(DB) as db:
        ad = await (await db.execute("SELECT * FROM ads WHERE id=?", (ad_id,))).fetchone()
        await db.execute("UPDATE ads SET views = views + 1 WHERE id=?", (ad_id,))
        await db.commit()

    await call.message.answer(ad[2])


# ================= CHANNELS =================
@dp.message(F.text == "📡 Kanallar")
async def channels(message: Message):
    async with aiosqlite.connect(DB) as db:
        rows = await (await db.execute("SELECT channel_id FROM channels")).fetchall()

    text = "\n".join([r[0] for r in rows]) if rows else "Bo‘sh"
    await message.answer("📡 Kanallar:\n" + text)


# ================= CANCEL =================
@dp.callback_query(F.data == "cancel")
async def cancel(call: CallbackQuery):
    await call.message.answer("❌ Bekor")


# ================= RUN =================
async def main():
    await init_db()
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

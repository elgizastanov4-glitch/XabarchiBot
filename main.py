import asyncio
import json
from datetime import datetime

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = "8608111715:AAF0WAFMAeSebO0ketA9rhgkNVDw7lIFPMk"
ADMIN_ID = 6884014716

bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()


# ================= DATABASE =================
async def init_db():
    async with aiosqlite.connect("bot.db") as db:
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
            buttons TEXT
        )
        """)
        await db.commit()


# ================= ADMIN =================
def is_admin(user_id):
    return user_id == ADMIN_ID


# ================= STATES =================
class AdState(StatesGroup):
    name = State()
    text = State()
    photo = State()
    button_ask = State()
    buttons = State()
    schedule = State()
    add_channel = State()


# ================= MENU =================
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Reklama yaratish"),
             KeyboardButton(text="📋 Reklamalarim")],
            [KeyboardButton(text="📡 Kanallar boshqaruvi")]
        ],
        resize_keyboard=True
    )


# ================= START =================
@dp.message(F.text == "/start")
async def start_handler(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("Sizga ruxsat yo'q.")

    await message.answer(
        "Botga xush kelibsiz",
        reply_markup=main_menu()
    )


# ================= CREATE AD =================
@dp.message(F.text == "📝 Reklama yaratish")
async def create_ad(message: Message, state: FSMContext):
    await state.set_state(AdState.name)
    await message.answer("1. Reklama nomi yuboring")


@dp.message(AdState.name)
async def ad_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AdState.text)
    await message.answer("2. Reklama matn yuboring")


@dp.message(AdState.text)
async def ad_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(AdState.photo)
    await message.answer("3. Rasm yuboring yoki /skip")


@dp.message(AdState.photo, F.photo)
async def ad_photo(message: Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await state.set_state(AdState.button_ask)
    await message.answer("4. Tugma qo'shasizmi? (ha/yo'q)")


@dp.message(AdState.photo, F.text == "/skip")
async def skip_photo(message: Message, state: FSMContext):
    await state.update_data(photo=None)
    await state.set_state(AdState.button_ask)
    await message.answer("4. Tugma qo'shasizmi? (ha/yo'q)")


@dp.message(AdState.button_ask)
async def ask_buttons(message: Message, state: FSMContext):
    if message.text.lower() == "ha":
        await state.set_state(AdState.buttons)
        await message.answer(
            "Format:\nNomi|Link\nNomi|Link\n(max 5)"
        )
    else:
        await save_ad_preview(message, state, [])


@dp.message(AdState.buttons)
async def save_buttons(message: Message, state: FSMContext):
    buttons = []

    lines = message.text.split("\n")[:5]

    for line in lines:
        if "|" in line:
            name, link = line.split("|", 1)
            buttons.append({
                "name": name.strip(),
                "link": link.strip()
            })

    await save_ad_preview(message, state, buttons)


async def save_ad_preview(message, state, buttons):
    data = await state.get_data()

    async with aiosqlite.connect("bot.db") as db:
        cursor = await db.execute("""
        INSERT INTO ads(name,text,photo,buttons)
        VALUES(?,?,?,?)
        """, (
            data["name"],
            data["text"],
            data.get("photo"),
            json.dumps(buttons)
        ))
        await db.commit()
        ad_id = cursor.lastrowid

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Tasdiqlash",
                callback_data=f"send_{ad_id}"
            )],
            [InlineKeyboardButton(
                text="⏰ Vaqtga qo'yish",
                callback_data=f"schedule_{ad_id}"
            )],
            [InlineKeyboardButton(
                text="❌ Bekor qilish",
                callback_data="cancel"
            )]
        ]
    )

    if data.get("photo"):
        await message.answer_photo(
            photo=data["photo"],
            caption=data["text"],
            reply_markup=kb
        )
    else:
        await message.answer(
            data["text"],
            reply_markup=kb
        )

    await state.clear()


# ================= SEND AD =================
async def send_ad_to_channels(ad_id):
    async with aiosqlite.connect("bot.db") as db:
        ad_cursor = await db.execute(
            "SELECT * FROM ads WHERE id=?",
            (ad_id,)
        )
        ad = await ad_cursor.fetchone()

        ch_cursor = await db.execute(
            "SELECT channel_id FROM channels"
        )
        channels = await ch_cursor.fetchall()

    buttons = json.loads(ad[4])

    markup = None
    if buttons:
        inline = []
        for btn in buttons:
            inline.append([
                InlineKeyboardButton(
                    text=btn["name"],
                    url=btn["link"]
                )
            ])
        markup = InlineKeyboardMarkup(
            inline_keyboard=inline
        )

    for ch in channels:
        if ad[3]:
            await bot.send_photo(
                ch[0],
                ad[3],
                caption=ad[2],
                reply_markup=markup
            )
        else:
            await bot.send_message(
                ch[0],
                ad[2],
                reply_markup=markup
            )


@dp.callback_query(F.data.startswith("send_"))
async def send_ad(call: CallbackQuery):
    ad_id = int(call.data.split("_")[1])

    await send_ad_to_channels(ad_id)
    await call.message.answer("Reklama yuborildi")


# ================= SCHEDULE =================
@dp.callback_query(F.data.startswith("schedule_"))
async def schedule_ad(call: CallbackQuery, state: FSMContext):
    ad_id = int(call.data.split("_")[1])

    await state.update_data(schedule_id=ad_id)
    await state.set_state(AdState.schedule)

    await call.message.answer(
        "Vaqt kiriting:\n2026-05-10 18:30"
    )


@dp.message(AdState.schedule)
async def set_schedule(message: Message, state: FSMContext):
    dt = datetime.strptime(
        message.text,
        "%Y-%m-%d %H:%M"
    )

    data = await state.get_data()

    scheduler.add_job(
        send_ad_to_channels,
        "date",
        run_date=dt,
        args=[data["schedule_id"]]
    )

    await message.answer("Rejalashtirildi")
    await state.clear()


# ================= ADS LIST =================
@dp.message(F.text == "📋 Reklamalarim")
async def my_ads(message: Message):
    async with aiosqlite.connect("bot.db") as db:
        cursor = await db.execute(
            "SELECT id,name FROM ads"
        )
        ads = await cursor.fetchall()

    if not ads:
        return await message.answer("Reklama yo'q")

    for ad in ads:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👁 Ko'rish",
                        callback_data=f"view_{ad[0]}"
                    ),
                    InlineKeyboardButton(
                        text="📤 Yuborish",
                        callback_data=f"send_{ad[0]}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⏰ Rejalashtirish",
                        callback_data=f"schedule_{ad[0]}"
                    ),
                    InlineKeyboardButton(
                        text="🗑 O'chirish",
                        callback_data=f"delete_{ad[0]}"
                    )
                ]
            ]
        )

        await message.answer(
            f"📢 {ad[1]}",
            reply_markup=kb
        )


@dp.callback_query(F.data.startswith("view_"))
async def view_ad(call: CallbackQuery):
    ad_id = int(call.data.split("_")[1])

    async with aiosqlite.connect("bot.db") as db:
        cursor = await db.execute(
            "SELECT * FROM ads WHERE id=?",
            (ad_id,)
        )
        ad = await cursor.fetchone()

    if ad[3]:
        await call.message.answer_photo(
            ad[3],
            caption=ad[2]
        )
    else:
        await call.message.answer(ad[2])


@dp.callback_query(F.data.startswith("delete_"))
async def delete_ad(call: CallbackQuery):
    ad_id = int(call.data.split("_")[1])

    async with aiosqlite.connect("bot.db") as db:
        await db.execute(
            "DELETE FROM ads WHERE id=?",
            (ad_id,)
        )
        await db.commit()

    await call.message.answer("O'chirildi")


# ================= CHANNELS =================
@dp.message(F.text == "📡 Kanallar boshqaruvi")
async def channels_menu(message: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Kanal ulash")],
            [KeyboardButton(text="🔴 Uzish")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "Kanal boshqaruvi",
        reply_markup=kb
    )


@dp.message(F.text == "➕ Kanal ulash")
async def add_channel(message: Message, state: FSMContext):
    await state.set_state(AdState.add_channel)
    await message.answer(
        "Kanal username yuboring\nMasalan: @kanalim"
    )


@dp.message(AdState.add_channel)
async def save_channel(message: Message, state: FSMContext):
    channel = message.text.strip()

    try:
        admins = await bot.get_chat_administrators(channel)

        bot_is_admin = False
        for admin in admins:
            if admin.user.id == (await bot.me()).id:
                bot_is_admin = True

        if not bot_is_admin:
            return await message.answer(
                "Bot kanalga admin qilinmagan"
            )

        async with aiosqlite.connect("bot.db") as db:
            await db.execute("""
            INSERT OR IGNORE INTO channels(channel_id)
            VALUES(?)
            """, (channel,))
            await db.commit()

        await message.answer("Kanal qo'shildi")

    except:
        await message.answer("Kanal topilmadi")

    await state.clear()


@dp.message(F.text == "🔴 Uzish")
async def remove_channel(message: Message):
    async with aiosqlite.connect("bot.db") as db:
        cursor = await db.execute(
            "SELECT channel_id FROM channels"
        )
        channels = await cursor.fetchall()

    if not channels:
        return await message.answer("Kanal yo'q")

    for ch in channels:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="O'chirish",
                    callback_data=f"remove_{ch[0]}"
                )]
            ]
        )

        await message.answer(
            ch[0],
            reply_markup=kb
        )


@dp.callback_query(F.data.startswith("remove_"))
async def remove_channel_confirm(call: CallbackQuery):
    channel = call.data.replace("remove_", "")

    async with aiosqlite.connect("bot.db") as db:
        await db.execute(
            "DELETE FROM channels WHERE channel_id=?",
            (channel,)
        )
        await db.commit()

    await call.message.answer("Kanal uzildi")


@dp.callback_query(F.data == "cancel")
async def cancel_action(call: CallbackQuery):
    await call.message.answer("Bekor qilindi")


# ================= RUN =================
async def main():
    await init_db()
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# ======================= CONFIGURATION =======================
BOT_TOKEN = "9181789422:AAGJka8WVewPtes1msIueW6Ph0ilcwUYlIw"
DB_FILE = "users_data.json"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()

# ======================= DATABASE =======================
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ======================= KEYBOARDS =======================
def get_tz_keyboard(page: int = 1):
    """
    All UTC offsets from UTC-12 to UTC+14.
    page=1: UTC-12 to UTC+0
    page=2: UTC+1 to UTC+14
    """
    builder_buttons = []
    
    if page == 1:
        offsets = list(range(-12, 1))
        row = []
        for off in offsets:
            sign = "+" if off > 0 else ""
            btn_text = f"UTC{sign}{off}"
            row.append(InlineKeyboardButton(text=btn_text, callback_data=f"tz_set:{off}"))
            if len(row) == 3:
                builder_buttons.append(row)
                row = []
        if row:
            builder_buttons.append(row)
        builder_buttons.append([
            InlineKeyboardButton(text="➡️ Show UTC+1 ... UTC+14", callback_data="tz_page:2")
        ])
    else:
        offsets = list(range(1, 15))
        row = []
        for off in offsets:
            btn_text = f"UTC+{off}"
            row.append(InlineKeyboardButton(text=btn_text, callback_data=f"tz_set:{off}"))
            if len(row) == 3:
                builder_buttons.append(row)
                row = []
        if row:
            builder_buttons.append(row)
        builder_buttons.append([
            InlineKeyboardButton(text="⬅️ Show UTC-12 ... UTC+0", callback_data="tz_page:1")
        ])

    return InlineKeyboardMarkup(inline_keyboard=builder_buttons)

def get_sleep_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="22:00"), KeyboardButton(text="22:30")],
            [KeyboardButton(text="23:00"), KeyboardButton(text="23:30")],
            [KeyboardButton(text="00:00"), KeyboardButton(text="00:30")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_break_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Every 1 hour"), KeyboardButton(text="Every 2 hours")],
            [KeyboardButton(text="Every 3 hours"), KeyboardButton(text="Bedtime only")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_done_inline_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="I put my phone away.", callback_data="phone_put_away")
        ]]
    )

class ProfileForm(StatesGroup):
    timezone = State()
    sleep_time = State()
    break_interval = State()

def parse_tz_offset(text: str) -> int:
    text = text.strip()
    if "UTC" in text:
        part = text.split("UTC")[1].split()[0]
        return int(part.replace("+", ""))
    val = int(text.replace("+", ""))
    if -12 <= val <= 14:
        return val
    raise ValueError

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Welcome! I'm your digital detox assistant.**\n\n"
        "I'll help you disconnect on time and take regular breaks from your screen.\n\n"
        "**Step 1 of 3: Select your timezone.**\n"
        "Choose your UTC offset below (use the button to switch pages), or simply type it (e.g. `+3` or `-5`):",
        parse_mode="Markdown",
        reply_markup=get_tz_keyboard(page=1)
    )
    await state.set_state(ProfileForm.timezone)

@dp.callback_query(F.data.startswith("tz_page:"))
async def on_tz_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=get_tz_keyboard(page=page))
    await callback.answer()

@dp.callback_query(F.data.startswith("tz_set:"), ProfileForm.timezone)
async def on_tz_selected(callback: CallbackQuery, state: FSMContext):
    offset_hours = int(callback.data.split(":")[1])
    await state.update_data(tz_offset=offset_hours)
    tz_str = f"UTC{'+' if offset_hours >= 0 else ''}{offset_hours}"

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"Timezone saved: **{tz_str}**.\n\n"
        "**Step 2 of 3:** What time do you want to put your phone away at night?\n"
        "Pick a preset button below or enter a custom time (e.g., `22:45`):",
        parse_mode="Markdown",
        reply_markup=get_sleep_keyboard()
    )
    await state.set_state(ProfileForm.sleep_time)
    await callback.answer()

@dp.message(ProfileForm.timezone)
async def process_timezone(message: Message, state: FSMContext):
    try:
        offset_hours = parse_tz_offset(message.text)
    except Exception:
        await message.answer(
            "⚠Please tap one of the buttons or type a valid offset from -12 to 14 (e.g., `+3`):",
            reply_markup=get_tz_keyboard(page=1)
        )
        return

    await state.update_data(tz_offset=offset_hours)
    tz_str = f"UTC{'+' if offset_hours >= 0 else ''}{offset_hours}"

    await message.answer(
        f"Timezone saved: **{tz_str}**.\n\n"
        "**Step 2 of 3:** What time do you want to put your phone away at night?\n"
        "Pick a preset button below or enter a custom time (e.g., `22:45`):",
        parse_mode="Markdown",
        reply_markup=get_sleep_keyboard()
    )
    await state.set_state(ProfileForm.sleep_time)

@dp.message(ProfileForm.sleep_time)
async def process_sleep_time(message: Message, state: FSMContext):
    text = message.text.strip().replace(".", ":")
    try:
        parts = text.split(":")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
    except Exception:
        await message.answer(
            "Invalid format. Tap a button below or write time as `23:00` or `22:30`:",
            reply_markup=get_sleep_keyboard()
        )
        return

    await state.update_data(sleep_h=h, sleep_m=m, sleep_str=f"{h:02d}:{m:02d}")

    await message.answer(
        "**Step 3 of 3:** How often would you like daytime screen break reminders?",
        reply_markup=get_break_keyboard()
    )
    await state.set_state(ProfileForm.break_interval)

@dp.message(ProfileForm.break_interval)
async def process_break_interval(message: Message, state: FSMContext):
    choice = message.text.strip()
    interval_map = {
        "Every 1 hour": 1,
        "Every 2 hours": 2,
        "Every 3 hours": 3,
        "Bedtime only": 0
    }

    if choice not in interval_map:
        await message.answer(
            "Please select an option from the menu buttons below:",
            reply_markup=get_break_keyboard()
        )
        return

    data = await state.get_data()
    user_id = str(message.from_user.id)
    tz_offset = data["tz_offset"]

    db = load_db()
    db[user_id] = {
        "tz_offset": tz_offset,
        "sleep_h": data["sleep_h"],
        "sleep_m": data["sleep_m"],
        "sleep_str": data["sleep_str"],
        "break_hours": interval_map[choice],
        "registered_at": datetime.now(timezone.utc).isoformat()
    }
    save_db(db)
    schedule_user_reminders(user_id, db[user_id])

    tz_str = f"UTC{'+' if tz_offset >= 0 else ''}{tz_offset}"
    await state.clear()
    await message.answer(
        f"**Your schedule is set and active!**\n\n"
        f"Timezone: **{tz_str}**\n"
        f"Bedtime disconnect: **{data['sleep_str']}**\n"
        f"Daytime pauses: **{choice}**\n\n"
        "When your evening reminder arrives, tap the «I put my phone away.» button. "
        "If you don't confirm within 10 minutes, I will send a follow-up alert!\n\n"
        "_(Send /start at any time to reconfigure)_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
async def send_sleep_reminder(chat_id: int, user_tz: timezone):
    await bot.send_message(
        chat_id,
        "**Time to put your phone away!**\n\n"
        "Plug it in away from your bed and tap the button below to confirm you are heading to sleep.",
        parse_mode="Markdown",
        reply_markup=get_done_inline_keyboard()
    )

    check_time = datetime.now(user_tz) + timedelta(minutes=10)
    retry_job_id = f"retry_{chat_id}"

    scheduler.add_job(
        send_sleep_retry,
        trigger="date",
        run_date=check_time,
        args=[chat_id],
        id=retry_job_id,
        replace_existing=True
    )

async def send_sleep_retry(chat_id: int):
    await bot.send_message(
        chat_id,
        "**Are you still scrolling?**\n\n"
        "It's been 10 minutes and you haven't checked in. Put your screen away and let your eyes and mind rest!",
        reply_markup=get_done_inline_keyboard()
    )

@dp.callback_query(F.data == "phone_put_away")
async def on_phone_put_away(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    retry_job_id = f"retry_{chat_id}"

    if scheduler.get_job(retry_job_id):
        scheduler.remove_job(retry_job_id)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Great job! Screen is off. Have a restful night and sleep well.")
    await callback.answer("Confirmed!")

async def send_break_reminder(chat_id: int):
    await bot.send_message(
        chat_id,
        "**Time for a quick screen break!**\n\n"
        "Look into the distance for 30 seconds, stretch your neck and drink some water.",
        parse_mode="Markdown"
    )

def schedule_user_reminders(user_id: str, profile: dict):
    chat_id = int(user_id)
    sleep_job_id = f"sleep_{user_id}"
    break_job_id = f"break_{user_id}"

    if scheduler.get_job(sleep_job_id):
        scheduler.remove_job(sleep_job_id)
    if scheduler.get_job(break_job_id):
        scheduler.remove_job(break_job_id)

    offset_hours = profile.get("tz_offset", 0)
    user_tz = timezone(timedelta(hours=offset_hours))

    scheduler.add_job(
        send_sleep_reminder,
        trigger=CronTrigger(hour=profile["sleep_h"], minute=profile["sleep_m"], timezone=user_tz),
        args=[chat_id, user_tz],
        id=sleep_job_id,
        replace_existing=True
    )

    interval = profile.get("break_hours", 0)
    if interval > 0:
        scheduler.add_job(
            send_break_reminder,
            trigger=IntervalTrigger(hours=interval, timezone=user_tz),
            args=[chat_id],
            id=break_job_id,
            replace_existing=True
        )

def restore_saved_schedules():
    db = load_db()
    for user_id, profile in db.items():
        try:
            schedule_user_reminders(user_id, profile)
        except Exception as e:
            logging.error(f"Failed to restore schedule for {user_id}: {e}")
async def main():
    scheduler.start()
    restore_saved_schedules()
    print(">>> Bot is running! Press Ctrl+C to stop. <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")
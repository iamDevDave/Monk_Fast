import json
import os
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

# Load environment variables from .env file
load_dotenv()
BOT_API_TOKEN = os.getenv("BOT_API_TOKEN")

# Load schedules and reminder data from the data.json file
def load_schedules():
    if os.path.exists('data.json'):
        with open('data.json', 'r') as f:
            return json.load(f)  # Return the data as a dictionary
    return {}  # Return an empty dictionary if no data file exists

# Save the schedules and reminder data to the data.json file
def save_schedules(schedules):
    with open('data.json', 'w') as f:
        json.dump(schedules, f, indent=4)  # Write the data to the file

# Initialize FastAPI
app = FastAPI()
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# Calculate time left until the schedule time
def calculate_time_left(schedule_time):
    time_left = datetime.strptime(schedule_time, '%Y-%m-%d %H:%M:%S') - datetime.now()
    days = time_left.days
    hours, remainder = divmod(time_left.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{days} days {hours} hours {minutes} minutes"

# Store active reminder tasks in memory
active_tasks = {}

# Send periodic reminders to the user
async def send_reminders(user_id, schedule_time, interval_minutes, context):
    while True:
        user_schedule = schedules.get(str(user_id), {})
        if not user_schedule.get("reminder", {}).get("active", False):
            break
        time_left = calculate_time_left(schedule_time)
        await context.bot.send_message(user_id, f"Reminder: {time_left} left!")
        await asyncio.sleep(interval_minutes * 60)

# Set reminder command
async def set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        await update.message.reply_text("No message found. Please try again.")
        return

    try:
        interval_minutes = int(context.args[0])
        user_id = update.message.chat_id
        username = update.message.chat.username
        schedule_time = schedules.get(str(user_id), {}).get("schedule_time")

        if not schedule_time:
            await update.message.reply_text("You need to set a schedule first using /set <days> <hours>.")
            return

        reminder_data = {
            "interval_minutes": interval_minutes,
            "user_id": user_id,
            "username": username,
            "schedule_time": schedule_time
        }

        schedules[str(user_id)]["reminder"] = reminder_data
        save_schedules(schedules)

        await update.message.reply_text(f"Reminder set for {username} to repeat every {interval_minutes} minutes.")

        if user_id in active_tasks:
            active_tasks[user_id].cancel()

        active_tasks[user_id] = asyncio.create_task(send_reminders(user_id, schedule_time, interval_minutes, context))

    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /reminder <interval_in_minutes>")

# Set schedule command
async def set_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /set <days> <hours>")
        return

    try:
        days = int(context.args[0])
        hours = int(context.args[1])
        user_id = update.message.chat_id
        username = update.message.chat.username

        schedule_time = datetime.now() + timedelta(days=days, hours=hours)
        schedules[str(user_id)] = {
            "user_id": user_id,
            "username": username,
            "schedule_time": schedule_time.strftime('%Y-%m-%d %H:%M:%S')
        }

        save_schedules(schedules)
        await update.message.reply_text(f"Schedule set for {username} at {schedule_time}.")
        await update.message.reply_text("Now set a reminder using /reminder <interval_in_minutes>.")
    except ValueError:
        await update.message.reply_text("Usage: /set <days> <hours>")

# Start reminder command
async def start_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    user_schedule = schedules.get(str(user_id), {})

    if "reminder" not in user_schedule or not user_schedule["reminder"].get("active"):
        await update.message.reply_text("Starting your reminder!")
        if "reminder" not in user_schedule:
            user_schedule["reminder"] = {}
        user_schedule["reminder"]["active"] = True
        schedules[str(user_id)] = user_schedule
        save_schedules(schedules)

        interval_minutes = user_schedule["reminder"].get("interval_minutes")
        schedule_time = user_schedule["schedule_time"]

        active_tasks[user_id] = asyncio.create_task(send_reminders(user_id, schedule_time, interval_minutes, context))
    else:
        await update.message.reply_text("Your reminder is already active.")

# Stop reminder command
async def stop_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    user_schedule = schedules.get(str(user_id), {})

    if "reminder" in user_schedule and user_schedule["reminder"].get("active"):
        user_schedule["reminder"]["active"] = False
        schedules[str(user_id)] = user_schedule
        save_schedules(schedules)

        if user_id in active_tasks:
            active_tasks[user_id].cancel()

        await update.message.reply_text("Your reminder has been stopped.")
    else:
        await update.message.reply_text("You don't have an active reminder to stop.")

# Delete schedule command
async def delete_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    if str(user_id) in schedules:
        del schedules[str(user_id)]
        save_schedules(schedules)
        await update.message.reply_text("Your schedule has been deleted.")
    else:
        await update.message.reply_text("You don't have any schedule to delete.")

# Reset reminder interval command
async def reset_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    try:
        new_interval = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /resetrmd <interval_in_minutes>")
        return

    user_schedule = schedules.get(str(user_id), {})

    if "reminder" in user_schedule and user_schedule["reminder"].get("active"):
        user_schedule["reminder"]["interval_minutes"] = new_interval
        schedules[str(user_id)] = user_schedule
        save_schedules(schedules)

        await update.message.reply_text(f"Your reminder interval has been reset to {new_interval} minutes.")

        if user_id in active_tasks:
            active_tasks[user_id].cancel()

        schedule_time = user_schedule["schedule_time"]
        active_tasks[user_id] = asyncio.create_task(send_reminders(user_id, schedule_time, new_interval, context))
    else:
        await update.message.reply_text("You need to activate the reminder first using /startreminder.")

# Greet users
async def greet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.message.chat.username
    greeting_response = f"Hello, {user_name}!"
    await update.message.reply_text(greeting_response)

# Initialize the bot and schedule
def main():
    global schedules
    schedules = load_schedules()

    application = Application.builder().token(BOT_API_TOKEN).build()

    application.add_handler(CommandHandler("set", set_schedule))
    application.add_handler(CommandHandler("reminder", set_reminder))
    application.add_handler(CommandHandler("start", start_reminder))
    application.add_handler(CommandHandler("stop", stop_reminder))
    application.add_handler(CommandHandler("delete", delete_schedule))
    application.add_handler(CommandHandler("resetrmd", reset_reminder))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, greet))

    application.run_polling(drop_pending_updates=True)

@app.get("/")
async def run_telegram_bot():
    await main()
    return JSONResponse({"status": "Bot is running!"})

if __name__ == "__main__":
    main()

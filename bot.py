import os
import re
import logging
import asyncio
from threading import Thread
from datetime import datetime, timezone, timedelta
from flask import Flask
from supabase import create_client, Client
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    # ចាប់យក PORT ពី Render ប្រសិនបើគ្មានទេ ប្រើ Port 8080 ជាផ្លូវការ
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ហៅ function នេះមុនពេលរ៉ាន់ Telegram Bot
keep_alive()


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# ---------------------------------------------------------------
# ១. បង្កើត Dummy Web Server សម្រាប់ Render Health Check
# ---------------------------------------------------------------
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "Bot is running fine!", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# ---------------------------------------------------------------
# ២. កំណត់ទិន្នន័យ និង Environment Variables
# ---------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not all([BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    raise ValueError("❌ សូមកំណត់ Environment Variables ឱ្យបានគ្រប់គ្រាន់!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BAD_WORDS = ["អាឆ្កែ", "អាខ្វាក់", "អាល្ងង់", "fuck", "shit", "bitch", "scam"]
LINK_PATTERN = re.compile(
    r'(https?://[^\s]+)|(www\.[^\s]+)|(t\.me/[^\s]+)|(telegram\.me/[^\s]+)',
    re.IGNORECASE
)

MAX_WARNS = 3
MUTE_HOURS = 24

# ---------------------------------------------------------------
# ៣. Helper Functions សម្រាប់ Supabase
# ---------------------------------------------------------------
async def delete_message_after_delay(message, delay_seconds: int):
    await asyncio.sleep(delay_seconds)
    try:
        await message.delete()
    except Exception:
        pass

def get_and_update_warns(user_id: int, chat_id: int) -> int:
    res = supabase.table("user_warns").select("warn_count").eq("user_id", user_id).execute()
    if res.data:
        current_warns = res.data[0]["warn_count"] + 1
        supabase.table("user_warns").update({
            "warn_count": current_warns,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("user_id", user_id).execute()
    else:
        current_warns = 1
        supabase.table("user_warns").insert({
            "user_id": user_id,
            "chat_id": chat_id,
            "warn_count": 1
        }).execute()
    return current_warns

def reset_warns(user_id: int):
    supabase.table("user_warns").update({"warn_count": 0}).eq("user_id", user_id).execute()

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    return chat_member.status in ["administrator", "creator"]

# ---------------------------------------------------------------
# ៤. Admin Commands (/warns & /unwarn)
# ---------------------------------------------------------------
async def warns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ មានតែ Admin ទេដែលနိုင်သည်။")
        return

    reply_msg = update.message.reply_to_message
    if not reply_msg or not reply_msg.from_user:
        await update.message.reply_text("⚠️ សូម Reply លើសាររបស់សមាជិកដែលអ្នកចង់មើលចំនួន Warn!")
        return

    target_user = reply_msg.from_user
    res = supabase.table("user_warns").select("warn_count").eq("user_id", target_user.id).execute()
    warn_count = res.data[0]["warn_count"] if res.data else 0

    await update.message.reply_text(
        f"📊 <b>ព័ត៌មានការព្រមាន (Warns)</b>\n"
        f"👤 សមាជិក: {target_user.mention_html()}\n"
        f"⚠️ ចំនួន Warn បច្ចុប្បន្ន: <b>{warn_count}/{MAX_WARNS}</b> ដង",
        parse_mode="HTML"
    )

async def unwarn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ មានតែ Admin ទេដែលနိုင်သည်။")
        return

    reply_msg = update.message.reply_to_message
    if not reply_msg or not reply_msg.from_user:
        await update.message.reply_text("⚠️ សូម Reply លើសាររបស់សមាជិកដែលអ្នកចង់ Reset Warn!")
        return

    target_user = reply_msg.from_user
    reset_warns(target_user.id)

    await update.message.reply_text(
        f"✅ បាន Reset ចំនួន Warn របស់ {target_user.mention_html()} មក <b>០</b> វិញរៀបរយហើយ!",
        parse_mode="HTML"
    )

# ---------------------------------------------------------------
# ៥. Main Filter & Chat Logger Handler
# ---------------------------------------------------------------
async def filter_and_log_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat or not message.text:
        return

    text_lower = message.text.lower()
    full_name = user.full_name
    username = f"@{user.username}" if user.username else "គ្មាន Username"

    # រំលងប្រសិនបើជា Admin
    chat_member = await context.bot.get_chat_member(chat.id, user.id)
    if chat_member.status in ["administrator", "creator"]:
        # Save Chat Log ធម្មតា
        try:
            supabase.table("chat_logs").insert({
                "chat_id": chat.id, "group_title": chat.title,
                "user_id": user.id, "full_name": full_name,
                "username": username, "message_text": message.text
            }).execute()
        except Exception:
            pass
        return

    # ពិនិត្យ Link និង Bad Words
    contains_link = bool(LINK_PATTERN.search(message.text))
    contains_bad_word = any(
        re.search(r'\b' + re.escape(word.lower()) + r'\b', text_lower) or word.lower() in text_lower
        for word in BAD_WORDS
    )

    if contains_link or contains_bad_word:
        reason = "ផ្ញើ Link/Spam" if contains_link else "ប្រើប្រាស់ពាក្យមិនគួរសម"
        try:
            await message.delete()
            warn_count = get_and_update_warns(user.id, chat.id)

            if warn_count >= MAX_WARNS:
                no_permissions = ChatPermissions(
                    can_send_messages=False, can_send_media_messages=False,
                    can_send_other_messages=False, can_add_web_page_previews=False
                )
                until_time = datetime.now(timezone.utc) + timedelta(hours=MUTE_HOURS)
                await context.bot.restrict_chat_member(
                    chat_id=chat.id, user_id=user.id,
                    permissions=no_permissions, until_date=until_time
                )
                reset_warns(user.id)
                warning_text = (
                    f"🔇 {user.mention_html()} ត្រូវបាន <b>Mute រយៈពេល {MUTE_HOURS} ម៉ោង</b> ស្វ័យប្រវត្តិ!\n"
                    f"⚠️ <b>មូលហេតុ:</b> ល្មើសច្បាប់គ្រប់ {MAX_WARNS} ដង ({reason})"
                )
            else:
                warning_text = (
                    f"⚠️ {user.mention_html()} សាររបស់អ្នកត្រូវបានលុប ដោយសារ <b>{reason}</b>!\n"
                    f"❗️ <b>ការព្រមាន:</b> {warn_count}/{MAX_WARNS} ដង\n"
                    f"<i>(សារនេះនឹងលុបស្វ័យប្រវត្តិក្នុងរយៈពេល ១០ វិនាទី)</i>"
                )

            warning_msg = await context.bot.send_message(
                chat_id=chat.id, text=warning_text, parse_mode="HTML"
            )

            supabase.table("chat_logs").insert({
                "chat_id": chat.id, "group_title": chat.title,
                "user_id": user.id, "full_name": full_name,
                "username": username, "message_text": f"[WARN {warn_count}/{MAX_WARNS} - {reason}]: {message.text}"
            }).execute()

            asyncio.create_task(delete_message_after_delay(warning_msg, 10))
            return
        except Exception as e:
            print(f"❌ Error: {e}")

    # សារធម្មតា
    try:
        supabase.table("chat_logs").insert({
            "chat_id": chat.id, "group_title": chat.title if chat.title else "Private Chat",
            "user_id": user.id, "full_name": full_name,
            "username": username, "message_text": message.text
        }).execute()
    except Exception as e:
        print(f"❌ Error saving chat: {e}")

# ---------------------------------------------------------------
# ៦. Main Function
# ---------------------------------------------------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("warns", warns_command))
    app.add_handler(CommandHandler("unwarn", unwarn_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, filter_and_log_chat))

    print("🤖 Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
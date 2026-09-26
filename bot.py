import os
import re
import asyncio
from threading import Thread
from flask import Flask
from supabase import create_client, Client
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==========================================
# 1. FLASK HEALTH CHECK SERVER (សម្រាប់ RENDER)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    # ចាប់យក PORT ពី Render (Default: 10000 ឬ 8080)
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# រ៉ាន់ Flask ក្នុង Background Thread
flask_thread = Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()

# ==========================================
# 2. CONFIGURATION & SUPABASE SETUP
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ ERROR: Missing Environment Variables!")

# បង្កើត Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Regex សម្រាប់ចាប់ Link
URL_REGEX = r'(https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})'

# ==========================================
# 3. HELPER FUNCTIONS (SUPABASE OPERATIONS)
# ==========================================
def save_chat_log(user_id: int, username: str, chat_id: int, message_text: str):
    """រក្សាទុកសារចូលក្នុង Table chat_logs"""
    try:
        data = {
            "user_id": user_id,
            "username": username or "Unknown",
            "chat_id": chat_id,
            "message": message_text
        }
        res = supabase.table("chat_logs").insert(data).execute()
        print(f"✅ Saved log to Supabase: {res.data}")
    except Exception as e:
        print(f"❌ Error saving chat log: {e}")

def get_user_warn_count(user_id: int, chat_id: int) -> int:
    """ទាញយកចំនួន Warn របស់ User"""
    try:
        res = supabase.table("user_warns").select("warn_count").eq("user_id", user_id).eq("chat_id", chat_id).execute()
        if res.data:
            return res.data[0]["warn_count"]
        return 0
    except Exception as e:
        print(f"❌ Error getting warns: {e}")
        return 0

def add_user_warn(user_id: int, username: str, chat_id: int) -> int:
    """បន្ថែមចំនួន Warn និងរក្សាទុកក្នុង user_warns"""
    try:
        current_warns = get_user_warn_count(user_id, chat_id)
        new_warns = current_warns + 1
        
        data = {
            "user_id": user_id,
            "username": username or "Unknown",
            "chat_id": chat_id,
            "warn_count": new_warns
        }
        
        # Upsert (Insert ឬ Update ប្រសិនបើមាន Record ស្រាប់)
        supabase.table("user_warns").upsert(data, on_conflict="user_id,chat_id").execute()
        print(f"⚠️ Warn added for {user_id}. Total warns: {new_warns}")
        return new_warns
    except Exception as e:
        print(f"❌ Error updating warn: {e}")
        return 1

# ==========================================
# 4. TELEGRAM BOT HANDLERS
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /start"""
    await update.message.reply_text("សួស្តី! Bot គ្រប់គ្រង Group និង Log ទិន្នន័យកំពុងដំណើរការ។")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler ចាប់យកគ្រប់សារទាំងអស់ក្នុង Group"""
    if not update.message or not update.message.text:
        return

    user = update.message.from_user
    chat = update.message.chat
    text = update.message.text

    print(f"📩 Received message from {user.first_name} ({user.id}) in {chat.title}: {text}")

    # 1. រក្សាទុកសារចូល Supabase chat_logs
    save_chat_log(
        user_id=user.id,
        username=user.username,
        chat_id=chat.id,
        message_text=text
    )

    # 2. ពិនិត្យមើលថាមាន Link ក្នុងសារដែរឬទេ (Moderation)
    if re.search(URL_REGEX, text):
        print(f"🚨 Link detected from user {user.id}")
        
        try:
            # លុបសារដែលមាន Link
            await update.message.delete()
            
            # បន្ថែម Warn Count
            warn_count = add_user_warn(user.id, user.username, chat.id)
            
            if warn_count >= 3:
                # ប្រសិនបើ Warn គ្រប់ ៣ ដង ធ្វើការ Mute User រយៈពេល ២៤ ម៉ោង
                await context.bot.restrict_chat_member(
                    chat_id=chat.id,
                    user_id=user.id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=int(asyncio.get_event_loop().time() + 86400)
                )
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"🚫 {user.mention_html()} ត្រូវបាន Mute រយៈពេល ២៤ម៉ោង ដោយសារផ្ញើ Link លើសពី ៣ដង!",
                    parse_mode="HTML"
                )
            else:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"⚠️ {user.mention_html()} មិនអនុញ្ញាតឱ្យផ្ញើ Link ក្នុង Group នេះទេ! (ការព្រមានលើកទី {warn_count}/3)",
                    parse_mode="HTML"
                )
        except Exception as e:
            print(f"❌ Failed to enforce moderation rules: {e}")

# ==========================================
# 5. MAIN ASYNC RUNNER
# ==========================================
async def main():
    print("🚀 Starting Telegram Bot...")
    
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ចាប់ផ្តើម Bot Polling
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    print("✅ Bot is active and listening for messages...")

    # រក្សា Loop ឱ្យរ៉ាន់រហូត ២៤/៧
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped manually.")
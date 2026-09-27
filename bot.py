import os
import re
import asyncio
import threading
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from supabase import create_client, Client

# ==========================================
# 1. SETUP ENVIRONMENT & SUPABASE
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not TELEGRAM_BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Error: Missing required Environment Variables!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Regex សម្រាប់ស្វែងរក Link/URL
URL_REGEX = r"(https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9-]+\.[a-z]{2,}[^\s]*)"

# ==========================================
# 2. FLASK HEALTH CHECK SERVER (For UptimeRobot)
# ==========================================
app = Flask(__name__)

@app.route("/")
def health_check():
    # ឆ្លើយតប 200 OK ទៅកាន់ UptimeRobot ដើម្បីការពារ Error 502 / Sleep
    return "Bot status OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ==========================================
# 3. SUPABASE HELPER FUNCTIONS
# ==========================================
def save_chat_log(user_id: int, username: str, full_name: str, chat_id: int, group_title: str, message_text: str):
    """រក្សាទុកសារចូលក្នុង Table chat_logs ឱ្យត្រូវតាម Schema របស់ Supabase"""
    try:
        data = {
            "user_id": user_id,
            "username": username or "Unknown",
            "full_name": full_name or "Unknown",
            "chat_id": chat_id,
            "group_title": group_title or "Private",
            "message_text": message_text
        }
        res = supabase.table("chat_logs").insert(data).execute()
        print(f"✅ Saved log to Supabase: {res.data}")
    except Exception as e:
        print(f"❌ Error saving chat log: {e}")

def check_and_warn_user(user_id: int, chat_id: int):
    """ពិនិត្យ និងកើនចំនួន Warn របស់ User ក្នុង Supabase"""
    try:
        # ស្វែងរកមើលថា User នេះធ្លាប់មាន Record ក្នុង Table user_warns ដែរឬទេ
        res = supabase.table("user_warns").select("warn_count").eq("user_id", user_id).eq("chat_id", chat_id).execute()
        
        if res.data and len(res.data) > 0:
            # បើមានស្រាប់ បូកបន្ថែម 1
            current_warn = res.data[0]["warn_count"]
            new_warn = current_warn + 1
            
            supabase.table("user_warns").update({
                "warn_count": new_warn,
                "updated_at": "now()"
            }).eq("user_id", user_id).eq("chat_id", chat_id).execute()
        else:
            # បើមិនទាន់មាន បង្កើតថ្មីត្រឹម 1
            new_warn = 1
            supabase.table("user_warns").insert({
                "user_id": user_id,
                "chat_id": chat_id,
                "warn_count": new_warn
            }).execute()
            
        return new_warn
    except Exception as e:
        print(f"❌ Error updating warn count: {e}")
        return 1

# ==========================================
# 4. TELEGRAM BOT HANDLERS
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ជម្រាបសួរ! Bot កំពុងដំណើរការ និងកត់ត្រាសារក្នុង Group ដោយស្វ័យប្រវត្តិ។")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.message.from_user
    chat = update.message.chat
    text = update.message.text

    # 1. រក្សាទុកសារគ្រប់ប្រភេទចូល Supabase chat_logs
    save_chat_log(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        chat_id=chat.id,
        group_title=chat.title,
        message_text=text
    )

    # 2. ពិនិត្យមើល Moderation ក្នុង Group
    if chat.type in ["group", "supergroup"]:
        # ពិនិត្យមើលថាតើជា Admin ដែរឬទេ (Admin អាចផ្ញើ Link បាន)
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status in ["administrator", "creator"]:
                return
        except Exception as e:
            print(f"⚠️ Could not check admin status: {e}")

        # ពិនិត្យមើលថាតើមាន Link ក្នុង Message ឬទេ
        has_url = False
        
        # វិធីទី១៖ ឆែកតាម Telegram Entities (ច្បាស់លាស់បំផុត)
        if update.message.entities:
            for entity in update.message.entities:
                if entity.type in ["url", "text_link"]:
                    has_url = True
                    break
                    
        # វិធីទី២៖ ឆែកតាម Regex
        if not has_url and re.search(URL_REGEX, text):
            has_url = True

        # បើជាសមាជិកធម្មតា ហើយមានផ្ញើ Link
        if has_url:
            try:
                # លុបសារដែលមាន Link
                await update.message.delete()
                
                # បូកចំនួន Warn ក្នុង Supabase
                warn_count = check_and_warn_user(user.id, chat.id)
                
                if warn_count >= 3:
                    # Mute អ្នកប្រើប្រាស់ ២៤ ម៉ោង បើគ្រប់ ៣ ដង
                    await context.bot.restrict_chat_member(
                        chat_id=chat.id,
                        user_id=user.id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=int(update.message.date.timestamp()) + 86400
                    )
                    await context.bot.send_message(
                        chat_id=chat.id,
                        text=f"🚫 {user.full_name} ត្រូវបាន Mute រយៈពេល ២៤ ម៉ោង ដោយសារតែការផ្ញើ Link លើសពី ៣ ដង!"
                    )
                else:
                    # ផ្ញើសារព្រមាន
                    await context.bot.send_message(
                        chat_id=chat.id,
                        text=f"⚠️ {user.full_name} មិនអនុញ្ញាតឱ្យផ្ញើ Link ក្នុង Group នេះទេ!\n(ការព្រមានលើកទី {warn_count}/3)"
                    )
            except Exception as e:
                print(f"❌ Error in moderation: {e}")

# ==========================================
# 5. MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    # បើក Flask Server លើ Thread ផ្សេង
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # រ៉ាន់ Telegram Bot
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("🚀 Telegram Bot is running...")
    application.run_polling(drop_pending_updates=True)
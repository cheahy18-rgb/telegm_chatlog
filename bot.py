import os
import re
import threading
from flask import Flask, render_template_string
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
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
# 2. FLASK HEALTH CHECK & DASHBOARD SERVER
# ==========================================
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="km">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Chat Logs Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; padding: 20px; font-family: sans-serif; }
        .table-container { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .badge-group { background-color: #0d6efd; }
    </style>
</head>
<body>
    <div class="container-fluid">
        <h2 class="mb-4 text-center">📊 Telegram Chat Logs Dashboard</h2>
        <div class="table-container">
            <table class="table table-hover table-striped align-middle">
                <thead class="table-dark">
                    <tr>
                        <th>ID</th>
                        <th>កាលបរិច្ឆេទ</th>
                        <th>Group / Chat</th>
                        <th>ឈ្មោះអ្នកផ្ញើ</th>
                        <th>Username</th>
                        <th>សារ (Message)</th>
                    </tr>
                </thead>
                <tbody>
                    {% for log in logs %}
                    <tr>
                        <td>{{ log.id }}</td>
                        <td>{{ log.created_at[:19].replace('T', ' ') }}</td>
                        <td><span class="badge badge-group">{{ log.group_title }}</span></td>
                        <td><strong>{{ log.full_name }}</strong></td>
                        <td>@{{ log.username }}</td>
                        <td>{{ log.message_text }}</td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="6" class="text-center">មិនទាន់មានទិន្នន័យនៅឡើយទេ</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

@app.route("/")
def health_check():
    return "Bot status OK", 200

@app.route("/logs")
def view_logs():
    try:
        res = supabase.table("chat_logs").select("*").order("created_at", desc=True).limit(100).execute()
        logs = res.data or []
        return render_template_string(HTML_TEMPLATE, logs=logs)
    except Exception as e:
        return f"Error loading logs: {e}", 500

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ==========================================
# 3. SUPABASE HELPER FUNCTIONS
# ==========================================
def save_chat_log(user_id: int, username: str, full_name: str, chat_id: int, group_title: str, message_text: str):
    """រក្សាទុកសារចូលក្នុង Table chat_logs"""
    try:
        data = {
            "user_id": user_id,
            "username": username or "Unknown",
            "full_name": full_name or "Unknown",
            "chat_id": chat_id,
            "group_title": group_title or "Private",
            "message_text": message_text
        }
        supabase.table("chat_logs").insert(data).execute()
    except Exception as e:
        print(f"❌ Error saving chat log: {e}")

def check_and_warn_user(user_id: int, chat_id: int):
    """ពិនិត្យ និងកើនចំនួន Warn របស់ User ក្នុង Supabase"""
    try:
        res = supabase.table("user_warns").select("warn_count").eq("user_id", user_id).eq("chat_id", chat_id).execute()
        
        if res.data and len(res.data) > 0:
            current_warn = res.data[0]["warn_count"]
            new_warn = current_warn + 1
            
            supabase.table("user_warns").update({
                "warn_count": new_warn,
                "updated_at": "now()"
            }).eq("user_id", user_id).eq("chat_id", chat_id).execute()
        else:
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

def reset_user_warns(user_id: int, chat_id: int):
    """លុប/កំណត់ចំនួន Warn ឡើងវិញ (Reset ទៅ 0)"""
    try:
        supabase.table("user_warns").update({
            "warn_count": 0,
            "updated_at": "now()"
        }).eq("user_id", user_id).eq("chat_id", chat_id).execute()
    except Exception as e:
        print(f"❌ Error resetting warn count: {e}")

# ==========================================
# 4. TELEGRAM BOT HANDLERS & ADMIN BUTTONS
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
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in ["administrator", "creator"]:
            return

        # ពិនិត្យមើលថាតើមាន Link ក្នុង Message ឬទេ
        has_url = False
        if update.message.entities:
            for entity in update.message.entities:
                if entity.type in ["url", "text_link"]:
                    has_url = True
                    break
                    
        if not has_url and re.search(URL_REGEX, text):
            has_url = True

        # បើជាសមាជិកធម្មតា ហើយមានផ្ញើ Link
        if has_url:
            try:
                await update.message.delete()
                warn_count = check_and_warn_user(user.id, chat.id)
                
                if warn_count >= 3:
                    # Mute អ្នកប្រើប្រាស់ ២៤ ម៉ោង
                    await context.bot.restrict_chat_member(
                        chat_id=chat.id,
                        user_id=user.id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=int(update.message.date.timestamp()) + 86400
                    )
                    
                    # បង្កើត Inline Buttons សម្រាប់ Admin
                    keyboard = [
                        [
                            InlineKeyboardButton("🔊 Unmute (ដោះលែង)", callback_data=f"unmute_{user.id}"),
                            InlineKeyboardButton("👞 Kick (ដេញចេញ)", callback_data=f"kick_{user.id}")
                        ],
                        [
                            InlineKeyboardButton("🔄 Reset Warnings", callback_data=f"reset_{user.id}")
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await context.bot.send_message(
                        chat_id=chat.id,
                        text=(
                            f"🚫 <b>{user.full_name}</b> (@{user.username or 'NoUsername'}) "
                            f"ត្រូវបាន Mute រយៈពេល ២៤ ម៉ោង ដោយសារតែការផ្ញើ Link លើសពី ៣ ដង!\n\n"
                            f"🛠️ <b>សម្រាប់ Admin រៀបចំ៖</b>"
                        ),
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                else:
                    await context.bot.send_message(
                        chat_id=chat.id,
                        text=f"⚠️ {user.full_name} មិនអនុញ្ញាតឱ្យផ្ញើ Link ក្នុង Group នេះទេ!\n(ការព្រមានលើកទី {warn_count}/3)"
                    )
            except Exception as e:
                print(f"❌ Error in moderation: {e}")

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """គ្រប់គ្រងការចុច Button (Unmute / Kick / Reset) ដោយបញ្ជាក់សិទ្ធិ Admin"""
    query = update.callback_query
    await query.answer()

    clicker_user_id = query.from_user.id
    chat_id = query.message.chat_id

    # ពិនិត្យមើលថាតើអ្នកចុច Button ជា Admin ឬទេ
    clicker_member = await context.bot.get_chat_member(chat_id, clicker_user_id)
    if clicker_member.status not in ["administrator", "creator"]:
        await query.answer("⚠️ មានតែ Admin ទេដែល៖ អាចចុចប្រើប្រាស់ Button នេះបាន!", show_alert=True)
        return

    data = query.data
    action, target_user_id = data.split("_")
    target_user_id = int(target_user_id)

    try:
        if action == "unmute":
            # បើកសិទ្ធិផ្ញើសារវិញ (Unmute)
            full_permissions = ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
            await context.bot.restrict_chat_member(chat_id=chat_id, user_id=target_user_id, permissions=full_permissions)
            reset_user_warns(target_user_id, chat_id)
            
            await query.edit_message_text(
                text=f"✅ User ID: <code>{target_user_id}</code> ត្រូវបាន Admin <b>{query.from_user.full_name}</b> ដោះ Unmute និង Reset ការព្រមានរួចរាល់!",
                parse_mode="HTML"
            )

        elif action == "kick":
            # ដេញចេញពី Group (Kick / Ban & Unban)
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_user_id)
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=target_user_id)
            
            await query.edit_message_text(
                text=f"👞 User ID: <code>{target_user_id}</code> ត្រូវបាន Admin <b>{query.from_user.full_name}</b> Kick ចេញពី Group រួចរាល់!",
                parse_mode="HTML"
            )

        elif action == "reset":
            # Reset Warn Count ទៅ 0
            reset_user_warns(target_user_id, chat_id)
            await query.answer("🔄 បាន Reset ការព្រមានរបស់ User នេះទៅ ០ វិញរួចរាល់!", show_alert=True)

    except Exception as e:
        print(f"❌ Error handling button action: {e}")
        await query.answer("❌ មានបញ្ហាក្នុងការអនុវត្តសកម្មភាពនេះ (សូមពិនិត្យសិទ្ធិ Admin របស់ Bot)!", show_alert=True)

# ==========================================
# 5. MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(CallbackQueryHandler(handle_button_click))
    
    print("🚀 Telegram Bot with Admin Control Buttons is running...")
    application.run_polling(drop_pending_updates=True)

import os
import re
import datetime
import threading
import requests
import math
from flask import Flask, render_template_string, request, redirect, url_for
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
        .chat-image { max-width: 150px; max-height: 150px; border-radius: 8px; border: 1px solid #ddd; cursor: pointer; }
        .chat-image:hover { transform: scale(1.05); transition: 0.2s; }
    </style>
</head>
<body>
    <div class="container-fluid">
        <h2 class="mb-4 text-center">📊 Telegram Chat Logs Dashboard</h2>
        
        <div class="row mb-3 align-items-center">
            <!-- Filter Form តាម Group -->
            <div class="col-md-6 offset-md-1">
                <form method="GET" action="/logs">
                    <div class="input-group">
                        <label class="input-group-text" for="groupSelect">ជ្រើសរើស Group:</label>
                        <select class="form-select" id="groupSelect" name="group" onchange="this.form.submit()">
                            <option value="ALL" {% if selected_group == 'ALL' %}selected{% endif %}>--- Group ទាំងអស់ ---</option>
                            {% for g in groups %}
                                <option value="{{ g }}" {% if selected_group == g %}selected{% endif %}>{{ g }}</option>
                            {% endfor %}
                        </select>
                    </div>
                </form>
            </div>

            <!-- Form ប៊ូតុង Delete -->
            <div class="col-md-4 text-end">
                <form method="POST" action="/delete-old-logs" onsubmit="return confirm('តើអ្នកពិតជាចង់លុប Chat Logs ដែលចាស់ជាង ៧ ថ្ងៃសម្រាប់ {% if selected_group == 'ALL' %}Group ទាំងអស់{% else %}Group {{ selected_group }}{% endif %} មែនទេ?');">
                    <input type="hidden" name="target_group" value="{{ selected_group }}">
                    <button type="submit" class="btn btn-danger">
                        🗑️ លុប Logs > ៧ ថ្ងៃ {% if selected_group != 'ALL' %}({{ selected_group }}){% endif %}
                    </button>
                </form>
            </div>
        </div>

        <div class="table-container">

            <!-- 1. Pagination ផ្នែកខាងលើ (Top Pagination) -->
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div>
                    <span class="text-muted">បង្ហាញទំព័រទី <strong>{{ page }}</strong> នៃ <strong>{{ total_pages }}</strong> (សរុប {{ total_count }} ជួរ)</span>
                </div>
                <nav>
                    <ul class="pagination mb-0">
                        <!-- ប៊ូតុង មុន (<) -->
                        <li class="page-item {% if page <= 1 %}disabled{% endif %}">
                            <a class="page-link" href="{{ url_for('view_logs', group=selected_group, page=page-1) }}">❮ មុន</a>
                        </li>
                        
                        <!-- លេខទំព័រ -->
                        <li class="page-item active">
                            <span class="page-link">{{ page }}</span>
                        </li>

                        <!-- ប៊ូតុង បន្ទាប់ (>) -->
                        <li class="page-item {% if page >= total_pages %}disabled{% endif %}">
                            <a class="page-link" href="{{ url_for('view_logs', group=selected_group, page=page+1) }}">បន្ទាប់ ❯</a>
                        </li>
                    </ul>
                </nav>
            </div>

            <!-- តារាងបង្ហាញទិន្នន័យ (Logs Table) -->
            <table class="table table-hover table-striped align-middle">
                <thead class="table-dark">
                    <tr>
                        <th>ID</th>
                        <th>កាលបរិច្ឆេទ</th>
                        <th>Group / Chat</th>
                        <th>ឈ្មោះអ្នកផ្ញើ</th>
                        <th>Username</th>
                        <th>សារ / រូបភាព</th>
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
                        <td>
                            {% if log.message_text.startswith('http') and (log.message_text.endswith('.jpg') or log.message_text.endswith('.png') or 'chat_images' in log.message_text) %}
                                <a href="{{ log.message_text }}" target="_blank">
                                    <img src="{{ log.message_text }}" class="chat-image" alt="Uploaded Image">
                                </a>
                            {% else %}
                                {{ log.message_text }}
                            {% endif %}
                        </td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="6" class="text-center">មិនទាន់មានទិន្នន័យនៅឡើយទេ</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>

            <!-- 2. Pagination ផ្នែកខាងក្រោម (Bottom Pagination) -->
            <div class="d-flex justify-content-between align-items-center mt-3">
                <div>
                    <span class="text-muted">បង្ហាញទំព័រទី <strong>{{ page }}</strong> នៃ <strong>{{ total_pages }}</strong> (សរុប {{ total_count }} ជួរ)</span>
                </div>
                <nav>
                    <ul class="pagination mb-0">
                        <!-- ប៊ូតុង មុន (<) -->
                        <li class="page-item {% if page <= 1 %}disabled{% endif %}">
                            <a class="page-link" href="{{ url_for('view_logs', group=selected_group, page=page-1) }}">❮ មុន</a>
                        </li>
                        
                        <!-- លេខទំព័រ -->
                        <li class="page-item active">
                            <span class="page-link">{{ page }}</span>
                        </li>

                        <!-- ប៊ូតុង បន្ទាប់ (>) -->
                        <li class="page-item {% if page >= total_pages %}disabled{% endif %}">
                            <a class="page-link" href="{{ url_for('view_logs', group=selected_group, page=page+1) }}">បន្ទាប់ ❯</a>
                        </li>
                    </ul>
                </nav>
            </div>

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
        selected_group = request.args.get("group", "ALL")
        page = request.args.get("page", 1, type=int)
        per_page = 100  # បង្ហាញ ១០០ ជួរក្នុង ១ ទំព័រ

        # ១. ទាញយកបញ្ជី Group ទាំងអស់សម្រាប់ Dropdown
        groups_res = supabase.table("chat_logs").select("group_title").execute()
        unique_groups = sorted(list(set([item["group_title"] for item in groups_res.data if item.get("group_title")])))

        # ២. រាប់ចំនួនទិន្នន័យសរុប (Total Count) ដើម្បីគណនាចំនួនទំព័រ
        count_query = supabase.table("chat_logs").select("id", count="exact")
        if selected_group != "ALL":
            count_query = count_query.eq("group_title", selected_group)
        count_res = count_query.execute()
        total_count = count_res.count or 0
        total_pages = max(1, math.ceil(total_count / per_page))

        # ប្រសិនបើកែប្រែ Page ខុស ឱ្យមក Page 1 វិញ
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages

        # ៣. គណនា Range (Offset) សម្រាប់ Supabase Pagination (100 ជួរ)
        start = (page - 1) * per_page
        end = start + per_page - 1

        query = supabase.table("chat_logs").select("*")
        if selected_group != "ALL":
            query = query.eq("group_title", selected_group)

        # ទាញយកទិន្នន័យតាម Range ( start -> end )
        res = query.order("created_at", desc=True).range(start, end).execute()
        logs = res.data or []

        return render_template_string(
            HTML_TEMPLATE,
            logs=logs,
            groups=unique_groups,
            selected_group=selected_group,
            page=page,
            total_pages=total_pages,
            total_count=total_count
        )
    except Exception as e:
        return f"Error loading logs: {e}", 500

@app.route("/delete-old-logs", methods=["POST"])
def delete_old_logs():
    """លុបទិន្នន័យ Chat Logs ដែលមានអាយុកាលលើសពី ៧ ថ្ងៃ"""
    try:
        target_group = request.form.get("target_group", "ALL")
        seven_days_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).isoformat()
        
        query = supabase.table("chat_logs").delete().lt("created_at", seven_days_ago)
        if target_group != "ALL":
            query = query.eq("group_title", target_group)
            
        res = query.execute()
        print(f"🗑️ Deleted logs older than 7 days for group [{target_group}]: {res.data}")
        
        return redirect(url_for("view_logs", group=target_group))
    except Exception as e:
        return f"Error deleting old logs: {e}", 500

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ==========================================
# 3. SUPABASE HELPER FUNCTIONS & IMAGE UPLOAD
# ==========================================
def save_chat_log(user_id: int, username: str, full_name: str, chat_id: int, group_title: str, message_text: str):
    """រក្សាទុកសារ/URL រូបភាព ចូលក្នុង Table chat_logs"""
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

async def upload_photo_to_supabase(photo_file) -> str:
    """ទាញយករូបភាពពី Telegram រួច Upload ទៅ Supabase Storage Bucket 'chat_images'"""
    try:
        # ទាញយក File path ពី Telegram Server
        file = await photo_file.get_file()
        file_bytes = await file.download_as_bytearray()

        # បង្កើតឈ្មោះ File មិនឱ្យស្ទួន (Unique Filename)
        filename = f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{photo_file.file_id[-6:]}.jpg"
        
        # Upload ទៅ Supabase Storage Bucket 'chat_images'
        supabase.storage.from_("chat_images").upload(
            path=filename,
            file=bytes(file_bytes),
            file_options={"content-type": "image/jpeg"}
        )

        # យក Public URL របស់រូបភាពមកប្រើ
        public_url = supabase.storage.from_("chat_images").get_public_url(filename)
        return public_url
    except Exception as e:
        print(f"❌ Error uploading photo to Supabase: {e}")
        return "[📷 រូបភាពមិនអាចរក្សាទុកបានទេ]"

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
    await update.message.reply_text("👋 ជម្រាបសួរ! Bot កំពុងដំណើរការ និងកត់ត្រាសារ/រូបភាពក្នុង Group ដោយស្វ័យប្រវត្តិ។")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.message.from_user
    chat = update.message.chat
    text = update.message.text or update.message.caption or ""

    # ១. ប្រសិនបើសារនោះជារូបភាព (Photo)
    if update.message.photo:
        # យករូបភាពដែលមាន Resolution ច្បាស់ជាងគេ (រូបចុងក្រោយក្នុង Array)
        photo = update.message.photo[-1]
        image_url = await upload_photo_to_supabase(photo)
        
        # បើមាន Caption ជាមួយរូបភាព ឱ្យភ្ជាប់ជាមួយគ្នា
        content_to_save = image_url if not text else f"{image_url}\n\n📝 Caption: {text}"
        
        save_chat_log(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            chat_id=chat.id,
            group_title=chat.title,
            message_text=content_to_save
        )

    # ២. ប្រសិនបើសារនោះជាអត្ថបទ (Text)
    elif text:
        save_chat_log(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            chat_id=chat.id,
            group_title=chat.title,
            message_text=text
        )

    # ៣. ពិនិត្យមើល Moderation ក្នុង Group (សម្រាប់អត្ថបទ/Link)
    if chat.type in ["group", "supergroup"] and text:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in ["administrator", "creator"]:
            return

        has_url = False
        if update.message.entities:
            for entity in update.message.entities:
                if entity.type in ["url", "text_link"]:
                    has_url = True
                    break
                    
        if not has_url and re.search(URL_REGEX, text):
            has_url = True

        if has_url:
            try:
                await update.message.delete()
                warn_count = check_and_warn_user(user.id, chat.id)
                
                if warn_count >= 3:
                    await context.bot.restrict_chat_member(
                        chat_id=chat.id,
                        user_id=user.id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=int(update.message.date.timestamp()) + 86400
                    )
                    
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

    clicker_member = await context.bot.get_chat_member(chat_id, clicker_user_id)
    if clicker_member.status not in ["administrator", "creator"]:
        await query.answer("⚠️ មានតែ Admin ទេដែល៖ អាចចុចប្រើប្រាស់ Button នេះបាន!", show_alert=True)
        return

    data = query.data
    action, target_user_id = data.split("_")
    target_user_id = int(target_user_id)

    try:
        if action == "unmute":
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
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_user_id)
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=target_user_id)
            
            await query.edit_message_text(
                text=f"👞 User ID: <code>{target_user_id}</code> ត្រូវបាន Admin <b>{query.from_user.full_name}</b> Kick ចេញពី Group រួចរាល់!",
                parse_mode="HTML"
            )

        elif action == "reset":
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
    # បន្ថែម Filter PHOTO ដើម្បីកត់ត្រារូបភាព
    application.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & (~filters.COMMAND), handle_message))
    application.add_handler(CallbackQueryHandler(handle_button_click))
    
    print("🚀 Telegram Bot with Photo Logger & Dashboard is running...")
    application.run_polling(drop_pending_updates=True)

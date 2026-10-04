import logging
import os
import threading
from flask import Flask, redirect, render_template_string, request, url_for
from supabase import Client, create_client
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

# ----------------------------------------------------
# ១. Setup Logging
# ----------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------
# ២. Read Environment Variables
# ----------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "YOUR_SUPABASE_URL")

# អនុសាសន៍៖ ប្រើ Service Role Key ដើម្បី Bypass RLS
SUPABASE_KEY = os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY",
    os.environ.get("SUPABASE_KEY", "YOUR_SUPABASE_KEY"),
)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
STORAGE_BUCKET = "chat_images"

# ----------------------------------------------------
# ៣. Create Flask App (Web Dashboard)
# ----------------------------------------------------
app = Flask(__name__)

# HTML Template (Dropdown List + Sequential Numbering #)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Chat Logs</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; padding: 20px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .card { border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .table { vertical-align: middle; }
        .badge-group { background-color: #0d6efd; }
        .chat-img { max-width: 180px; max-height: 180px; border-radius: 8px; border: 1px solid #ddd; transition: transform 0.2s; }
        .chat-img:hover { transform: scale(1.05); }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="card p-4 mb-4">
            <h2 class="mb-3">💬 Telegram Chat Logs Dashboard</h2>
            
            <!-- Dropdown Filter Form -->
            <form method="GET" action="/logs" class="row g-3 mb-3 align-items-center">
                <div class="col-auto">
                    <select name="group" class="form-select" onchange="this.form.submit()">
                        <option value="">-- Select All Groups --</option>
                        {% for g in groups %}
                            <option value="{{ g }}" {% if g == group_filter %}selected{% endif %}>
                                {{ g }}
                            </option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-auto">
                    <button type="submit" class="btn btn-primary">Filter</button>
                    <a href="/logs" class="btn btn-secondary">Reset</a>
                </div>
            </form>
            
            <!-- Logs Table -->
            <div class="table-responsive">
                <table class="table table-hover table-striped border">
                    <thead class="table-dark">
                        <tr>
                            <th style="width: 60px;">#</th>
                            <th>Date/Time (UTC)</th>
                            <th>Group Title</th>
                            <th>Full Name</th>
                            <th>Username</th>
                            <th>Message / Image</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for log in logs %}
                        <tr>
                            <!-- លេខរៀងរាប់ចាប់ពី ១ ឡើងទៅ -->
                            <td><strong>{{ loop.index }}</strong></td>
                            <td><small class="text-muted">{{ log.created_at }}</small></td>
                            <td><span class="badge badge-group">{{ log.group_title }}</span></td>
                            <td><strong>{{ log.full_name }}</strong></td>
                            <td>@{{ log.username }}</td>
                            <td>
                                {% if log.message_text and log.message_text.startswith('http') and ('.jpg' in log.message_text or '.png' in log.message_text or '.jpeg' in log.message_text) %}
                                    {% set parts = log.message_text.split(' ', 1) %}
                                    <div class="mb-1">
                                        <a href="{{ parts[0] }}" target="_blank">
                                            <img src="{{ parts[0] }}" class="chat-img" alt="Uploaded Image">
                                        </a>
                                    </div>
                                    {% if parts|length > 1 %}
                                        <small class="text-dark d-block">📝 {{ parts[1] }}</small>
                                    {% endif %}
                                {% else %}
                                    {{ log.message_text }}
                                {% endif %}
                            </td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="6" class="text-center text-muted">No chat logs found.</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>
"""


# Root Route
@app.route("/")
def home():
    return redirect(url_for("view_logs"))


# Dashboard Logs Route
@app.route("/logs")
def view_logs():
    try:
        group_filter = request.args.get("group", "").strip()

        # ១. ទាញយកបញ្ជីឈ្មោះ Group ទាំងអស់មកធ្វើជា Option ក្នុង Dropdown List
        groups_res = supabase.table("chat_logs").select("group_title").execute()
        all_groups = set()
        if groups_res.data:
            for item in groups_res.data:
                if item.get("group_title"):
                    all_groups.add(item["group_title"])
        sorted_groups = sorted(list(all_groups))

        # ២. Query ទិន្នន័យ logs តាម Group ដែលបានជ្រើសរើស
        query = (
            supabase.table("chat_logs")
            .select("*")
            .order("id", desc=True)
            .limit(100)
        )

        if group_filter:
            query = query.eq("group_title", group_filter)

        response = query.execute()
        logs_data = response.data or []

        return render_template_string(
            HTML_TEMPLATE,
            logs=logs_data,
            groups=sorted_groups,
            group_filter=group_filter,
        )
    except Exception as e:
        logger.error(f"Error fetching logs from Supabase: {e}")
        return f"<h3>Error loading logs: {e}</h3>", 500


def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)


# ----------------------------------------------------
# ៤. Telegram Message Handler (គាំទ្រ Text & Photo Upload)
# ----------------------------------------------------
async def handle_telegram_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    try:
        msg = update.message or update.channel_post
        if not msg:
            return

        chat_id = msg.chat.id if msg.chat else None
        group_title = (
            msg.chat.title
            if (msg.chat and msg.chat.title)
            else "Private Chat"
        )

        user_id = None
        full_name = "Unknown"
        username = "No Username"

        if msg.from_user:
            user_id = msg.from_user.id
            first_name = msg.from_user.first_name or ""
            last_name = msg.from_user.last_name or ""
            full_name = f"{first_name} {last_name}".strip() or "Unknown"
            username = msg.from_user.username or "No Username"

        message_text = ""

        if msg.text:
            message_text = msg.text

        elif msg.photo:
            caption = msg.caption or ""
            try:
                photo_file = await msg.photo[-1].get_file()
                file_bytes = await photo_file.download_as_bytearray()

                filename = f"img_{msg.message_id}_{photo_file.file_unique_id}.jpg"

                supabase.storage.from_(STORAGE_BUCKET).upload(
                    path=filename,
                    file=bytes(file_bytes),
                    file_options={"content-type": "image/jpeg"},
                )

                image_url = supabase.storage.from_(
                    STORAGE_BUCKET
                ).get_public_url(filename)

                message_text = (
                    f"{image_url} {caption}".strip()
                    if caption
                    else image_url
                )
            except Exception as img_err:
                logger.error(f"❌ Upload Image Error: {img_err}")
                message_text = (
                    f"[រូបភាពមិនអាចទាញយកបាន] {caption}".strip()
                )

        else:
            message_text = msg.caption or "[Media/Attachment]"

        payload = {
            "chat_id": chat_id,
            "group_title": group_title,
            "user_id": user_id,
            "full_name": full_name,
            "username": username,
            "message_text": message_text,
        }

        res = supabase.table("chat_logs").insert(payload).execute()
        logger.info(
            f"✅ Saved to Supabase: [{group_title}] {full_name}: {message_text}"
        )

    except Exception as e:
        logger.error(f"❌ Supabase Insert Error: {e}")


# ----------------------------------------------------
# ៥. Main Runner (Multithreading)
# ----------------------------------------------------
def main():
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN":
        logger.error("❌ TELEGRAM_BOT_TOKEN មិនទាន់បានកំណត់ឡើយ!")
        return

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    msg_filter = (filters.TEXT | filters.PHOTO) & (~filters.COMMAND)
    telegram_app.add_handler(
        MessageHandler(msg_filter, handle_telegram_message)
    )

    telegram_app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

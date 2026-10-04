import datetime
import math
import os
from flask import Flask, flash, redirect, render_template_string, request, url_for
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = "super_secret_key_for_flash_messages"

# ----------------------------------------------------
# ១. ការភ្ជាប់ទៅកាន់ Supabase
# ----------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "YOUR_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "YOUR_SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ----------------------------------------------------
# ២. HTML Template (UI Dashboard)
# ----------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="km">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Chat Logs Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; padding: 20px; font-family: 'Kantumruy Pro', sans-serif, system-ui; }
        .table-container { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .badge-group { background-color: #0d6efd; }
        .chat-image { max-width: 150px; max-height: 150px; border-radius: 8px; border: 1px solid #ddd; cursor: pointer; }
        .chat-image:hover { transform: scale(1.05); transition: 0.2s; }

        /* Style សម្រាប់ Table Scrollbar & ប៊ូតុងរំកិល ▲ ▼ */
        .dashboard-table-wrapper {
            position: relative;
        }

        .custom-table-scroll {
            max-height: 650px;
            overflow-y: auto;
            border: 1px solid #dee2e6;
            border-radius: 6px;
        }

        .table-scroll-buttons {
            position: absolute;
            right: -45px;
            top: 50%;
            transform: translateY(-50%);
            display: flex;
            flex-direction: column;
            gap: 8px;
            z-index: 100;
        }

        .btn-scroll-action {
            width: 38px;
            height: 38px;
            background-color: #0d6efd;
            color: #ffffff;
            border: none;
            border-radius: 50%;
            cursor: pointer;
            font-size: 14px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.2);
            transition: background-color 0.2s, transform 0.1s;
        }

        .btn-scroll-action:hover {
            background-color: #0b5ed7;
            transform: scale(1.1);
        }
    </style>
</head>
<body>
    <div class="container-fluid" style="max-width: 95%;">
        <h2 class="mb-4 text-center">📊 Telegram Chat Logs Dashboard</h2>
        
        <!-- ផ្នែកបង្ហាញសារ Alert -->
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }} alert-dismissible fade show text-center mb-4" role="alert">
                <strong>{{ message }}</strong>
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
              </div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <div class="row mb-3 align-items-center">
            <!-- Filter Form តាម Group -->
            <div class="col-md-5">
                <form method="GET" action="/logs">
                    {% if is_admin %}
                    <input type="hidden" name="admin" value="true">
                    {% endif %}
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

            <!-- Form Delete បង្ហាញតែពេលជា Admin ប៉ុណ្ណោះ -->
            <div class="col-md-7 text-end">
                {% if is_admin %}
                <form method="POST" action="/delete-old-logs" class="d-inline-flex float-end" onsubmit="return confirm('តើអ្នកពិតជាចង់លុប Chat Logs ដែលចាស់ជាងចំនួនថ្ងៃដែលបានជ្រើសរើសមែនទេ?');">
                    <input type="hidden" name="target_group" value="{{ selected_group }}">
                    <input type="hidden" name="is_admin_req" value="true">
                    
                    <div class="input-group">
                        <label class="input-group-text" for="daysSelect">លុបចាស់ជាង:</label>
                        <select class="form-select" id="daysSelect" name="days_threshold" style="max-width: 130px;">
                            <option value="3">3 ថ្ងៃ</option>
                            <option value="7" selected>7 ថ្ងៃ</option>
                            <option value="14">14 ថ្ងៃ</option>
                            <option value="30">30 ថ្ងៃ</option>
                            <option value="60">60 ថ្ងៃ</option>
                        </select>
                        <button type="submit" class="btn btn-danger">
                            🗑️ លុប Logs
                        </button>
                    </div>
                </form>
                {% else %}
                <span class="badge bg-secondary p-2 fs-6">👁️ របៀបមើលប៉ុណ្ណោះ (Visitor Mode)</span>
                {% endif %}
            </div>
        </div>

        <div class="table-container">

            <!-- ១. Pagination ផ្នែកខាងលើ -->
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div>
                    <span class="text-muted">បង្ហាញទំព័រទី <strong>{{ page }}</strong> នៃ <strong>{{ total_pages }}</strong> (សរុប {{ total_count }} ជួរ)</span>
                </div>
                <nav>
                    <ul class="pagination mb-0">
                        <li class="page-item {% if page <= 1 %}disabled{% endif %}">
                            <a class="page-link" href="{{ url_for('view_logs', group=selected_group, page=page-1, admin='true' if is_admin else None) }}">❮ មុន</a>
                        </li>
                        <li class="page-item active">
                            <span class="page-link">{{ page }}</span>
                        </li>
                        <li class="page-item {% if page >= total_pages %}disabled{% endif %}">
                            <a class="page-link" href="{{ url_for('view_logs', group=selected_group, page=page+1, admin='true' if is_admin else None) }}">បន្ទាប់ ❯</a>
                        </li>
                    </ul>
                </nav>
            </div>

            <!-- ២. Table Wrapper & Scroll Buttons ▲ ▼ -->
            <div class="dashboard-table-wrapper">
                
                <div id="table-scroll-container" class="custom-table-scroll">
                    <table class="table table-hover table-striped align-middle mb-0">
                        <thead class="table-dark" style="position: sticky; top: 0; z-index: 10;">
                            <tr>
                                <th>ល.រ</th>
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
                                <!-- គណនាលេខរៀងរត់ (1, 2, 3...) -->
                                <td><strong>{{ (page - 1) * 100 + loop.index }}</strong></td>
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
                </div>

                <!-- ប៊ូតុងរំកិល ▲ និង ▼ -->
                <div class="table-scroll-buttons">
                    <button type="button" class="btn-scroll-action" onclick="scrollTableContainer(-250)" title="Scroll ឡើងលើ">▲</button>
                    <button type="button" class="btn-scroll-action" onclick="scrollTableContainer(250)" title="Scroll ចុះក្រោម">▼</button>
                </div>

            </div>

            <!-- ៣. Pagination ផ្នែកខាងក្រោម -->
            <div class="d-flex justify-content-between align-items-center mt-3">
                <div>
                    <span class="text-muted">បង្ហាញទំព័រទី <strong>{{ page }}</strong> នៃ <strong>{{ total_pages }}</strong> (សរុប {{ total_count }} ជួរ)</span>
                </div>
                <nav>
                    <ul class="pagination mb-0">
                        <li class="page-item {% if page <= 1 %}disabled{% endif %}">
                            <a class="page-link" href="{{ url_for('view_logs', group=selected_group, page=page-1, admin='true' if is_admin else None) }}">❮ មុន</a>
                        </li>
                        <li class="page-item active">
                            <span class="page-link">{{ page }}</span>
                        </li>
                        <li class="page-item {% if page >= total_pages %}disabled{% endif %}">
                            <a class="page-link" href="{{ url_for('view_logs', group=selected_group, page=page+1, admin='true' if is_admin else None) }}">បន្ទាប់ ❯</a>
                        </li>
                    </ul>
                </nav>
            </div>

        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function scrollTableContainer(offset) {
            const container = document.getElementById('table-scroll-container');
            if (container) {
                container.scrollBy({
                    top: offset,
                    behavior: 'smooth'
                });
            }
        }
    </script>
</body>
</html>
"""

# ----------------------------------------------------
# ៣. Route បង្ហាញ Dashboard (/logs)
# ----------------------------------------------------
@app.route("/")
def home():
    return redirect(url_for("view_logs"))  # ឬ return "Bot is running OK!"
    
@app.route("/logs")
def view_logs():
    try:
        selected_group = request.args.get("group", "ALL")
        page = request.args.get("page", 1, type=int)
        is_admin = request.args.get("admin") == "true"  # ពិនិត្យមើលសិទ្ធិ Admin
        per_page = 100

        # ទាញយកបញ្ជី Group
        groups_res = supabase.table("chat_logs").select("group_title").execute()
        unique_groups = sorted(list(set([item["group_title"] for item in groups_res.data if item.get("group_title")])))

        # គណនា Pagination
        count_query = supabase.table("chat_logs").select("id", count="exact")
        if selected_group != "ALL":
            count_query = count_query.eq("group_title", selected_group)
        count_res = count_query.execute()
        total_count = count_res.count or 0
        total_pages = max(1, math.ceil(total_count / per_page))

        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages

        start = (page - 1) * per_page
        end = start + per_page - 1

        query = supabase.table("chat_logs").select("*")
        if selected_group != "ALL":
            query = query.eq("group_title", selected_group)

        res = query.order("created_at", desc=True).range(start, end).execute()
        logs = res.data or []

        return render_template_string(
            HTML_TEMPLATE,
            logs=logs,
            groups=unique_groups,
            selected_group=selected_group,
            page=page,
            total_pages=total_pages,
            total_count=total_count,
            is_admin=is_admin
        )
    except Exception as e:
        return f"Error loading logs: {e}", 500

# ----------------------------------------------------
# ៤. Route លុបទិន្នន័យ (/delete-old-logs)
# ----------------------------------------------------
@app.route("/delete-old-logs", methods=["POST"])
def delete_old_logs():
    try:
        is_admin_req = request.form.get("is_admin_req") == "true"
        target_group = request.form.get("target_group", "ALL")
        days_threshold = int(request.form.get("days_threshold", 7))

        # ប្រសិនបើមិនមែន Admin ទេ មិនអនុញ្ញាតឱ្យលុបឡើយ
        if not is_admin_req:
            flash("❌ អ្នកគ្មានសិទ្ធិក្នុងការលុបទិន្នន័យឡើយ!", "danger")
            return redirect(url_for("view_logs", group=target_group))

        cutoff_date = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_threshold)).isoformat()

        # Query រកមើល Logs ដែលត្រូវលុប
        query_select = supabase.table("chat_logs").select("*").lt("created_at", cutoff_date)
        if target_group != "ALL":
            query_select = query_select.eq("group_title", target_group)

        old_logs_res = query_select.execute()
        old_logs = old_logs_res.data or []
        deleted_rows_count = len(old_logs)

        # ស្រង់យកឈ្មោះ File រូបភាព
        files_to_delete = []
        for log in old_logs:
            msg = log.get("message_text", "")
            if "chat_images" in msg:
                filename = msg.split("/")[-1].split("?")[0].strip()
                if filename:
                    files_to_delete.append(filename)

        # លុប File រូបភាពចេញពី Storage
        deleted_images_count = len(files_to_delete)
        if files_to_delete:
            supabase.storage.from_("chat_images").remove(files_to_delete)

        # លុប Row ចេញពី Database
        if old_logs:
            query_delete = supabase.table("chat_logs").delete().lt("created_at", cutoff_date)
            if target_group != "ALL":
                query_delete = query_delete.eq("group_title", target_group)
            query_delete.execute()

            msg = f"✅ បានលុប Chat Logs ចំនួន {deleted_rows_count} ជួរដេក (ចាស់ជាង {days_threshold} ថ្ងៃ)"
            if deleted_images_count > 0:
                msg += f" និងរូបភាពចំនួន {deleted_images_count} រូបចេញពី Storage ដោយជោគជ័យ!"
            flash(msg, "success")
        else:
            flash(f"ℹ️ មិនមាន Chat Logs ណាដែលចាស់ជាង {days_threshold} ថ្ងៃ ត្រូវលុបឡើយ។", "info")

        return redirect(url_for("view_logs", group=target_group, admin="true"))
    except Exception as e:
        print(f"❌ Error during delete: {e}")
        flash(f"❌ មានបញ្ហាក្នុងការលុបទិន្នន័យ៖ {e}", "danger")
        return redirect(url_for("view_logs", group=target_group, admin="true"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

import os
import asyncio
from flask import Flask
from threading import Thread
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# 1. បង្កើត Flask App សម្រាប់ Render Health Check
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# 2. ហៅ Flask ឱ្យរ៉ាន់ក្នុង Background
flask_thread = Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()

# 3. ទាញយក Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# 4. Main Function សម្រាប់ Telegram Bot
async def main():
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN is missing!")
        return

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # បន្ថែម Handlers របស់អ្នកនៅទីនេះ (ឧទាហរណ៍)
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is starting...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # រក្សាឱ្យ Bot រ៉ាន់រហូត
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
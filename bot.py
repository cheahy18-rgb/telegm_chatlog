import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import Application, ChatMemberHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

BOT_TOKEN = "8833632355:AAFonpB8kasWNzgOd2adfls8jBAXBEQ3VJM"
ADMIN_CHAT_ID = 67024201  # ជំនួសដោយ Admin Chat ID ពិតប្រាកដ

async def log_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    if old_status in ["left", "kicked"] and new_status in ["member", "administrator"]:
        user = result.new_chat_member.user
        chat = update.effective_chat
        
        user_id = user.id
        full_name = user.full_name
        username = f"@{user.username}" if user.username else "គ្មាន Username"
        join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # បន្ថែមប៊ូតុង Mute តាមរយៈពេលវេលា
        keyboard = [
            [
                InlineKeyboardButton("🚫 Kick", callback_data=f"kick|{chat.id}|{user_id}"),
                InlineKeyboardButton("⛔ Ban", callback_data=f"ban|{chat.id}|{user_id}")
            ],
            [
                InlineKeyboardButton("🔇 Mute 1 ម៉ោង", callback_data=f"mute1h|{chat.id}|{user_id}"),
                InlineKeyboardButton("🔇 Mute 24 ម៉ោង", callback_data=f"mute24h|{chat.id}|{user_id}")
            ],
            [
                InlineKeyboardButton("✅ Unban / Unmute", callback_data=f"unban|{chat.id}|{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        admin_message = (
            f"📥 **សមាជិកថ្មីបានចូល Group!**\n\n"
            f"👤 **ឈ្មោះ:** {full_name}\n"
            f"🔗 **Username:** {username}\n"
            f"🆔 **User ID:** `{user_id}`\n"
            f"👥 **Group:** {chat.title}\n"
            f"⏰ **កាលបរិច្ឆេទ:** {join_date}"
        )

        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_message,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        except Exception as e:
            print(f"❌ មិនអាចផ្ញើសារទៅ Admin បានទេ: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, chat_id, user_id = query.data.split("|")
    chat_id = int(chat_id)
    user_id = int(user_id)

    # បង្កើត Permissions សម្រាប់ Mute (បិទការផ្ញើសារ)
    no_permissions = ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False
    )

    try:
        if action == "mute1h":
            # កំណត់ពេលផុតកំណត់ ១ ម៉ោង (ប្រើ UTC Time)
            until_time = datetime.now(timezone.utc) + timedelta(hours=1)
            
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=no_permissions,
                until_date=until_time
            )
            status_text = f"🔇 **លទ្ធផល:** បាន Mute អ្នកប្រើប្រាស់ (ID: `{user_id}`) រយៈពេល **១ ម៉ោង** (នឹងបើកវិញស្វ័យប្រវត្តិ)"

        elif action == "mute24h":
            # កំណត់ពេលផុតកំណត់ ២៤ ម៉ោង
            until_time = datetime.now(timezone.utc) + timedelta(hours=24)
            
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=no_permissions,
                until_date=until_time
            )
            status_text = f"🔇 **លទ្ធផល:** បាន Mute អ្នកប្រើប្រាស់ (ID: `{user_id}`) រយៈពេល **២៤ ម៉ោង** (នឹងបើកវិញស្វ័យប្រវត្តិ)"

        elif action == "kick":
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
            status_text = f"✅ **លទ្ធផល:** បាន Kick អ្នកប្រើប្រាស់ (ID: `{user_id}`) ចេញពី Group!"

        elif action == "ban":
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            status_text = f"⛔ **លទ្ធផល:** បាន Ban អ្នកប្រើប្រាស់ (ID: `{user_id}`) ជារៀងរហូត!"

        elif action == "unban":
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
            full_permissions = ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=full_permissions
            )
            status_text = f"✅ **លទ្ធផល:** បាន Unban / Unmute អ្នកប្រើប្រាស់ (ID: `{user_id}`) រួចរាល់!"

        # បច្ចុប្បន្នភាពសាររបស់ Admin
        await query.edit_message_text(
            text=f"{query.message.text}\n\n{status_text}",
            parse_mode="Markdown"
        )

    except Exception as e:
        await query.edit_message_text(
            text=f"{query.message.text}\n\n❌ **បរាជ័យ:** មិនអាចអនុវត្តបានទេ ({e})",
            parse_mode="Markdown"
        )

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(ChatMemberHandler(log_new_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot កំពុងដំណើរការ...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
import os
import secrets
import string
import asyncio
import re
import logging
import sys
from datetime import datetime, timedelta, time
import aiohttp
import requests
from pymongo import MongoClient
from flask import Flask, request, jsonify
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters, ContextTypes

# --- LOGGING ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO, stream=sys.stdout)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", 1234567))          
API_HASH = os.environ.get("API_HASH", "your_asli_api_hash") 
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
DB_URI = os.environ.get("DB_URI")  
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", -100xxxxxxxxx))   
START_IMAGE = os.environ.get("START_IMAGE", "https://graph.org/file/abc.jpg") 

LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID", -5408786306))     
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "@Cources99")  
OWNER_ID = int(os.environ.get("OWNER_ID", 7559016251))         

BOT_USERNAME = "free_file_store2026_bot" # Yahan apne bot ka username bina @ ke likhein

ADMIN_EARNING_API = "https://arolinks.com/api?api=f4617908b561110a219cd2b65bc255c2c2c6ff8a"

if not BOT_TOKEN or not DB_URI:
    print("💥 Critical Error: BOT_TOKEN ya DB_URI missing hai!", flush=True)
    sys.exit(1)

# --- DATABASE SETUP ---
try:
    mongo_client = MongoClient(DB_URI, maxPoolSize=5, minPoolSize=1, waitQueueTimeoutMS=2000, retryWrites=True)
    db = mongo_client["FileStoreDB"]
    users_col = db["users"]
    files_col = db["files"]
    print("✅ MongoDB Connected Successfully!", flush=True)
except Exception as e:
    print(f"💥 MongoDB Connection Error: {e}", flush=True)
    sys.exit(1)

user_states = {} 
session = requests.Session()

# --- INITIALIZE FLASK & PTB APPLICATION ---
app = Flask(__name__)
ptb_app = Application.builder().token(BOT_TOKEN).build()
ptb_app.bot._username = BOT_USERNAME
ptb_app.bot._bot_user = telegram.User(id=int(BOT_TOKEN.split(':')[0]), is_bot=True, first_name="FileStore", username=BOT_USERNAME)

# --- HELPER FUNCTIONS ---
def generate_code():
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(12))

def get_tonight_expiry():
    now = datetime.now()
    midnight = datetime.combine(now.date(), time(23, 59, 59))
    return midnight

def get_shortened_url(api_url, long_url):
    try:
        clean_api = api_url.strip()
        clean_api = re.split(r'[&?]url=', clean_api, flags=re.IGNORECASE)[0]
        clean_api = re.split(r'[&?]alias=', clean_api, flags=re.IGNORECASE)[0]
        
        connector = "&" if "?" in clean_api else "?"
        final_api_call = f"{clean_api}{connector}url={long_url}"
        
        response = session.get(final_api_call, timeout=6)
        if response.status_code == 200:
            try:
                res_json = response.json()
                short_url = None
                if "shortenedUrl" in res_json: short_url = res_json["shortenedUrl"]
                elif "shortlink" in res_json: short_url = res_json["shortlink"]
                elif "link" in res_json: short_url = res_json["link"]
                elif "url" in res_json: short_url = res_json["url"]
                elif "data" in res_json and isinstance(res_json["data"], dict):
                    short_url = res_json["data"].get("shortitem") or res_json["data"].get("shortenedUrl") or res_json["data"].get("shortlink")
                elif res_json.get("status") == "success":
                    short_url = res_json.get("shortenedUrl") or res_json.get("link") or res_json.get("url")
                    
                if short_url and (short_url.startswith("http://") or short_url.startswith("https://")):
                    return short_url
            except Exception:
                res_text = response.text.strip()
                if res_text.startswith("http://") or res_text.startswith("https://"):
                    return res_text
        return long_url
    except Exception:
        return long_url

async def show_main_menu(bot, chat_id, is_callback=False, message_id=None):
    text = "📂 **Main Menu**\n\nNiche diye gaye buttons ka use karein:"
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Your Links", callback_data="your_links"),
         InlineKeyboardButton("⚙️ Enter Your Shortener", callback_data="enter_shortener")],
        [InlineKeyboardButton("📁 Upload Single File", callback_data="upload_single"),
         InlineKeyboardButton("📦 Upload Bulk File", callback_data="upload_bulk")],
        [InlineKeyboardButton("❌ Delete Account", callback_data="delete_confirm")]
    ])
    if is_callback and message_id:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=buttons, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=buttons, parse_mode="Markdown")

# --- ADMIN SECURED HANDLER (/a) ---
async def verify_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ **Access Denied!**")
        return
    if not context.args:
        await update.message.reply_text("❌ Sahi format use karein: `/a target_user_id`")
        return
    try:
        target_id = int(context.args[0])
        users_col.update_one({"user_id": target_id}, {"$set": {"status": "verified"}})
        await update.message.reply_text(f"✅ User `{target_id}` verified!")
    except ValueError:
        return

# --- MESSAGE HANDLER (START & GLOBAL CAPTURE) ---
async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    bot = context.bot
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    text_message = update.message.text.strip() if update.message.text else ""

    # --- START COMMAND ROUTE ---
    if text_message.startswith("/start"):
        text_args = text_message.split()
        
        # 1. Verification Token Route
        if len(text_args) > 1 and text_args[1].startswith("verify_"):
            verify_token = text_args[1]
            owner_doc = users_col.find_one({"Users.verify_token": verify_token})
            if not owner_doc:
                await update.message.reply_text("❌ Verification Link Invalid hai.")
                return
            expiry_time = get_tonight_expiry()
            users_col.update_one(
                {"user_id": owner_doc["user_id"], "Users.verify_token": verify_token},
                {"$set": {"Users.$.status": "verified", "Users.$.expiretime": expiry_time}}
            )
            await update.message.reply_text("✅ **Aap successfully verify ho chuke hain!**\nDubara file link par click karein.")
            return

        # 2. Deep Linking File Route
        if len(text_args) > 1:
            code = text_args[1].strip()
            file_data = files_col.find_one({"code": code})
            if not file_data:
                await update.message.reply_text("❌ Link invalid hai.")
                return
                
            file_owner_id = file_data.get("owner_id")
            if file_owner_id and file_owner_id != user_id:
                owner_profile = users_col.find_one({"user_id": file_owner_id})
                if owner_profile:
                    users_array = owner_profile.get("Users", [])
                    target_user = next((u for u in users_array if u["userid"] == user_id), None)
                    now = datetime.now()
                    is_verified = False
                    
                    if target_user:
                        if target_user.get("status") == "verified":
                            exp_time = target_user.get("expiretime")
                            if exp_time and now < exp_time: is_verified = True
                            else:
                                users_col.update_one(
                                    {"user_id": file_owner_id, "Users.userid": user_id},
                                    {"$set": {"Users.$.status": "unverified", "Users.$.verify_token": None}}
                                )
                    else:
                        new_user_data = {"userid": user_id, "status": "unverified", "expiretime": None, "verify_token": None}
                        users_col.update_one({"user_id": file_owner_id}, {"$push": {"Users": new_user_data}})
                    
                    if not is_verified:
                        status_msg = await update.message.reply_text("⏳ **Verification check kiya jaa raha hai...**")
                        random_verify_str = f"verify_{generate_code().lower()}"
                        base_verify_url = f"https://t.me/{BOT_USERNAME}?start={random_verify_str}"
                        
                        users_col.update_one(
                            {"user_id": file_owner_id, "Users.userid": user_id},
                            {"$set": {"Users.$.verify_token": random_verify_str}}
                        )
                        
                        owner_apis = owner_profile.get("shorteners", [])
                        final_short_url = base_verify_url
                        if owner_apis:
                            for api in owner_apis:
                                final_short_url = get_shortened_url(api, final_short_url)
                        
                        if ADMIN_EARNING_API:
                            final_short_url = get_shortened_url(ADMIN_EARNING_API, final_short_url)
                        
                        await bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
                        if not (final_short_url.startswith("http://") or final_short_url.startswith("https://")):
                            final_short_url = base_verify_url
                            
                        verification_button = InlineKeyboardMarkup([[InlineKeyboardButton("🔐 Verify Account", url=final_short_url)]])
                        await update.message.reply_text("⚠️ **Access Denied!**\n\nFile download karne ke liye pehle verify karein.", reply_markup=verification_button)
                        return

            file_ids = file_data["file_ids"]
            next_part_code = file_data.get("next_part", None)
            await update.message.reply_text(f"📦 Files send ki jaa rahi hain... ({len(file_ids)})")
            
            for f_id in file_ids:
                try:
                    await bot.copy_message(chat_id=chat_id, from_chat_id=CHANNEL_ID, message_id=int(f_id))
                    await asyncio.sleep(0.5)
                except Exception: pass
                    
            if next_part_code:
                next_link = f"https://t.me/{BOT_USERNAME}?start={next_part_code}"
                markup = InlineKeyboardMarkup([[InlineKeyboardButton("⏩ Get Next Part", url=next_link)]])
                await update.message.reply_text("✨ Agla part lene ke liye niche click karein 👇", reply_markup=markup)
            else:
                await update.message.reply_text("✅ Sari files successfully deliver ho chuki hain!")
            return

        # Normal /start
        user = users_col.find_one({"user_id": user_id})
        if not user:
            text = "👋 Welcome! Is bot me files store karne ke liye account create karein."
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("📝 Create Account", callback_data="create_account")]])
            if START_IMAGE:
                try: await update.message.reply_photo(photo=START_IMAGE, caption=text, reply_markup=reply_markup)
                except Exception: await update.message.reply_text(text=text, reply_markup=reply_markup)
            else: await update.message.reply_text(text=text, reply_markup=reply_markup)
        else:
            await show_main_menu(bot, chat_id)
        return

    # --- END COMMAND ROUTE ---
    if text_message.startswith("/end"):
        user = users_col.find_one({"user_id": user_id})
        if user and user.get("status") == "unverified":
            username = f"@{update.effective_user.username}" if update.effective_user.username else "No Username"
            try: await bot.send_message(chat_id=LOG_GROUP_ID, text=f"key user ({username})\nUser id({user_id})")
            except Exception: pass
            await update.message.reply_text(f"❌ you need to connect admin for approval \nUsername ho {ADMIN_USERNAME}")
            return
        if user_id not in user_states: return
        state_type = user_states[user_id]["state"]

        if state_type == "waiting_api":
            all_apis = user_states[user_id]["apis"]
            if all_apis:
                users_col.update_one({"user_id": user_id}, {"$set": {"shorteners": all_apis}})
            del user_states[user_id]
            await update.message.reply_text("✅ Saved!")
            await show_main_menu(bot, chat_id)

        elif state_type == "waiting_bulk":
            all_files = user_states[user_id]["bulk_files"]
            if not all_files: return
            status_msg = await update.message.reply_text("⏳ Processing...")
            chunks = [all_files[i:i + 50] for i in range(0, len(all_files), 50)]
            previous_code = None
            first_share_link = ""
            for idx, chunk in enumerate(reversed(chunks)):
                code = generate_code()
                doc = {"code": code, "file_ids": chunk, "owner_id": user_id}
                if previous_code: doc["next_part"] = previous_code
                files_col.insert_one(doc)
                previous_code = code
                if idx == len(chunks) - 1: first_share_link = f"https://t.me/{BOT_USERNAME}?start={code}"
            users_col.update_one({"user_id": user_id}, {"$push": {"links": first_share_link}})
            del user_states[user_id]
            await bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            await update.message.reply_text(f"✅ **Link:** {first_share_link}", disable_web_page_preview=True)
            await show_main_menu(bot, chat_id)
        return

    # --- GENERAL TEXT INPUT CAPTURE ---
    if user_id in user_states and user_states[user_id]["state"] == "waiting_api" and text_message:
        if not (text_message.startswith("http://") or text_message.startswith("https://")): return
        user_states[user_id]["apis"].append(text_message)
        await update.message.reply_text(f"📥 API Added! Send next or `/end`.")
        return

    # --- MEDIA/FILE INPUT CAPTURE ---
    user = users_col.find_one({"user_id": user_id})
    if not user or user.get("status") == "unverified": return
    if user_id not in user_states: return
    state_data = user_states[user_id]
    
    try:
        forwarded = await update.message.forward(chat_id=CHANNEL_ID)
        file_id = forwarded.message_id
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return

    if state_data["state"] == "waiting_single":
        code = generate_code()
        share_link = f"https://t.me/{BOT_USERNAME}?start={code}"
        files_col.insert_one({"code": code, "file_ids": [file_id], "owner_id": user_id})
        users_col.update_one({"user_id": user_id}, {"$push": {"links": share_link}})
        del user_states[user_id]
        await update.message.reply_text(f"✅ **Link Ready:** {share_link}", disable_web_page_preview=True)
        await show_main_menu(bot, chat_id)
    elif state_data["state"] == "waiting_bulk":
        state_data["bulk_files"].append(file_id)
        await update.message.reply_text(f"📥 Received ({len(state_data['bulk_files'])}).")

# --- CALLBACK QUERY HANDLERS ---
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    bot = context.bot
    await query.answer()

    if data == "create_account":
        user = users_col.find_one({"user_id": user_id})
        if not user:
            users_col.insert_one({"user_id": user_id, "links": [], "shorteners": [], "status": "unverified", "Users": []})
        await show_main_menu(bot, chat_id)
    elif data == "your_links":
        user = users_col.find_one({"user_id": user_id})
        if not user or not user.get("links"):
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="⚠️ Koi link nahi hai.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="back_to_menu")]]))
            return
        links_text = "🔗 **Links:**\n\n"
        for idx, link in enumerate(user["links"], 1): links_text += f"{idx}. {link}\n"
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=links_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="back_to_menu")]]), disable_web_page_preview=True)
    elif data == "enter_shortener":
        user_states[user_id] = {"state": "waiting_api", "apis": []}
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="⚙️ Send APIs one by one, then send `/end` to save.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_to_menu")]]))
    elif data == "upload_single":
        user_states[user_id] = {"state": "waiting_single"}
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="📥 Send/Forward any file now.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_to_menu")]]))
    elif data == "upload_bulk":
        user_states[user_id] = {"state": "waiting_bulk", "bulk_files": []}
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="📦 Send files one by one, then send `/end`.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_to_menu")]]))
    elif data == "delete_confirm":
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="⚠️ Sure?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes", callback_data="delete_account_final")],[InlineKeyboardButton("❌ No", callback_data="back_to_menu")]]))
    elif data == "delete_account_final":
        users_col.delete_one({"user_id": user_id})
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="🗑️ Deleted.")
    elif data == "back_to_menu":
        if user_id in user_states: del user_states[user_id]
        await show_main_menu(bot, chat_id, is_callback=True, message_id=message_id)

# --- HANDLERS REGISTRATION ---
ptb_app.add_handler(CommandHandler("a", verify_user_handler))
ptb_app.add_handler(MessageHandler(filters.TEXT | filters.COMMAND | filters.ALL, handle_all_messages))
ptb_app.add_handler(CallbackQueryHandler(callback_handler))

# --- FLASK WEBHOOK SYSTEM ---
@app.route('/', methods=['GET'])
def index():
    return "Bot is active via Flask & python-telegram-bot Webhook!", 200

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    if request.method == "POST":
        try:
            update_json = request.get_json(force=True)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            ptb_app._initialized = True
            ptb_app.bot._initialized = True
            
            update = Update.de_json(update_json, ptb_app.bot)
            loop.run_until_complete(ptb_app.process_update(update))
            return jsonify({"status": "success"}), 200
        except Exception as e:
            print(f"💥 Webhook Process Error: {e}", flush=True)
            return jsonify({"status": "error"}), 200
    return "Method Not Allowed", 400

# Entrypoint for Vercel
app = app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7860)

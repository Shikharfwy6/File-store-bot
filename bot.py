import os
import secrets
import string
import asyncio
from datetime import datetime, timedelta, time
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIGURATION ---
API_ID = 33038589          # Apna API ID dalein
API_HASH = "3a0926df33e0ada07f5f9ccb6ce8c1a3" # Apna API Hash dalein
BOT_TOKEN = "8819160503:AAGQ8f23z3EuXyDPRRJ8vohw1fW1WtQNXQc" # Apna Bot Token dalein
DB_URI = "mongodb+srv://Shikhar:Shikharclasstw@telegram.pnl5wrr.mongodb.net/?appName=Telegram"  # Apna MongoDB URI dalein
CHANNEL_ID = -1003700429012   # Apna DB/Log Channel ID dalein
BOT_USERNAME = "free_file_store2026_bot_bot" # Bot ka username (bina @ ke)
START_IMAGE = "https://i.postimg.cc/jdcrNdQq/images-2026-06-13T195118-621.jpg" # /start par jo image dikhani hai

LOG_GROUP_ID = -5408786306     
ADMIN_USERNAME = "@Cources99"  
OWNER_ID = 7559016251         

# --- INITIALIZATION ---
bot = Client("FileStoreBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_client = AsyncIOMotorClient(DB_URI)
db = db_client["FileStoreDB"]
users_col = db["users"]
files_col = db["files"]

user_states = {} 
BOT_USERNAME = "" 

# --- HELPER FUNCTIONS ---
def generate_code():
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(12))

def get_tonight_expiry():
    now = datetime.now()
    midnight = datetime.combine(now.date(), time(23, 59, 59))
    return midnight

async def get_shortened_url(api_url, long_url):
    """Fully Dynamic Shortener Handler for AroLinks, VPLinks, InstantShortener etc."""
    try:
        clean_api = api_url.strip()
        
        # Format standard check: Kuch owners direct full API query string de dete hain
        # Agar link me pehle se '?api=' ya '&url=' nahi hai to hum use standard append karenge
        if "url=" not in clean_api:
            connector = "&" if "?" in clean_api else "?"
            final_api_call = f"{clean_api}{connector}url={long_url}"
        else:
            # Agar owner ne query di hui hai to default string replace ya append setup
            final_api_call = f"{clean_api}{long_url}" if clean_api.endswith("=") else f"{clean_api}&url={long_url}"
            
        async with aiohttp.ClientSession() as session:
            async with session.get(final_api_call, timeout=15) as response:
                if response.status == 200:
                    try:
                        # 1. Try JSON Parsing
                        res_json = await response.json()
                        short_url = None
                        
                        # Har tarah ke shorteners ke alag-alag JSON response keys ka system
                        if "shortenedUrl" in res_json:
                            short_url = res_json["shortenedUrl"]
                        elif "shortlink" in res_json:
                            short_url = res_json["shortlink"]
                        elif "link" in res_json:
                            short_url = res_json["link"]
                        elif "url" in res_json:
                            short_url = res_json["url"]
                        elif "data" in res_json and isinstance(res_json["data"], dict):
                            short_url = res_json["data"].get("shortitem") or res_json["data"].get("shortenedUrl") or res_json["data"].get("shortlink")
                        elif res_json.get("status") == "success":
                            short_url = res_json.get("shortenedUrl") or res_json.get("link") or res_json.get("url")
                            
                        if short_url and (short_url.startswith("http://") or short_url.startswith("https://")):
                            return short_url
                            
                    except Exception:
                        # 2. Try Plain Text Parsing (Kuch shorteners JSON nahi, direct url response dete hain)
                        res_text = await response.text()
                        res_text = res_text.strip()
                        if res_text.startswith("http://") or res_text.startswith("https://"):
                            return res_text

        return long_url
    except Exception as e:
        print(f"Shortener API Error: {e}")
        return long_url

async def show_main_menu(client, message, user_id, is_callback=False):
    text = "📂 **Main Menu**\n\nNiche diye gaye buttons ka use karein:"
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Your Links", callback_data="your_links"),
         InlineKeyboardButton("⚙️ Enter Your Shortener", callback_data="enter_shortener")],
        [InlineKeyboardButton("📁 Upload Single File", callback_data="upload_single"),
         InlineKeyboardButton("📦 Upload Bulk File", callback_data="upload_bulk")],
        [InlineKeyboardButton("❌ Delete Account", callback_data="delete_confirm")]
    ])
    if is_callback:
        await message.edit_text(text, reply_markup=buttons)
    else:
        await message.reply_text(text, reply_markup=buttons)

# --- COMMAND HANDLERS ---

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    text_args = message.text.split()
    
    # 1. Verification Handler Link (?start=verify_XXXX)
    if len(text_args) > 1 and text_args[1].startswith("verify_"):
        verify_token = text_args[1]
        owner_doc = await users_col.find_one({"Users.verify_token": verify_token})
        
        if not owner_doc:
            await message.reply_text("❌ Verification Link Invalid hai ya expire ho chuka hai.")
            return
            
        expiry_time = get_tonight_expiry()
        await users_col.update_one(
            {"user_id": owner_doc["user_id"], "Users.verify_token": verify_token},
            {"$set": {
                "Users.$.status": "verified",
                "Users.$.expiretime": expiry_time
            }}
        )
        await message.reply_text("✅ **Aap successfully verify ho chuke hain!**\nAb aap owner ke link se file access kar sakte hain. Dubara file link par click karein.")
        return

    # 2. File / Deep Linking Link Handling
    if len(text_args) > 1:
        code = text_args[1].strip()
        
        file_data = await files_col.find_one({"code": code})
        if not file_data:
            await message.reply_text("❌ Link invalid hai ya file delete ho chuki hai.")
            return
            
        file_owner_id = file_data.get("owner_id")
        
        if file_owner_id and file_owner_id != user_id:
            owner_profile = await users_col.find_one({"user_id": file_owner_id})
            
            if owner_profile:
                users_array = owner_profile.get("Users", [])
                target_user = next((u for u in users_array if u["userid"] == user_id), None)
                
                now = datetime.now()
                is_verified = False
                
                if target_user:
                    if target_user.get("status") == "verified":
                        exp_time = target_user.get("expiretime")
                        if exp_time and now < exp_time:
                            is_verified = True
                        else:
                            await users_col.update_one(
                                {"user_id": file_owner_id, "Users.userid": user_id},
                                {"$set": {"Users.$.status": "unverified", "Users.$.verify_token": None}}
                            )
                else:
                    new_user_data = {
                        "userid": user_id,
                        "status": "unverified",
                        "expiretime": None,
                        "verify_token": None
                    }
                    await users_col.update_one(
                        {"user_id": file_owner_id},
                        {"$push": {"Users": new_user_data}}
                    )
                
                if not is_verified:
                    status_msg = await message.reply_text("⏳ **Aapka verification check kiya jaa raha hai...**\nShortener link ready ho raha hai, kripya thoda intezar karein.")
                    
                    random_verify_str = f"verify_{generate_code().lower()}"
                    base_verify_url = f"https://t.me/{BOT_USERNAME}?start={random_verify_str}"
                    
                    await users_col.update_one(
                        {"user_id": file_owner_id, "Users.userid": user_id},
                        {"$set": {"Users.$.verify_token": random_verify_str}}
                    )
                    
                    owner_apis = owner_profile.get("shorteners", [])
                    final_short_url = base_verify_url
                    
                    if owner_apis:
                        # Chain Loop Execute
                        for api in owner_apis:
                            final_short_url = await get_shortened_url(api, final_short_url)
                    
                    await status_msg.delete()
                    
                    if not (final_short_url.startswith("http://") or final_short_url.startswith("https://")):
                        final_short_url = base_verify_url
                        
                    verification_button = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔐 Verify Account", url=final_short_url)]
                    ])
                    
                    await message.reply_text(
                        "⚠️ **Access Denied!**\n\nFile download karne ke liye aapko pehle Owner ke links se verify karna hoga. Yeh verification aaj raat 12 baje tak valid rahega.",
                        reply_markup=verification_button
                    )
                    return

        # File Delivery Section
        file_ids = file_data["file_ids"]
        next_part_code = file_data.get("next_part", None)
        
        await message.reply_text(f"📦 Aapki files send ki jaa rahi hain... (Is Part Me: {len(file_ids)})")
        
        for f_id in file_ids:
            try:
                await client.copy_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=int(f_id))
                await asyncio.sleep(0.6)
            except Exception as e:
                print(f"Error forwarding file: {e}")
                
        if next_part_code:
            next_link = f"https://t.me/{BOT_USERNAME}?start={next_part_code}"
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("⏩ Get Next Part Files", url=next_link)]])
            await message.reply_text("✨ Is part ki files complete ho gayi hain. Agla part lene ke liye niche click karein 👇", reply_markup=markup)
        else:
            await message.reply_text("✅ Sari files successfully deliver ho chuki hain!")
        return

    # Normal /start
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        text = "👋 Welcome! Is bot me files store karne ke liye aapko account create karna hoga."
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("📝 Create Account", callback_data="create_account")]])
        if START_IMAGE:
            try: await message.reply_photo(photo=START_IMAGE, caption=text, reply_markup=reply_markup)
            except Exception: await message.reply_text(text=text, reply_markup=reply_markup)
        else:
            await message.reply_text(text=text, reply_markup=reply_markup)
    else:
        await show_main_menu(client, message, user_id)


# --- SECURED ADMIN VERIFY COMMAND (/a userid) ---
@bot.on_message(filters.command("a") & filters.private)
async def verify_user_handler(client, message):
    sender_id = message.from_user.id
    if sender_id != OWNER_ID:
        await message.reply_text("❌ **Access Denied!**")
        return
        
    text_args = message.text.split()
    if len(text_args) < 2:
        await message.reply_text("❌ Sahi format use karein: `/a target_user_id`")
        return
        
    try: target_id = int(text_args[1])
    except ValueError: return
        
    user = await users_col.find_one({"user_id": target_id})
    if not user: return
        
    await users_col.update_one({"user_id": target_id}, {"$set": {"status": "verified"}})
    await message.reply_text(f"✅ User `{target_id}` ko admin status verified kar diya gaya hai!")


# --- CALLBACK QUERY HANDLERS ---
@bot.on_callback_query()
async def callback_handler(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    message = callback_query.message
    await callback_query.answer()

    if data == "create_account":
        user = await users_col.find_one({"user_id": user_id})
        if not user:
            await users_col.insert_one({"user_id": user_id, "links": [], "shorteners": [], "status": "unverified", "Users": []})
            await message.reply_text("🎉 Account successfully ban gaya!")
        await show_main_menu(client, message, user_id, is_callback=False)

    elif data == "your_links":
        user = await users_col.find_one({"user_id": user_id})
        if not user or not user.get("links") or len(user["links"]) == 0:
            back_button = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]])
            await message.edit_text("⚠️ Aapne abhi tak koi link nahi banaya.", reply_markup=back_button)
            return
        
        links_text = "🔗 **Aapke Saved Links:**\n\n"
        for idx, link in enumerate(user["links"], 1):
            links_text += f"{idx}. {link}\n"
        
        back_button = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]])
        await message.edit_text(links_text, reply_markup=back_button, disable_web_page_preview=True)

    elif data == "enter_shortener":
        user_states[user_id] = {"state": "waiting_api", "apis": []}
        await message.edit_text(
            "⚙️ **Shortener API Input Mode:**\n\nApne shorteners ke API link ek-ek karke send karein.\n\n"
            "Format Example:\n`https://arolinks.com/api?api=YOUR_TOKEN_HERE`\n\n"
            "Jab saare API send kar dein, tab save karne ke liye `/end` command bhein.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_to_menu")]])
        )

    elif data == "upload_single":
        user_states[user_id] = {"state": "waiting_single"}
        await message.edit_text(
            "📥 **Single File Mode:**\nAb koi bhi file forward/upload karein. Link turant ban jayega.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_to_menu")]])
        )

    elif data == "upload_bulk":
        user_states[user_id] = {"state": "waiting_bulk", "bulk_files": []}
        await message.edit_text(
            "📦 **Bulk File Mode:**\nSari files ek-ek karke bhejein. Jab sab upload ho jayein, tab `/end` command bhejein.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_to_menu")]])
        )

    elif data == "delete_confirm":
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Haan, Delete Karo", callback_data="delete_account_final")],
            [InlineKeyboardButton("❌ Nahi, Cancel", callback_data="back_to_menu")]
        ])
        await message.edit_text("⚠️ **Kya aap sach me apna account aur data delete karna chahte hain?**", reply_markup=buttons)

    elif data == "delete_account_final":
        await users_col.delete_one({"user_id": user_id})
        if user_id in user_states: del user_states[user_id]
        await message.edit_text("🗑️ Aapka account delete ho chuka hai. Dobara judne ke liye `/start` karein.")

    elif data == "back_to_menu":
        if user_id in user_states: del user_states[user_id]
        await show_main_menu(client, message, user_id, is_callback=True)


# --- TEXT & FILE HANDLERS / /end HANDLER ---
@bot.on_message(filters.private & filters.command("end"))
async def end_command_handler(client, message):
    user_id = message.from_user.id
    user = await users_col.find_one({"user_id": user_id})
    
    if user and user.get("status") == "unverified":
        username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
        log_text = f"key user ({username})\nUser id({user_id})\nNa file upload/api upload karan key kosis key"
        try: await client.send_message(chat_id=LOG_GROUP_ID, text=log_text)
        except Exception: pass
        
        await message.reply_text(f"❌ you need to connect admin for approval \nUsername ho {ADMIN_USERNAME}")
        if user_id in user_states: del user_states[user_id]
        return

    if user_id not in user_states:
        await message.reply_text("❌ Aap kisi active mode me nahi hain.")
        return
        
    state_type = user_states[user_id]["state"]

    if state_type == "waiting_api":
        all_apis = user_states[user_id]["apis"]
        if not all_apis:
            await message.reply_text("⚠️ Aapne koi bhi API link send nahi kiya.")
            del user_states[user_id]
            await show_main_menu(client, message, user_id)
            return
            
        status_msg = await message.reply_text("⏳ Saare APIs ko save kiya jaa raha hai...")
        await users_col.update_one({"user_id": user_id}, {"$set": {"shorteners": all_apis}})
            
        count = len(all_apis)
        del user_states[user_id]
        await status_msg.delete()
        await message.reply_text(f"✅ Successfully aapke saare **{count} API links** save ho chuke hain!")
        await show_main_menu(client, message, user_id)

    elif state_type == "waiting_bulk":
        all_files = user_states[user_id]["bulk_files"]
        if not all_files:
            await message.reply_text("⚠️ Aapne koi file upload nahi ki.")
            return
            
        status_msg = await message.reply_text("⏳ Processing aur split links generate kiye jaa rhe hain...")
        chunks = [all_files[i:i + 50] for i in range(0, len(all_files), 50)]
        previous_code = None
        first_share_link = ""

        for idx, chunk in enumerate(reversed(chunks)):
            code = generate_code()
            doc = {"code": code, "file_ids": chunk, "owner_id": user_id}
            if previous_code:
                doc["next_part"] = previous_code
            
            await files_col.insert_one(doc)
            previous_code = code
            
            if idx == len(chunks) - 1:
                first_share_link = f"https://t.me/{BOT_USERNAME}?start={code}"

        await users_col.update_one({"user_id": user_id}, {"$push": {"links": first_share_link}})
        del user_states[user_id]
        
        await status_msg.delete()
        await message.reply_text(f"✅ **Bulk Link Generated!**\n\n🔗 **Main Link:** {first_share_link}", disable_web_page_preview=True)
        await show_main_menu(client, message, user_id)


# --- GENERAL TEXT CAPTURE HANDLER ---
@bot.on_message(filters.private & filters.text & ~filters.command(["start", "end", "a"]))
async def text_handler(client, message):
    user_id = message.from_user.id
    if user_id not in user_states: return
        
    if user_states[user_id]["state"] == "waiting_api":
        api_text = message.text.strip()
        if not (api_text.startswith("http://") or api_text.startswith("https://")):
            await message.reply_text("❌ Galat format!")
            return
            
        user_states[user_id]["apis"].append(api_text)
        current_count = len(user_states[user_id]["apis"])
        await message.reply_text(f"📥 **API Link Received ({current_count})!**\nAgla link bhejein ya `/end` karein.")


# --- FILE RECEIVER HANDLER ---
@bot.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo | filters.animation))
async def file_receiver_handler(client, message):
    user_id = message.from_user.id
    user = await users_col.find_one({"user_id": user_id})
    if not user: return

    if user.get("status") == "unverified":
        username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
        log_text = f"key user ({username})\nUser id({user_id})\nNa file upload karan key kosis key"
        try: await client.send_message(chat_id=LOG_GROUP_ID, text=log_text)
        except Exception: pass
        await message.reply_text(f"❌ you need to connect admin for approval \nUsername ho {ADMIN_USERNAME}")
        return

    if user_id not in user_states: return
    state_data = user_states[user_id]
        
    try:
        forwarded = await message.forward(CHANNEL_ID)
        file_id = forwarded.id
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")
        return

    if state_data["state"] == "waiting_single":
        code = generate_code()
        share_link = f"https://t.me/{BOT_USERNAME}?start={code}"
        
        await files_col.insert_one({"code": code, "file_ids": [file_id], "owner_id": user_id})
        await users_col.update_one({"user_id": user_id}, {"$push": {"links": share_link}})
        del user_states[user_id]
        await message.reply_text(f"✅ **Single File Link Ready:**\n\n🔗 {share_link}", disable_web_page_preview=True)
        await show_main_menu(client, message, user_id)

    elif state_data["state"] == "waiting_bulk":
        state_data["bulk_files"].append(file_id)
        current_count = len(state_data["bulk_files"])
        if current_count % 50 == 0:
            await message.reply_text(f"📥 **{current_count} Files Receive!**\nKhatam karne ke liye `/end` dabayein.")
        else:
            await message.reply_text(f"📥 File received ({current_count}).")


# --- MAIN ENGINE ---
async def main():
    global BOT_USERNAME
    print("Bot starting...")
    await bot.start()
    bot_info = await bot.get_me()
    BOT_USERNAME = bot_info.username
    print(f"✨ Bot is live on @{BOT_USERNAME}!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

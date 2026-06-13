import os
import secrets
import string
import asyncio
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
# --- INITIALIZATION ---
bot = Client("FileStoreBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_client = AsyncIOMotorClient(DB_URI)
db = db_client["FileStoreDB"]
users_col = db["users"]
files_col = db["files"]

user_states = {} 
BOT_USERNAME = "" 

# --- FIXED HELPER FUNCTION (No Underscores, Safe Alphanumeric) ---
def generate_code():
    # Yeh hamesha 12 characters ka pure letters aur numbers ka code banayega, koi '_' nahi aayega
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(12))

async def show_main_menu(client, message, user_id, is_callback=False):
    text = "📂 **Main Menu**\n\nNiche diye gaye buttons ka use karein:"
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Your Links", callback_data="your_links")],
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
    
    # Deep Linking Parsing (Link handle karna)
    if len(text_args) > 1:
        raw_code = text_args[1]
        code = raw_code.strip() # Kisi bhi extra space ko hatane ke liye
        
        # Database me code check karna
        file_data = await files_col.find_one({"code": code})
        
        if not file_data:
            await message.reply_text("❌ Link invalid hai ya file delete ho chuki hai.")
            return
            
        file_ids = file_data["file_ids"]
        next_part_code = file_data.get("next_part", None)
        
        await message.reply_text(f"📦 Aapki files send ki jaa rahi hain... (Is Part Me: {len(file_ids)})")
        
        for f_id in file_ids:
            try:
                await client.copy_message(
                    chat_id=user_id,
                    from_chat_id=CHANNEL_ID,
                    message_id=int(f_id)
                )
                await asyncio.sleep(0.6) # Anti-flood delay to prevent crash
            except Exception as e:
                print(f"Error forwarding file: {e}")
                
        # Bulk File Split Integration
        if next_part_code:
            next_link = f"https://t.me/{BOT_USERNAME}?start={next_part_code}"
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("⏩ Get Next Part Files", url=next_link)]])
            await message.reply_text("✨ Is part ki 50 files complete ho gayi hain. Agla part lene ke liye niche click karein 👇", reply_markup=markup)
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
            await users_col.insert_one({"user_id": user_id, "links": []})
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


# --- TEXT & FILE HANDLERS ---

@bot.on_message(filters.private & filters.command("end"))
async def bulk_end_handler(client, message):
    user_id = message.from_user.id
    
    if user_id not in user_states or user_states[user_id]["state"] != "waiting_bulk":
        await message.reply_text("❌ Aap bulk upload mode me nahi hain.")
        return
        
    all_files = user_states[user_id]["bulk_files"]
    if not all_files:
        await message.reply_text("⚠️ Aapne koi file upload nahi ki.")
        return
        
    status_msg = await message.reply_text("⏳ Processing aur split links generate kiye jaa rhe hain...")
    
    # 50-50 files chunk logic
    chunks = [all_files[i:i + 50] for i in range(0, len(all_files), 50)]
    previous_code = None
    first_share_link = ""

    for idx, chunk in enumerate(reversed(chunks)):
        code = generate_code()
        doc = {"code": code, "file_ids": chunk}
        if previous_code:
            doc["next_part"] = previous_code
        
        await files_col.insert_one(doc)
        previous_code = code
        
        if idx == len(chunks) - 1:
            first_share_link = f"https://t.me/{BOT_USERNAME}?start={code}"

    await users_col.update_one({"user_id": user_id}, {"$push": {"links": first_share_link}})
    del user_states[user_id]
    
    await status_msg.delete()
    await message.reply_text(
        f"✅ **Bulk Link Generated! (Total Parts: {len(chunks)})**\n\n🔗 **Main Link:** {first_share_link}\n\n*Note: Is link se user ko pehle 50 files milengi, fir wahan 'Next Part' ka button automatic aa jayega.*",
        disable_web_page_preview=True
    )
    await show_main_menu(client, message, user_id)

@bot.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo | filters.animation))
async def file_receiver_handler(client, message):
    user_id = message.from_user.id
    
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        await message.reply_text("⚠️ Pehle `/start` karke account create karein.")
        return

    if user_id not in user_states:
        await message.reply_text("⚠️ Pehle menu se selection karein.")
        return
        
    state_data = user_states[user_id]
    
    try:
        forwarded = await message.forward(CHANNEL_ID)
        file_id = forwarded.id
    except Exception as e:
        await message.reply_text(f"❌ File channel me nahi gayi. Error: {e}")
        return

    if state_data["state"] == "waiting_single":
        code = generate_code()
        share_link = f"https://t.me/{BOT_USERNAME}?start={code}"
        await files_col.insert_one({"code": code, "file_ids": [file_id]})
        await users_col.update_one({"user_id": user_id}, {"$push": {"links": share_link}})
        del user_states[user_id]
        await message.reply_text(f"✅ **Single File Link Ready:**\n\n🔗 {share_link}", disable_web_page_preview=True)
        await show_main_menu(client, message, user_id)

    elif state_data["state"] == "waiting_bulk":
        state_data["bulk_files"].append(file_id)
        current_count = len(state_data["bulk_files"])
        
        if current_count % 50 == 0:
            await message.reply_text(f"📥 **{current_count} Files Receive Ho Chuki Hain!**\nYeh Part 50 complete ho gaya hai, aap bli files bhejna jaari rakh sakte hain. Khatam karne ke liye `/end` dabayein.")
        else:
            await message.reply_text(f"📥 File received ({current_count}). Aur bhejein ya `/end` karein.")


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

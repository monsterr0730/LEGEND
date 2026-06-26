#!/usr/bin/env python3
"""
📢 MEGA BROADCAST BOT - Send Anything to All Users!
🔄 Supports: Photo, Video, Document, Sticker, Voice, Audio, Animation, Text, Links
"""

import telebot
import os
import time
import json
import threading
import re
from datetime import datetime
from pymongo import MongoClient
from concurrent.futures import ThreadPoolExecutor
from telebot import types

# =============== THREAD POOL ===============
executor = ThreadPoolExecutor(max_workers=10)

# =============== MONGODB ===============
MONGO_URI = "mongodb+srv://MONSTER:xs2ntc4U9r11PkbZ@cluster0.07q3hqb.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client["broadcast_bot"]

users_collection = db["users"]
broadcast_history = db["broadcast_history"]
settings_collection = db["settings"]

print("✅ MongoDB Connected!")

# =============== CONFIG ===============
BOT_TOKEN = "8638318202:AAHuhX2nvJkOkPLpMrjvU_cVEDp6XE5tCbI"
OWNER_IDS = [7192516189]

bot = telebot.TeleBot(BOT_TOKEN, num_threads=20)

# =============== OWNER NAME SETTINGS ===============
def get_owner_name():
    """Get owner display name from settings"""
    settings = settings_collection.find_one({"_id": "owner_settings"})
    if settings and settings.get("display_name"):
        return settings["display_name"]
    return None

def set_owner_name(name):
    """Set owner display name"""
    settings_collection.update_one(
        {"_id": "owner_settings"},
        {"$set": {"display_name": name}},
        upsert=True
    )

def remove_owner_name():
    """Remove owner display name"""
    settings_collection.update_one(
        {"_id": "owner_settings"},
        {"$unset": {"display_name": ""}}
    )

# =============== HELPER FUNCTIONS ===============
def is_owner(user_id):
    return int(user_id) in OWNER_IDS

def bold(text):
    """Make text bold"""
    return f"*{text}*"

def styled_reply(text, status="info"):
    """Styled reply with bold text"""
    icon = "✅" if status == "success" else "❌" if status == "error" else "⚠️" if status == "warning" else "📌"
    return f"{icon} {bold(text)}"

def get_all_users():
    """Get all users from database"""
    users = []
    for user in users_collection.find({}, {"_id": 1}):
        users.append(user["_id"])
    return users

def get_user_count():
    return users_collection.count_documents({})

def save_user(user_id, username=None, first_name=None):
    """Save or update user in database"""
    update_data = {
        "last_active": datetime.now().isoformat()
    }
    if username:
        update_data["username"] = username
    if first_name:
        update_data["first_name"] = first_name
    
    users_collection.update_one(
        {"_id": str(user_id)},
        {"$set": update_data},
        upsert=True
    )

# =============== BROADCAST FUNCTION ===============
def broadcast_to_all(message_obj, caption=None, is_forward=False):
    """Send any type of message to all users"""
    users = get_all_users()
    total = len(users)
    success = 0
    fail = 0
    blocked = 0
    
    for user_id in users:
        try:
            if is_forward:
                bot.forward_message(user_id, message_obj.chat.id, message_obj.message_id)
            else:
                if message_obj.photo:
                    bot.send_photo(user_id, message_obj.photo[-1].file_id, caption=caption)
                elif message_obj.video:
                    bot.send_video(user_id, message_obj.video.file_id, caption=caption)
                elif message_obj.document:
                    bot.send_document(user_id, message_obj.document.file_id, caption=caption)
                elif message_obj.sticker:
                    bot.send_sticker(user_id, message_obj.sticker.file_id)
                elif message_obj.voice:
                    bot.send_voice(user_id, message_obj.voice.file_id, caption=caption)
                elif message_obj.audio:
                    bot.send_audio(user_id, message_obj.audio.file_id, caption=caption)
                elif message_obj.animation:
                    bot.send_animation(user_id, message_obj.animation.file_id, caption=caption)
                elif message_obj.video_note:
                    bot.send_video_note(user_id, message_obj.video_note.file_id)
                elif message_obj.text:
                    bot.send_message(user_id, caption if caption else message_obj.text)
                else:
                    bot.copy_message(user_id, message_obj.chat.id, message_obj.message_id)
            
            success += 1
            
        except Exception as e:
            if "blocked" in str(e).lower():
                blocked += 1
                users_collection.delete_one({"_id": user_id})
            else:
                fail += 1
        
        time.sleep(0.02)
    
    return {"success": success, "fail": fail, "blocked": blocked, "total": total}

def save_broadcast_history(broadcast_type, success, fail, blocked, total, sender_id):
    broadcast_history.insert_one({
        "type": broadcast_type,
        "success": success,
        "fail": fail,
        "blocked": blocked,
        "total": total,
        "sender_id": sender_id,
        "timestamp": datetime.now().isoformat(),
        "time_readable": datetime.now().strftime('%d %b %Y, %I:%M:%S %p')
    })

def get_broadcast_history(limit=10):
    return list(broadcast_history.find().sort("timestamp", -1).limit(limit))

# =============== BROADCAST COMMAND ===============
@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(m):
    uid = str(m.chat.id)
    
    if not is_owner(uid):
        bot.reply_to(m, styled_reply("Owner only!", "error"), parse_mode="Markdown")
        return
    
    if not m.reply_to_message:
        bot.reply_to(m, 
            styled_reply("📢 BROADCAST INSTRUCTIONS", "info") + "\n\n"
            "*1️⃣* Reply to any message (photo, video, file, link, etc.)\n"
            "*2️⃣* Type /broadcast\n\n"
            "*✅ Works with:*\n"
            "📸 Photo\n"
            "🎥 Video\n"
            "📁 Document (APK, PDF, etc.)\n"
            "🔗 Links\n"
            "🎨 Sticker\n"
            "🎵 Voice/Audio\n"
            "🎬 Animation (GIF)\n"
            "📝 Text Message\n"
            "🔄 Forwarded Message\n\n"
            "*Example:* Reply to a photo and type /broadcast",
            parse_mode="Markdown"
        )
        return
    
    msg = bot.reply_to(m, styled_reply("⏳ Broadcasting... Please wait.", "info"), parse_mode="Markdown")
    
    def handle_broadcast():
        try:
            total_users = get_user_count()
            caption = m.text.replace("/broadcast", "").strip() if m.text else None
            is_forward = m.reply_to_message.forward_date is not None
            
            result = broadcast_to_all(m.reply_to_message, caption, is_forward)
            
            save_broadcast_history(
                "mixed" if not caption else "text_with_media",
                result["success"],
                result["fail"],
                result["blocked"],
                result["total"],
                uid
            )
            
            owner_name = get_owner_name()
            owner_text = f"\n👑 *Owner:* {owner_name}" if owner_name else ""
            
            bot.edit_message_text(
                styled_reply("✅ BROADCAST COMPLETE!", "success") + "\n\n"
                f"*📊 Total Users:* {result['total']}\n"
                f"*✅ Successfully Sent:* {result['success']}\n"
                f"*❌ Failed:* {result['fail']}\n"
                f"*🚫 Blocked & Removed:* {result['blocked']}\n"
                f"*📅 Time:* {datetime.now().strftime('%d %b %Y, %I:%M:%S %p')}\n\n"
                f"*📊 Broadcast History:* /bhistory"
                f"{owner_text}",
                msg.chat.id, msg.message_id,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            bot.edit_message_text(
                styled_reply("❌ BROADCAST FAILED!", "error") + "\n\n"
                f"*Error:* {str(e)[:100]}",
                msg.chat.id, msg.message_id,
                parse_mode="Markdown"
            )
    
    executor.submit(handle_broadcast)

# =============== BROADCAST HISTORY COMMAND ===============
@bot.message_handler(commands=['bhistory'])
def broadcast_history_cmd(m):
    uid = str(m.chat.id)
    
    if not is_owner(uid):
        bot.reply_to(m, styled_reply("Owner only!", "error"), parse_mode="Markdown")
        return
    
    history = get_broadcast_history(10)
    owner_name = get_owner_name()
    owner_text = f"\n👑 *Owner:* {owner_name}" if owner_name else ""
    
    if not history:
        bot.reply_to(m, 
            styled_reply("📋 NO BROADCAST HISTORY", "info") + "\n\n"
            "*No broadcasts sent yet.*"
            f"{owner_text}",
            parse_mode="Markdown"
        )
        return
    
    msg = styled_reply("📊 BROADCAST HISTORY", "info") + "\n\n"
    for i, h in enumerate(history, 1):
        msg += f"*{i}.* 📅 {h['time_readable']}\n"
        msg += f"   *✅ Success:* {h['success']}\n"
        msg += f"   *❌ Failed:* {h['fail']}\n"
        msg += f"   *🚫 Blocked:* {h['blocked']}\n"
        msg += f"   *📊 Total:* {h['total']}\n\n"
    
    msg += owner_text
    
    bot.reply_to(m, msg, parse_mode="Markdown")

# =============== USER STATS COMMAND ===============
@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    uid = str(m.chat.id)
    
    if not is_owner(uid):
        bot.reply_to(m, styled_reply("Owner only!", "error"), parse_mode="Markdown")
        return
    
    total_users = get_user_count()
    history = get_broadcast_history(1)
    owner_name = get_owner_name()
    owner_text = f"\n👑 *Owner:* {owner_name}" if owner_name else ""
    
    msg = styled_reply("📊 BOT STATISTICS", "info") + "\n\n"
    msg += f"*👥 Total Users:* {total_users}\n"
    
    if history:
        last = history[0]
        msg += f"\n*📢 Last Broadcast:*\n"
        msg += f"   *✅ Sent:* {last['success']}\n"
        msg += f"   *❌ Failed:* {last['fail']}\n"
        msg += f"   *📅 Time:* {last['time_readable']}"
    
    msg += owner_text
    
    bot.reply_to(m, msg, parse_mode="Markdown")

# =============== REMOVE BLOCKED USERS ===============
@bot.message_handler(commands=['clean'])
def clean_cmd(m):
    uid = str(m.chat.id)
    
    if not is_owner(uid):
        bot.reply_to(m, styled_reply("Owner only!", "error"), parse_mode="Markdown")
        return
    
    msg = bot.reply_to(m, styled_reply("⏳ Checking for blocked users...", "info"), parse_mode="Markdown")
    
    def handle_clean():
        all_users = list(users_collection.find({}, {"_id": 1}))
        total = len(all_users)
        removed = 0
        
        for user in all_users:
            try:
                bot.send_chat_action(user["_id"], 'typing')
            except:
                users_collection.delete_one({"_id": user["_id"]})
                removed += 1
            time.sleep(0.02)
        
        owner_name = get_owner_name()
        owner_text = f"\n👑 *Owner:* {owner_name}" if owner_name else ""
        
        bot.edit_message_text(
            styled_reply("✅ CLEANUP COMPLETE!", "success") + "\n\n"
            f"*📊 Total Users Checked:* {total}\n"
            f"*🗑️ Blocked Users Removed:* {removed}\n"
            f"*👥 Remaining Users:* {total - removed}\n"
            f"*📅 Time:* {datetime.now().strftime('%d %b %Y, %I:%M:%S %p')}"
            f"{owner_text}",
            msg.chat.id, msg.message_id,
            parse_mode="Markdown"
        )
    
    executor.submit(handle_clean)

# =============== ADD NAME COMMAND ===============
@bot.message_handler(commands=['addname'])
def add_name_cmd(m):
    uid = str(m.chat.id)
    
    if not is_owner(uid):
        bot.reply_to(m, styled_reply("Owner only!", "error"), parse_mode="Markdown")
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) != 2:
        bot.reply_to(m, 
            styled_reply("📝 ADD OWNER NAME", "info") + "\n\n"
            "*Usage:* `/addname @Username`\n"
            "*Example:* `/addname @XsilentFoundr`\n\n"
            "*This name will appear in all replies.*",
            parse_mode="Markdown"
        )
        return
    
    name = args[1].strip()
    set_owner_name(name)
    
    bot.reply_to(m, 
        styled_reply("✅ OWNER NAME ADDED!", "success") + "\n\n"
        f"*👑 Display Name:* {name}\n\n"
        f"*This name will now appear in all bot replies.*",
        parse_mode="Markdown"
    )

# =============== REMOVE NAME COMMAND ===============
@bot.message_handler(commands=['removename'])
def remove_name_cmd(m):
    uid = str(m.chat.id)
    
    if not is_owner(uid):
        bot.reply_to(m, styled_reply("Owner only!", "error"), parse_mode="Markdown")
        return
    
    remove_owner_name()
    
    bot.reply_to(m, 
        styled_reply("✅ OWNER NAME REMOVED!", "success") + "\n\n"
        "*Owner name will no longer appear in replies.*",
        parse_mode="Markdown"
    )

# =============== EXPORT USERS ===============
@bot.message_handler(commands=['export'])
def export_cmd(m):
    uid = str(m.chat.id)
    
    if not is_owner(uid):
        bot.reply_to(m, styled_reply("Owner only!", "error"), parse_mode="Markdown")
        return
    
    msg = bot.reply_to(m, styled_reply("⏳ Exporting users...", "info"), parse_mode="Markdown")
    
    def handle_export():
        try:
            all_users = list(users_collection.find({}))
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"users_export_{timestamp}.json"
            
            with open(file_name, "w") as f:
                json.dump(all_users, f, indent=4, default=str)
            
            owner_name = get_owner_name()
            owner_text = f"\n👑 *Owner:* {owner_name}" if owner_name else ""
            
            with open(file_name, "rb") as f:
                bot.send_document(
                    m.chat.id,
                    f,
                    caption=styled_reply("📥 USERS EXPORT", "success") + "\n\n"
                            f"*👥 Total Users:* {len(all_users)}\n"
                            f"*📅 Time:* {datetime.now().strftime('%d %b %Y, %I:%M:%S %p')}"
                            f"{owner_text}",
                    parse_mode="Markdown"
                )
            
            os.remove(file_name)
            
            bot.edit_message_text(
                styled_reply("✅ EXPORT COMPLETE!", "success") + "\n\n"
                f"*👥 Users Exported:* {len(all_users)}",
                msg.chat.id, msg.message_id,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            bot.edit_message_text(
                styled_reply("❌ EXPORT FAILED!", "error") + "\n\n"
                f"*Error:* {str(e)[:100]}",
                msg.chat.id, msg.message_id,
                parse_mode="Markdown"
            )
    
    executor.submit(handle_export)

# =============== SEND TO SPECIFIC USER ===============
@bot.message_handler(commands=['sendto'])
def sendto_cmd(m):
    uid = str(m.chat.id)
    
    if not is_owner(uid):
        bot.reply_to(m, styled_reply("Owner only!", "error"), parse_mode="Markdown")
        return
    
    args = m.text.split()
    if len(args) != 2:
        bot.reply_to(m, 
            styled_reply("📤 SEND TO USER", "info") + "\n\n"
            "*Usage:* `/sendto USER_ID`\n"
            "*Then reply to a message to send it to that user.*\n\n"
            "*Example:* `/sendto 7192516189`\n"
            "*Then reply to a photo and type /sendto 7192516189*",
            parse_mode="Markdown"
        )
        return
    
    target_user = args[1]
    
    if not m.reply_to_message:
        bot.reply_to(m, styled_reply("⚠️ Reply to a message to send!", "warning"), parse_mode="Markdown")
        return
    
    def handle_sendto():
        try:
            bot.copy_message(target_user, m.chat.id, m.reply_to_message.message_id)
            owner_name = get_owner_name()
            owner_text = f"\n👑 *Owner:* {owner_name}" if owner_name else ""
            
            bot.reply_to(m, 
                styled_reply("✅ MESSAGE SENT!", "success") + "\n\n"
                f"*👤 User:* {target_user}"
                f"{owner_text}",
                parse_mode="Markdown"
            )
        except Exception as e:
            bot.reply_to(m, 
                styled_reply("❌ FAILED!", "error") + "\n\n"
                f"*Error:* {str(e)[:100]}",
                parse_mode="Markdown"
            )
    
    executor.submit(handle_sendto)

# =============== DELETE ALL USERS ===============
@bot.message_handler(commands=['deleteallusers'])
def delete_all_users(m):
    uid = str(m.chat.id)
    
    if not is_owner(uid):
        bot.reply_to(m, styled_reply("Owner only!", "error"), parse_mode="Markdown")
        return
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(
        types.InlineKeyboardButton("⚠️ CONFIRM DELETE ALL", callback_data="delete_users_confirm"),
        types.InlineKeyboardButton("❌ CANCEL", callback_data="delete_users_cancel")
    )
    
    owner_name = get_owner_name()
    owner_text = f"\n👑 *Owner:* {owner_name}" if owner_name else ""
    
    bot.reply_to(m, 
        styled_reply("⚠️ WARNING!", "warning") + "\n\n"
        f"*This will DELETE ALL USERS from the database!*\n"
        f"*Total Users:* {get_user_count()}\n\n"
        f"*Are you sure?*"
        f"{owner_text}",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_users_"))
def delete_users_callback(call):
    uid = str(call.from_user.id)
    
    if not is_owner(uid):
        bot.answer_callback_query(call.id, "Owner only!")
        return
    
    if call.data == "delete_users_cancel":
        bot.edit_message_text(
            styled_reply("❌ DELETE CANCELLED", "error"),
            call.message.chat.id, call.message.message_id,
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id)
        return
    
    if call.data == "delete_users_confirm":
        bot.edit_message_text(
            styled_reply("⏳ Deleting all users...", "info"),
            call.message.chat.id, call.message.message_id,
            parse_mode="Markdown"
        )
        
        def handle_delete():
            count = users_collection.count_documents({})
            users_collection.delete_many({})
            
            owner_name = get_owner_name()
            owner_text = f"\n👑 *Owner:* {owner_name}" if owner_name else ""
            
            bot.edit_message_text(
                styled_reply("✅ ALL USERS DELETED!", "success") + "\n\n"
                f"*🗑️ Deleted:* {count} users"
                f"{owner_text}",
                call.message.chat.id, call.message.message_id,
                parse_mode="Markdown"
            )
        
        executor.submit(handle_delete)
        bot.answer_callback_query(call.id)

# =============== START COMMAND ===============
@bot.message_handler(commands=['start'])
def start(m):
    uid = str(m.chat.id)
    username = m.from_user.username
    first_name = m.from_user.first_name
    
    save_user(uid, username, first_name)
    owner_name = get_owner_name()
    owner_text = f"\n👑 *Owner:* {owner_name}" if owner_name else ""
    
    if not is_owner(uid):
        bot.reply_to(m, 
            styled_reply("👋 WELCOME!", "success") + "\n\n"
            f"*This is a Broadcast Bot.*\n\n"
            f"*Only the owner can send broadcasts.*\n"
            f"*If you're the owner, use /broadcast*"
            f"{owner_text}",
            parse_mode="Markdown"
        )
    else:
        bot.reply_to(m, 
            styled_reply("👑 OWNER PANEL", "info") + "\n\n"
            "*📢* /broadcast *- Send to all users (reply to any message)*\n"
            "*📊* /stats *- Bot statistics*\n"
            "*📋* /bhistory *- Broadcast history*\n"
            "*🧹* /clean *- Remove blocked users*\n"
            "*📥* /export *- Export all users*\n"
            "*📤* /sendto *- Send to specific user*\n"
            "*🗑️* /deleteallusers *- Delete all users*\n"
            "*📝* /addname *- Set owner name*\n"
            "*📝* /removename *- Remove owner name*"
            f"{owner_text}",
            parse_mode="Markdown"
        )

# =============== AUTO SAVE USER ON ANY MESSAGE ===============
@bot.message_handler(func=lambda m: True)
def auto_save_user(m):
    """Auto save user when they send any message"""
    uid = str(m.chat.id)
    username = m.from_user.username
    first_name = m.from_user.first_name
    
    # Save or update user
    save_user(uid, username, first_name)
    
    # Check if message has link
    if m.text and re.search(r'https?://\S+', m.text):
        # Just silently save, no need to reply
        pass

# =============== START BOT ===============
if __name__ == "__main__":
    print("=" * 50)
    print("📢 MEGA BROADCAST BOT STARTED!")
    print(f"👑 Owner: {OWNER_IDS[0]}")
    print(f"👥 Total Users: {get_user_count()}")
    print("📅 " + datetime.now().strftime('%d %b %Y, %I:%M:%S %p'))
    print("=" * 50)
    print("✅ Supported: Photo, Video, Document, Sticker, Voice, Audio, Animation, Text, Links")
    print("✅ Auto Saves: Username, First Name, Last Active")
    print("=" * 50)
    
    bot.infinity_polling()

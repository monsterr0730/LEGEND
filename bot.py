#!/usr/bin/env python3
"""
📢 BROADCAST BOT - Clean Version
👑 Owner commands hidden from users
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
client = MongoClient(MONGO_URI, 
                     serverSelectionTimeoutMS=5000,
                     connectTimeoutMS=5000,
                     socketTimeoutMS=5000)
try:
    client.admin.command('ping')
    print("✅ MongoDB Connected!")
except Exception as e:
    print(f"❌ MongoDB Connection Failed: {e}")
    exit(1)

db = client["broadcast_bot"]

users_collection = db["users"]
broadcast_history = db["broadcast_history"]
settings_collection = db["settings"]

print("✅ Collections Ready!")

# =============== CONFIG ===============
BOT_TOKEN = "8638318202:AAHuhX2nvJkOkPLpMrjvU_cVEDp6XE5tCbI"
OWNER_IDS = [7192516189]

bot = telebot.TeleBot(BOT_TOKEN, num_threads=20)

# =============== BACKUP FOLDER ===============
BACKUP_FOLDER = "backups"
if not os.path.exists(BACKUP_FOLDER):
    os.makedirs(BACKUP_FOLDER)

# =============== OWNER NAME SETTINGS ===============
def get_owner_name():
    settings = settings_collection.find_one({"_id": "owner_settings"})
    if settings and settings.get("display_name"):
        return settings["display_name"]
    return None

def set_owner_name(name):
    settings_collection.update_one(
        {"_id": "owner_settings"},
        {"$set": {"display_name": name}},
        upsert=True
    )

def remove_owner_name():
    settings_collection.update_one(
        {"_id": "owner_settings"},
        {"$unset": {"display_name": ""}}
    )

# =============== HELPER FUNCTIONS ===============
def is_owner(user_id):
    return int(user_id) in OWNER_IDS

def bold(text):
    return f"*{text}*"

def styled_reply(text, status="info"):
    icon = "✅" if status == "success" else "❌" if status == "error" else "⚠️" if status == "warning" else "📌"
    return f"{icon} {bold(text)}"

def get_all_users():
    users = []
    for user in users_collection.find({}, {"_id": 1}):
        users.append(user["_id"])
    return users

def get_user_count():
    return users_collection.count_documents({})

def save_user(user_id, username=None, first_name=None):
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

# =============== BACKUP FUNCTIONS ===============
def create_full_backup():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_FOLDER, f"full_backup_{timestamp}.json")
    
    all_users = list(users_collection.find({}))
    all_history = list(broadcast_history.find({}))
    all_settings = list(settings_collection.find({}))
    
    # Convert ObjectId to string
    for user in all_users:
        user["_id"] = str(user["_id"])
    for h in all_history:
        h["_id"] = str(h["_id"])
    for s in all_settings:
        s["_id"] = str(s["_id"])
    
    data = {
        "backup_info": {
            "version": "2.0",
            "created_at": datetime.now().isoformat(),
            "created_at_readable": datetime.now().strftime('%d %b %Y, %I:%M:%S %p'),
            "bot_name": bot.get_me().username,
            "total_users": len(all_users),
            "total_broadcasts": len(all_history)
        },
        "users": all_users,
        "broadcast_history": all_history,
        "settings": all_settings
    }
    
    with open(backup_file, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False, default=str)
    
    return backup_file, data

def restore_from_backup(data):
    users_added = 0
    history_added = 0
    
    for user in data.get("users", []):
        user_id = user.get("_id")
        if user_id:
            try:
                user_copy = user.copy()
                user_copy.pop("_id", None)
                users_collection.update_one(
                    {"_id": user_id},
                    {"$set": user_copy},
                    upsert=True
                )
                users_added += 1
            except:
                pass
    
    for history in data.get("broadcast_history", []):
        history_id = history.get("_id")
        if history_id:
            try:
                history_copy = history.copy()
                history_copy.pop("_id", None)
                broadcast_history.update_one(
                    {"_id": history_id},
                    {"$set": history_copy},
                    upsert=True
                )
                history_added += 1
            except:
                pass
    
    return {"users": users_added, "history": history_added}

# =============== ONLY OWNER COMMANDS (Hidden from users) ===============

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(m):
    uid = str(m.chat.id)
    if not is_owner(uid):
        return
    
    if not m.reply_to_message:
        bot.reply_to(m, 
            "📢 *Reply to any message to broadcast!*\n\n"
            "*Works with:* Photo, Video, Document, Sticker, Voice, Audio, Text, Links",
            parse_mode="Markdown"
        )
        return
    
    msg = bot.reply_to(m, "⏳ *Broadcasting...*", parse_mode="Markdown")
    
    def handle_broadcast():
        try:
            total_users = get_user_count()
            caption = m.text.replace("/broadcast", "").strip() if m.text else None
            is_forward = m.reply_to_message.forward_date is not None
            
            success = 0
            fail = 0
            blocked = 0
            
            for user_id in get_all_users():
                try:
                    if is_forward:
                        bot.forward_message(user_id, m.chat.id, m.reply_to_message.message_id)
                    else:
                        msg_obj = m.reply_to_message
                        if msg_obj.photo:
                            bot.send_photo(user_id, msg_obj.photo[-1].file_id, caption=caption)
                        elif msg_obj.video:
                            bot.send_video(user_id, msg_obj.video.file_id, caption=caption)
                        elif msg_obj.document:
                            bot.send_document(user_id, msg_obj.document.file_id, caption=caption)
                        elif msg_obj.sticker:
                            bot.send_sticker(user_id, msg_obj.sticker.file_id)
                        elif msg_obj.voice:
                            bot.send_voice(user_id, msg_obj.voice.file_id, caption=caption)
                        elif msg_obj.audio:
                            bot.send_audio(user_id, msg_obj.audio.file_id, caption=caption)
                        elif msg_obj.animation:
                            bot.send_animation(user_id, msg_obj.animation.file_id, caption=caption)
                        elif msg_obj.text:
                            bot.send_message(user_id, caption if caption else msg_obj.text)
                        else:
                            bot.copy_message(user_id, m.chat.id, msg_obj.message_id)
                    success += 1
                except:
                    if "blocked" in str(e).lower():
                        blocked += 1
                        users_collection.delete_one({"_id": user_id})
                    else:
                        fail += 1
                time.sleep(0.02)
            
            broadcast_history.insert_one({
                "success": success,
                "fail": fail,
                "blocked": blocked,
                "total": total_users,
                "time_readable": datetime.now().strftime('%d %b %Y, %I:%M:%S %p')
            })
            
            owner_name = get_owner_name()
            owner_text = f"\n👑 *Owner:* {owner_name}" if owner_name else ""
            
            bot.edit_message_text(
                f"✅ *BROADCAST COMPLETE!*\n\n"
                f"*📊 Total:* {total_users}\n"
                f"*✅ Sent:* {success}\n"
                f"*❌ Failed:* {fail}\n"
                f"*🚫 Blocked:* {blocked}"
                f"{owner_text}",
                msg.chat.id, msg.message_id,
                parse_mode="Markdown"
            )
        except Exception as e:
            bot.edit_message_text(
                f"❌ *Failed:* {str(e)[:100]}",
                msg.chat.id, msg.message_id,
                parse_mode="Markdown"
            )
    
    executor.submit(handle_broadcast)

@bot.message_handler(commands=['backup'])
def backup_cmd(m):
    uid = str(m.chat.id)
    if not is_owner(uid):
        return
    
    msg = bot.reply_to(m, "⏳ *Creating backup...*", parse_mode="Markdown")
    
    def handle_backup():
        try:
            backup_file, data = create_full_backup()
            
            with open(backup_file, "rb") as f:
                bot.send_document(
                    m.chat.id, f,
                    caption=f"📦 *Backup Complete!*\n\n"
                            f"*👥 Users:* {data['backup_info']['total_users']}\n"
                            f"*📅 Time:* {data['backup_info']['created_at_readable']}",
                    parse_mode="Markdown"
                )
            
            bot.edit_message_text(
                f"✅ *Backup created!*",
                msg.chat.id, msg.message_id,
                parse_mode="Markdown"
            )
        except Exception as e:
            bot.edit_message_text(
                f"❌ *Failed:* {str(e)[:100]}",
                msg.chat.id, msg.message_id,
                parse_mode="Markdown"
            )
    
    executor.submit(handle_backup)

@bot.message_handler(commands=['restore'])
def restore_cmd(m):
    uid = str(m.chat.id)
    if not is_owner(uid):
        return
    
    if not m.reply_to_message or not m.reply_to_message.document:
        bot.reply_to(m, "📥 *Reply to a backup JSON file with /restore*", parse_mode="Markdown")
        return
    
    msg = bot.reply_to(m, "⏳ *Restoring...*", parse_mode="Markdown")
    
    def handle_restore():
        try:
            file_info = bot.get_file(m.reply_to_message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            data = json.loads(downloaded_file.decode('utf-8'))
            
            result = restore_from_backup(data)
            
            bot.edit_message_text(
                f"✅ *Restore Complete!*\n\n"
                f"*👥 Users Added:* {result['users']}\n"
                f"*📢 Broadcasts:* {result['history']}",
                msg.chat.id, msg.message_id,
                parse_mode="Markdown"
            )
        except Exception as e:
            bot.edit_message_text(
                f"❌ *Failed:* {str(e)[:100]}",
                msg.chat.id, msg.message_id,
                parse_mode="Markdown"
            )
    
    executor.submit(handle_restore)

@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    uid = str(m.chat.id)
    if not is_owner(uid):
        return
    
    total_users = get_user_count()
    last_broadcast = broadcast_history.find_one(sort=[("time_readable", -1)])
    
    msg = f"📊 *Bot Statistics*\n\n"
    msg += f"*👥 Total Users:* {total_users}\n"
    
    if last_broadcast:
        msg += f"\n*📢 Last Broadcast:*\n"
        msg += f"   *✅ Sent:* {last_broadcast.get('success', 0)}\n"
        msg += f"   *❌ Failed:* {last_broadcast.get('fail', 0)}\n"
        msg += f"   *📅 Time:* {last_broadcast.get('time_readable', 'Unknown')}"
    
    bot.reply_to(m, msg, parse_mode="Markdown")

@bot.message_handler(commands=['clean'])
def clean_cmd(m):
    uid = str(m.chat.id)
    if not is_owner(uid):
        return
    
    msg = bot.reply_to(m, "⏳ *Checking blocked users...*", parse_mode="Markdown")
    
    def handle_clean():
        removed = 0
        for user in users_collection.find({}, {"_id": 1}):
            try:
                bot.send_chat_action(user["_id"], 'typing')
            except:
                users_collection.delete_one({"_id": user["_id"]})
                removed += 1
            time.sleep(0.02)
        
        bot.edit_message_text(
            f"✅ *Cleanup Complete!*\n\n*🗑️ Removed:* {removed} blocked users",
            msg.chat.id, msg.message_id,
            parse_mode="Markdown"
        )
    
    executor.submit(handle_clean)

@bot.message_handler(commands=['export'])
def export_cmd(m):
    uid = str(m.chat.id)
    if not is_owner(uid):
        return
    
    msg = bot.reply_to(m, "⏳ *Exporting users...*", parse_mode="Markdown")
    
    def handle_export():
        try:
            all_users = list(users_collection.find({}))
            file_name = f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            with open(file_name, "w") as f:
                json.dump(all_users, f, indent=4, default=str)
            
            with open(file_name, "rb") as f:
                bot.send_document(m.chat.id, f, caption=f"📥 *Users Export*\n\n*👥 Total:* {len(all_users)}")
            
            os.remove(file_name)
            bot.edit_message_text("✅ *Export Complete!*", msg.chat.id, msg.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ *Failed:* {str(e)[:100]}", msg.chat.id, msg.message_id)
    
    executor.submit(handle_export)

@bot.message_handler(commands=['sendto'])
def sendto_cmd(m):
    uid = str(m.chat.id)
    if not is_owner(uid):
        return
    
    args = m.text.split()
    if len(args) != 2 or not m.reply_to_message:
        bot.reply_to(m, "📤 *Usage:* `/sendto USER_ID` (reply to a message)", parse_mode="Markdown")
        return
    
    target = args[1]
    try:
        bot.copy_message(target, m.chat.id, m.reply_to_message.message_id)
        bot.reply_to(m, f"✅ *Sent to {target}*", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(m, f"❌ *Failed:* {str(e)[:100]}", parse_mode="Markdown")

@bot.message_handler(commands=['deleteallusers'])
def delete_all_users(m):
    uid = str(m.chat.id)
    if not is_owner(uid):
        return
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(
        types.InlineKeyboardButton("⚠️ CONFIRM", callback_data="delete_confirm"),
        types.InlineKeyboardButton("❌ CANCEL", callback_data="delete_cancel")
    )
    
    bot.reply_to(m, 
        f"⚠️ *Delete ALL {get_user_count()} users?*\n\n*This cannot be undone!*",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['addname'])
def add_name_cmd(m):
    uid = str(m.chat.id)
    if not is_owner(uid):
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) != 2:
        bot.reply_to(m, "📝 *Usage:* `/addname @Username`", parse_mode="Markdown")
        return
    
    set_owner_name(args[1].strip())
    bot.reply_to(m, f"✅ *Owner name set to:* {args[1]}", parse_mode="Markdown")

@bot.message_handler(commands=['removename'])
def remove_name_cmd(m):
    uid = str(m.chat.id)
    if not is_owner(uid):
        return
    
    remove_owner_name()
    bot.reply_to(m, "✅ *Owner name removed*", parse_mode="Markdown")

# =============== CALLBACKS ===============
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if call.data == "delete_confirm":
        count = users_collection.count_documents({})
        users_collection.delete_many({})
        bot.edit_message_text(f"✅ *Deleted {count} users*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    elif call.data == "delete_cancel":
        bot.edit_message_text("❌ *Cancelled*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

# =============== START COMMAND ===============
@bot.message_handler(commands=['start'])
def start(m):
    uid = str(m.chat.id)
    save_user(uid, m.from_user.username, m.from_user.first_name)
    
    owner_name = get_owner_name()
    owner_text = f"\n👑 *Owner:* {owner_name}" if owner_name else ""
    
    if is_owner(uid):
        bot.reply_to(m, 
            f"👑 *Owner Panel*\n\n"
            f"📢 /broadcast - Send to all\n"
            f"📦 /backup - Full backup\n"
            f"📥 /restore - Restore backup\n"
            f"📊 /stats - Bot stats\n"
            f"🧹 /clean - Remove blocked\n"
            f"📥 /export - Export users\n"
            f"📤 /sendto - Send to user\n"
            f"🗑️ /deleteallusers - Delete all\n"
            f"📝 /addname - Set owner name\n"
            f"📝 /removename - Remove owner name"
            f"{owner_text}",
            parse_mode="Markdown"
        )
    else:
        bot.reply_to(m, 
            f"👋 *Welcome to XSilent Support!*\n\n"
            f"*This is the official support bot.*\n"
            f"*For any queries, contact the owner.*"
            f"{owner_text}",
            parse_mode="Markdown"
        )

# =============== AUTO SAVE USER ON ANY MESSAGE ===============
@bot.message_handler(func=lambda m: True)
def auto_save(m):
    uid = str(m.chat.id)
    save_user(uid, m.from_user.username, m.from_user.first_name)

# =============== START BOT ===============
if __name__ == "__main__":
    print("=" * 50)
    print("📢 BROADCAST BOT STARTED!")
    print(f"👑 Owner: {OWNER_IDS[0]}")
    print(f"👥 Users: {get_user_count()}")
    print("=" * 50)
    bot.infinity_polling()

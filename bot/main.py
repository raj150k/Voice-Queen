import os
import io
import tempfile
import logging
import sqlite3
import subprocess
import requests
from datetime import datetime, timedelta
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

from config import *

# ====== লগিং ======
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====== ডাটাবেস ======
DB_PATH = "girlicbot.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP,
            total_conversions INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            selected_voice TEXT DEFAULT 'japanese_anime'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            voice_model TEXT,
            duration_sec REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            action TEXT,
            target_user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def is_admin(user_id):
    return user_id in ADMIN_IDS

def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not is_admin(user_id):
            await update.message.reply_text("⛔ শুধু এডমিনের জন্য!")
            return
        return await func(update, context)
    return wrapper

# ====== হেল্পার ফাংশন ======

async def check_channel_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """চ্যানেল জয়েন চেক"""
    if not FORCE_JOIN_CHANNEL:
        return True
    
    try:
        user_id = update.effective_user.id
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
        return False
    except:
        return False

async def send_join_request(update: Update):
    """জয়েন করতে বলবে"""
    keyboard = [
        [InlineKeyboardButton("📢 জয়েন চ্যানেল", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")],
        [InlineKeyboardButton("✅ জয়েন করেছি", callback_data="check_join")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "❌ আপনি এখনও চ্যানেল জয়েন করেননি!\n\n"
        "👇 নিচের বাটনে ক্লিক করে আগে চ্যানেল জয়েন করুন,\n"
        "তারপর '✅ জয়েন করেছি' বাটনে ক্লিক করুন।",
        reply_markup=reply_markup
    )

def save_user(user_id, username, first_name):
    """ইউজার ডাটাবেজে সেভ"""
    conn = get_db()
    conn.execute("""
        INSERT OR IGNORE INTO users (user_id, username, first_name)
        VALUES (?, ?, ?)
    """, (user_id, username, first_name))
    conn.commit()
    conn.close()

def update_user_usage(user_id):
    """ইউজারের ব্যবহার আপডেট"""
    conn = get_db()
    conn.execute("""
        UPDATE users SET last_used = ?, total_conversions = total_conversions + 1
        WHERE user_id = ?
    """, (datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()

def save_conversion(user_id, voice_model, duration):
    """কনভার্সন হিস্টোরি সেভ"""
    conn = get_db()
    conn.execute("""
        INSERT INTO conversions (user_id, voice_model, duration_sec)
        VALUES (?, ?, ?)
    """, (user_id, voice_model, duration))
    conn.commit()
    conn.close()

# ====== কমান্ড হ্যান্ডলার ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """হোম পেজ /start"""
    user = update.effective_user
    save_user(user.id, user.username, user.first_name)
    
    # চ্যানেল জয়েন চেক
    if FORCE_JOIN_CHANNEL:
        is_member = await check_channel_member(update, context)
        if not is_member:
            await send_join_request(update)
            return
    
    keyboard = [
        [InlineKeyboardButton("🎤 ভয়েস কনভার্ট", callback_data="menu_convert")],
        [InlineKeyboardButton("🎀 ভয়েস মডেল বাছাই", callback_data="menu_voices")],
        [InlineKeyboardButton("📊 আমার পরিসংখ্যান", callback_data="menu_stats")],
        [InlineKeyboardButton("❓ সাহায্য", callback_data="menu_help")],
        [InlineKeyboardButton("📢 চ্যানেল", url=f"https://t.me/{CHANNEL_USERNAME[1:]}" if CHANNEL_USERNAME else "https://t.me/your_channel")]
    ]
    
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("⚙️ এডমিন প্যানেল", callback_data="menu_admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"🌟 হ্যালো {user.first_name}! 🌟\n\n"
        "আমি ** Voice Queen - ভয়েস চেঞ্জার বট! 🎤\n\n"
        "✨ **আমি যা করতে পারি:**\n"
        "• তোমার ভয়েস ➡️ নারী কণ্ঠে রূপান্তর 🎀\n"
        "• একাধিক ভয়েস মডেল থেকে বাছাই 🎭\n"
        "• সম্পূর্ণ ফ্রি 💝\n\n"
        "👇 নিচের অপশন থেকে বেছে নাও:"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """হেল্প কমান্ড"""
    help_text = (
        "❓ ** Voice Queen সাহায্য** ❓\n\n"
        "🎤 **ভয়েস কনভার্ট করতে:**\n"
        "সরাসরি ভয়েস মেসেজ পাঠাও → আমি কনভার্ট করে দেব!\n\n"
        "🎭 **ভয়েস মডেল পরিবর্তন:**\n"
        "/voices — সব মডেল দেখো\n"
        "/setvoice [নাম] — মডেল সেট করো\n\n"
        "📋 **কমান্ডসমূহ:**\n"
        "/start — বট শুরু করো\n"
        "/help — এই মেসেজ\n"
        "/voices — ভয়েস মডেল লিস্ট\n"
        "/setvoice — ভয়েস পরিবর্তন\n"
        "/stats — তোমার পরিসংখ্যান\n"
        "/about — বট সম্পর্কে\n\n"
        "💡 **টিপস:**\n"
        "• ক্লিয়ার ভয়েস রেকর্ড করো\n"
        "• ৩০ সেকেন্ডের কম হলে ভালো\n"
        "• ব্যাকগ্রাউন্ড নয়েজ কম রাখো"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def voices_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ভয়েস মডেল লিস্ট"""
    text = "🎀 **উপলব্ধ ভয়েস মডেল:**\n\n"
    
    for key, model in VOICE_MODELS.items():
        selected = "✅" if key == DEFAULT_VOICE else "⬜"
        text += f"{selected} **/{key}** — {model['name']}\n"
        text += f"   └ {model['desc']}\n\n"
    
    text += "\nব্যবহার: `/setvoice [মডেল_নাম]`"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def set_voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ভয়েস মডেল সেট"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "⚠️ ব্যবহার: `/setvoice japanese_anime`\n\n"
            "মডেল লিস্ট দেখতে: /voices",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    voice_name = args[0].lower()
    
    if voice_name in VOICE_MODELS:
        conn = get_db()
        conn.execute("UPDATE users SET selected_voice = ? WHERE user_id = ?", 
                    (voice_name, user_id))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ ভয়েস মডেল সেট করা হয়েছে:\n"
            f"**{VOICE_MODELS[voice_name]['name']}** 🎀",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            f"❌ ভুল ভয়েস মডেল!\n\n"
            f"সঠিক মডেল দেখতে: /voices",
            parse_mode=ParseMode.MARKDOWN
        )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইউজার পরিসংখ্যান"""
    user_id = update.effective_user.id
    
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conversions = conn.execute(
        "SELECT COUNT(*) as cnt, SUM(duration_sec) as total_dur FROM conversions WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    
    if user:
        selected_voice = VOICE_MODELS.get(user["selected_voice"], {}).get("name", "Unknown")
        text = (
            "📊 **তোমার পরিসংখ্যান** 📊\n\n"
            f"👤 ইউজার: {user['first_name'] or 'Unknown'}\n"
            f"🆔 আইডি: `{user_id}`\n"
            f"🎀 বর্তমান ভয়েস: {selected_voice}\n"
            f"🔄 মোট কনভার্সন: {conversions['cnt'] or 0}\n"
            f"⏱ মোট সময়: {conversions['total_dur'] or 0:.1f} সেকেন্ড\n"
            f"📅 জয়েন: {user['joined_at'][:19]}\n"
            f"🕐 শেষ ব্যবহার: {user['last_used'][:19] if user['last_used'] else 'N/A'}\n"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("তোমার কোনো ডাটা নেই। /start দিয়ে শুরু করো!")

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """বট সম্পর্কে"""
    text = (
        "🎀 ** Voice Queen - Voice Changer** 🎀\n\n"
        "একটি শক্তিশালী AI ভয়েস চেঞ্জার বট\n"
        "যা তোমার ভয়েসকে নারী কণ্ঠে রূপান্তর করে!\n\n"
        "✨ **ফিচার:**\n"
        "• RVC AI ভয়েস কনভার্সন\n"
        "• একাধিক ভয়েস মডেল\n"
        "• সম্পূর্ণ ফ্রি 💝\n"
        "• ২৪/৭ সেবা\n\n"
        "👑 **এডমিন:** @raj169k\n"
        "📢 **চ্যানেল:** {}\n\n"
        "🔥 **পাওয়ার্ড বাই:** RVC + AI".format(
            CHANNEL_USERNAME if CHANNEL_USERNAME else "@your_channel"
        )
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ====== ভয়েস হ্যান্ডলার ======

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ভয়েস মেসেজ হ্যান্ডল করবে"""
    user = update.effective_user
    user_id = user.id
    
    # চ্যানেল জয়েন চেক
    if FORCE_JOIN_CHANNEL:
        is_member = await check_channel_member(update, context)
        if not is_member:
            await send_join_request(update)
            return
    
    # ব্যান চেক
    conn = get_db()
    banned = conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if banned and banned["is_banned"]:
        await update.message.reply_text("⛔ আপনাকে ব্ল্যাকলিস্ট করা হয়েছে!")
        conn.close()
        return
    
    # ইউজারের সিলেক্টেড ভয়েস
    user_data = conn.execute("SELECT selected_voice FROM users WHERE user_id = ?", (user_id,)).fetchone()
    selected_voice = user_data["selected_voice"] if user_data else DEFAULT_VOICE
    conn.close()
    
    voice = update.message.voice
    duration = voice.duration if voice.duration else 5
    
    # ভয়েস ডাউনলোড
    await update.message.reply_chat_action("record_voice")
    process_msg = await update.message.reply_text(
        "🎤 **ভয়েস প্রসেস করছি...** ⏳\n\n"
        f"🎀 মডেল: {VOICE_MODELS.get(selected_voice, {}).get('name', 'ডিফল্ট')}\n"
        f"⏱ সময়: {duration} সেকেন্ড",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        voice_file = await voice.get_file()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            await voice_file.download_to_drive(tmp.name)
            orig_path = tmp.name
        
        # OGG → WAV কনভার্ট
        wav_path = orig_path.replace(".ogg", ".wav")
        subprocess.run(
            ["ffmpeg", "-i", orig_path, "-ar", "44100", "-ac", "1", wav_path, "-y"],
            capture_output=True
        )
        os.unlink(orig_path)
        
        # RVC কনভার্ট
        output_path = wav_path.replace(".wav", "_converted.wav")
        
        if USE_EXTERNAL_API and ELEVENLABS_API_KEY:
            # ElevenLabs API ব্যবহার
            result = await convert_with_elevenlabs(wav_path, output_path)
        else:
            # লোকাল RVC ব্যবহার
            result = await convert_with_rvc(wav_path, output_path, selected_voice)
        
        if result:
            # ওগ ফরম্যাটে কনভার্ট
            ogg_path = output_path.replace("_converted.wav", "_final.ogg")
            subprocess.run(
                ["ffmpeg", "-i", output_path, "-c:a", "libopus", ogg_path, "-y"],
                capture_output=True
            )
            
            # ভয়েস পাঠাও
            with open(ogg_path, "rb") as f:
                await update.message.reply_voice(
                    voice=f,
                    caption=f"✅ **কনভার্টেড!** 🎀\n🎤 মডেল: {VOICE_MODELS.get(selected_voice, {}).get('name', 'Unknown')}",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            # ক্লিনআপ
            os.unlink(ogg_path)
            
            # ডাটাবেজ আপডেট
            update_user_usage(user_id)
            save_conversion(user_id, selected_voice, duration)
            
            await process_msg.delete()
        else:
            await process_msg.edit_text(
                "❌ **কনভার্ট করতে সমস্যা!**\n\n"
                "আবার চেষ্টা করুন বা /help দেখুন।",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # ক্লিনআপ
        for f in [wav_path, output_path]:
            if os.path.exists(f):
                os.unlink(f)
        
    except Exception as e:
        logger.error(f"Voice conversion error: {e}")
        await process_msg.edit_text(
            "❌ **এরর!** কিছু সমস্যা হয়েছে।\nআবার চেষ্টা করুন। 🎤",
            parse_mode=ParseMode.MARKDOWN
        )

async def convert_with_rvc(input_path, output_path, voice_model):
    """লোকাল RVC দিয়ে কনভার্ট"""
    try:
        cmd = [
            "python", f"{os.path.expanduser('~/Retrieval-based-Voice-Conversion-WebUI')}/infer.py",
            "--model", voice_model,
            "--f0method", "rmvpe",
            "--input", input_path,
            "--output", output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    except Exception as e:
        logger.error(f"RVC error: {e}")
        return False

async def convert_with_elevenlabs(input_path, output_path):
    """ElevenLabs API দিয়ে কনভার্ট"""
    try:
        with open(input_path, "rb") as f:
            audio_data = f.read()
        
        headers = {
            "Accept": "audio/mpeg",
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "audio/wav"
        }
        
        response = requests.post(
            f"https://api.elevenlabs.io/v1/voices/{VOICE_ID}",
            headers=headers,
            data=audio_data
        )
        
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return True
        return False
    except Exception as e:
        logger.error(f"ElevenLabs error: {e}")
        return False

# ====== কলব্যাক হ্যান্ডলার ======

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইনলাইন বাটন হ্যান্ডল"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "check_join":
        is_member = await check_channel_member(update, context)
        if is_member:
            await query.edit_message_text("✅ আপনি জয়েন করেছেন! এখন /start দিন।")
        else:
            await query.edit_message_text(
                "❌ আপনি এখনও জয়েন করেননি।\n"
                "উপরের চ্যানেল জয়েন করে আবার চেষ্টা করুন।"
            )
    
    elif data == "menu_convert":
        await query.edit_message_text(
            "🎤 **ভয়েস কনভার্ট** 🎤\n\n"
            "শুধু একটি ভয়েস মেসেজ পাঠাও!\n"
            "আমি নিজেই কনভার্ট করে দেব 🎀\n\n"
            "মডেল পরিবর্তন করতে /voices দেখো।",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "menu_voices":
        text = "🎀 **উপলব্ধ ভয়েস মডেল:**\n\n"
        for key, model in VOICE_MODELS.items():
            text += f"• **{model['name']}** `/setvoice {key}`\n"
            text += f"  └ {model['desc']}\n\n"
        
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif data == "menu_stats":
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        conversions = conn.execute(
            "SELECT COUNT(*) as cnt, SUM(duration_sec) as total_dur FROM conversions WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        conn.close()
        
        if user:
            text = (
                "📊 **তোমার পরিসংখ্যান**\n\n"
                f"👤 ইউজার: {user['first_name']}\n"
                f"🔄 কনভার্সন: {conversions['cnt'] or 0}\n"
                f"⏱ সময়: {conversions['total_dur'] or 0:.1f} সেকেন্ড\n"
            )
        else:
            text = "কোনো ডাটা নেই!"
        
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif data == "menu_help":
        await help_command(update, context)
    
    elif data == "menu_admin" and is_admin(user_id):
        await admin_panel(update, context)

# ====== এডমিন কমান্ড ======

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """এডমিন প্যানেল"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ শুধু এডমিনের জন্য!")
        return
    
    conn = get_db()
    total_users = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
    total_convs = conn.execute("SELECT COUNT(*) as cnt FROM conversions").fetchone()["cnt"]
    banned_users = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE is_banned = 1").fetchone()["cnt"]
    active_today = conn.execute(
        "SELECT COUNT(*) as cnt FROM users WHERE last_used >= ?",
        (datetime.now().strftime("%Y-%m-%d"),)
    ).fetchone()["cnt"]
    conn.close()
    
    text = (
        "⚙️ **এডমিন প্যানেল** ⚙️\n\n"
        "📊 **পরিসংখ্যান:**\n"
        f"👥 মোট ইউজার: {total_users}\n"
        f"🔄 মোট কনভার্সন: {total_convs}\n"
        f"🚫 ব্যান্ড ইউজার: {banned_users}\n"
        f"📅 আজকের সক্রিয়: {active_today}\n\n"
        "🔧 **এডমিন কমান্ড:**\n"
        "• `/broadcast [মেসেজ]` — সবাইকে মেসেজ\n"
        "• `/ban [user_id]` — ইউজার ব্যান\n"
        "• `/unban [user_id]` — ব্যান তুলে দাও\n"
        "• `/stats` — বিস্তারিত পরিসংখ্যান\n"
        "• `/users` — ইউজার লিস্ট\n"
        "• `/export` — ডাটা এক্সপোর্ট"
    )
    
    if hasattr(update, 'callback_query'):
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

@admin_only
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সব ইউজারকে মেসেজ পাঠাও"""
    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("⚠️ ব্যবহার: `/broadcast [তোমার মেসেজ]`")
        return
    
    conn = get_db()
    users = conn.execute("SELECT user_id FROM users WHERE is_banned = 0").fetchall()
    conn.close()
    
    sent = 0
    failed = 0
    
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user["user_id"],
                text=f"📢 **এডমিন বার্তা:**\n\n{message}",
                parse_mode=ParseMode.MARKDOWN
            )
            sent += 1
        except:
            failed += 1
    
    await update.message.reply_text(
        f"✅ ব্রডকাস্ট সম্পন্ন!\n"
        f"✅ সফল: {sent}\n"
        f"❌ ব্যর্থ: {failed}"
    )

@admin_only
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইউজার ব্যান"""
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ ব্যবহার: `/ban [user_id]`")
        return
    
    target_id = int(args[0])
    conn = get_db()
    conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (target_id,))
    conn.execute(
        "INSERT INTO admin_logs (admin_id, action, target_user_id) VALUES (?, 'ban', ?)",
        (update.effective_user.id, target_id)
    )
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ ইউজার `{target_id}` ব্যান করা হয়েছে!")

@admin_only
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইউজার আনব্যান"""
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ ব্যবহার: `/unban [user_id]`")
        return
    
    target_id = int(args[0])
    conn = get_db()
    conn.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (target_id,))
    conn.execute(
        "INSERT INTO admin_logs (admin_id, action, target_user_id) VALUES (?, 'unban', ?)",
        (update.effective_user.id, target_id)
    )
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ ইউজার `{target_id}` আনব্যান করা হয়েছে!")

@admin_only
async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইউজার লিস্ট"""
    conn = get_db()
    users = conn.execute("""
        SELECT u.*, COUNT(c.id) as conv_count 
        FROM users u 
        LEFT JOIN conversions c ON u.user_id = c.user_id 
        GROUP BY u.user_id 
        ORDER BY u.total_conversions DESC 
        LIMIT 20
    """).fetchall()
    conn.close()
    
    text = "📋 **ইউজার লিস্ট (শীর্ষ ২০):**\n\n"
    for i, user in enumerate(users, 1):
        badge = "👑" if user["is_admin"] else "🚫" if user["is_banned"] else "👤"
        text += f"{i}. {badge} `{user['user_id']}` — {user['first_name'] or 'N/A'}\n"
        text += f"   └ কনভার্সন: {user['conv_count']}, শেষ: {str(user['last_used'])[:10] if user['last_used'] else 'N/A'}\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

@admin_only
async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ডাটা এক্সপোর্ট"""
    # CSV ফাইল বানাও
    import csv
    import io
    
    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["User ID", "Username", "Name", "Joined", "Last Used", "Total Conversions", "Banned", "Admin", "Voice"])
    
    for user in users:
        writer.writerow([
            user["user_id"], user["username"], user["first_name"],
            user["joined_at"], user["last_used"], user["total_conversions"],
            user["is_banned"], user["is_admin"], user["selected_voice"]
        ])
    
    output.seek(0)
    
    await update.message.reply_document(
        document=io.BytesIO(output.getvalue().encode()),
        filename="girlicbot_users.csv",
        caption="📊 ইউজার ডাটা এক্সপোর্ট"
    )

# ====== মেইন ফাংশন ======

def main():
    """বট চালু"""
    init_db()
    
    # BotFather-এ কমান্ড সেট করো
    commands = [
        ("start", "🔰 বট শুরু করো"),
        ("help", "❓ সাহায্য"),
        ("voices", "🎀 ভয়েস মডেল লিস্ট"),
        ("setvoice", "🎤 ভয়েস মডেল পরিবর্তন করো"),
        ("stats", "📊 তোমার পরিসংখ্যান"),
        ("about", "ℹ️ বট সম্পর্কে"),
        ("admin", "⚙️ এডমিন প্যানেল"),
        ("broadcast", "📢 সবাইকে মেসেজ পাঠাও (এডমিন)"),
        ("ban", "🚫 ইউজার ব্যান করো (এডমিন)"),
        ("unban", "✅ ইউজার আনব্যান করো (এডমিন)"),
        ("users", "📋 ইউজার লিস্ট (এডমিন)"),
        ("export", "📊 ডাটা এক্সপোর্ট (এডমिन)")
    ]
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # ইউজার কমান্ড
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("voices", voices_command))
    app.add_handler(CommandHandler("setvoice", set_voice_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("about", about_command))
    
    # এডমিন কমান্ড
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("users", users_list))
    app.add_handler(CommandHandler("export", export_data))
    
    # ভয়েস হ্যান্ডলার
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    
    # কলব্যাক হ্যান্ডলার
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # সব ভয়েস মডেলের জন্য কমান্ড (জাস্ট ইন কেস)
    for key in VOICE_MODELS.keys():
        app.add_handler(CommandHandler(key, set_voice_command))
    
    logger.info("🤖 GirlicBot চালু হচ্ছে...")
    print("=" * 50)
    print("  🎀 Voice Queen চালু হচ্ছে...")
    print(f"  👑 এডমিন আইডি: {ADMIN_IDS}")
    print(f"  🌐 বট: https://t.me/{(await app.bot.get_me()).username}")
    print("=" * 50)
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

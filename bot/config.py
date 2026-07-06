import os

# ====== @BotFather থেকে নাও ======
BOT_TOKEN = "8956527817:AAETStVWMjg1EXJKUcWRa81X8dGo0rGP5yo"

# ====== তোমার টেলিগ্রাম আইডি (শুধু তুমি এডমিন) ======
ADMIN_IDS = [8636937438]  # তোমার ID দাও

# ====== ভয়েস মডেল ======
# RVC লোকালি চালাতে চাইলে:
RVC_SERVER_URL = "http://127.0.0.1:5000"

# Render-এ হোস্ট করলে API ব্যবহার করবে (নিচে API কী বসাও)
USE_EXTERNAL_API = False  # True করলে নিচের API ব্যবহার করবে
ELEVENLABS_API_KEY = ""
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice (default)

# ====== ভয়েস মডেল তালিকা (girlicbot এর মতো) ======
VOICE_MODELS = {
    "japanese_anime": {
        "name": "🎀 Japanese Anime Girl",
        "desc": "Cute anime girl voice",
        "model_file": "japanese_anime_girl.pth"
    },
    "korean_female": {
        "name": "🌸 Korean Female",
        "desc": "Soft korean female voice",
        "model_file": "korean_female.pth"
    },
    "english_female": {
        "name": "💕 English Female",
        "desc": "Clear english female voice",
        "model_file": "english_female.pth"
    },
    "valentine": {
        "name": "💘 Valentine Girl",
        "desc": "Sweet valentine voice",
        "model_file": "valentine_girl.pth"
    }
}

DEFAULT_VOICE = "japanese_anime"

# ====== চ্যানেল জয়েন বাধ্যতামূলক ======
FORCE_JOIN_CHANNEL = True
CHANNEL_USERNAME = "@voice_queen150k"  # তোমার চ্যানেল
CHANNEL_ID = -1004351921952         # তোমার চ্যানেল ID

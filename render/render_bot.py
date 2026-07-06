"""Render-এ বট চালানোর জন্য এন্ট্রি পয়েন্ট"""
import os
import sys

# bot ফোল্ডার পাথে যোগ করো
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from bot.main import main

if __name__ == "__main__":
    main()

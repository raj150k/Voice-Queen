"""Render-এ ওয়েব চালানোর জন্য এন্ট্রি পয়েন্ট"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from web.app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

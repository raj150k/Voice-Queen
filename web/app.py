import os
import sqlite3
from datetime import timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
app.permanent_session_lifetime = timedelta(hours=24)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'bot', 'girlicbot.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS web_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            telegram_id INTEGER,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        pass_hash = generate_password_hash("admin123")
        conn.execute(
            "INSERT INTO web_users (username, password, is_admin) VALUES (?, ?, 1)",
            ("admin", pass_hash)
        )
        conn.commit()
    except:
        pass
    conn.close()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("প্লিজ লগইন করুন!", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM web_users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()
        
        if user and check_password_hash(user["password"], password):
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = user["is_admin"]
            flash(f"স্বাগতম {username}! 👋", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("ভুল ইউজারনেম বা পাসওয়ার্ড!", "danger")
    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    # বট ডাটাবেস থেকে ইউজার দেখাও
    conn = get_db()
    stats = {}
    try:
        stats["total_users"] = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        stats["total_convs"] = conn.execute("SELECT COUNT(*) as c FROM conversions").fetchone()["c"]
        stats["active_today"] = conn.execute(
            "SELECT COUNT(*) as c FROM users WHERE last_used >= date('now')"
        ).fetchone()["c"]
    except:
        stats = {"total_users": 0, "total_convs": 0, "active_today": 0}
    conn.close()
    
    return render_template("dashboard.html", stats=stats, username=session["username"])

@app.route("/admin")
@login_required
def admin_panel():
    if not session.get("is_admin"):
        flash("অ্যাডমিন ছাড়া প্রবেশযোগ্য নয়!", "danger")
        return redirect(url_for("dashboard"))
    
    conn = get_db()
    users = []
    try:
        users = conn.execute(
            "SELECT user_id, first_name, username, total_conversions, is_banned, joined_at FROM users ORDER BY total_conversions DESC LIMIT 50"
        ).fetchall()
    except:
        pass
    conn.close()
    
    return render_template("admin.html", users=users)

@app.route("/logout")
def logout():
    session.clear()
    flash("লগআউট সফল!", "info")
    return redirect(url_for("index"))

if __name__ == "__main__":
    init_db()
    print("🌐 Voice Queen Web চালু হচ্ছে...")
    print("🔗 http://127.0.0.1:8080")
    print("👤 admin / admin123")
    app.run(host="0.0.0.0", port=8080, debug=True)

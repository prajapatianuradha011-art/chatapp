import eventlet
eventlet.monkey_patch()

import os
from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, emit
import sqlite3
import hashlib

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')


# ── Helpers ──────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """SHA-256 hash for passwords (use bcrypt/argon2 for production)."""
    return hashlib.sha256(password.encode()).hexdigest()


def get_db():
    conn = sqlite3.connect("index.db")
    conn.row_factory = sqlite3.Row          # access columns by name
    return conn


# ── Init DB ───────────────────────────────────────────────────────────────────

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        msg      TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()

init_db()


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = hash_password(request.form['password'])

        try:
            conn = get_db()
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return render_template('signup.html', error="Username already exists ❌")
        finally:
            conn.close()

        return redirect('/login')

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = hash_password(request.form['password'])

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        conn.close()

        if user:
            session['user'] = username
            return redirect('/')
        return render_template('login.html', error="Invalid credentials ❌")

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')


# ── Main page ─────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    if 'user' not in session:
        return redirect('/login')
    return render_template('index.html', username=session['user'])


# ── Socket events ─────────────────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    """Send message history to the newly connected client."""
    username = session.get('user')
    if not username:
        return False                        # reject unauthenticated connections

    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, msg FROM messages ORDER BY id ASC"
    ).fetchall()
    conn.close()

    history = [{"id": r["id"], "username": r["username"], "msg": r["msg"]} for r in rows]
    emit('history', history)


@socketio.on('message')
def handle_message(data):
    username = session.get('user')
    if not username:
        return

    msg = data.get('msg', '').strip()
    if not msg:
        return

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO messages (username, msg) VALUES (?, ?)", (username, msg)
    )
    conn.commit()
    msg_id = cursor.lastrowid
    conn.close()

    # Broadcast to ALL connected clients (including sender)
    emit('new_message', {'id': msg_id, 'username': username, 'msg': msg}, broadcast=True)


@socketio.on('edit_message')
def edit_message(data):
    username = session.get('user')
    if not username:
        return

    msg_id  = data.get('id')
    new_msg = data.get('msg', '').strip()
    if not msg_id or not new_msg:
        return

    conn = get_db()

    # Only the author may edit
    row = conn.execute("SELECT username FROM messages WHERE id=?", (msg_id,)).fetchone()
    if not row or row['username'] != username:
        conn.close()
        emit('error', {'msg': 'Not authorised to edit this message.'})
        return

    conn.execute("UPDATE messages SET msg=? WHERE id=?", (new_msg, msg_id))
    conn.commit()
    conn.close()

    emit('message_edited', {'id': msg_id, 'msg': new_msg}, broadcast=True)


@socketio.on('delete_message')
def delete_message(data):
    username = session.get('user')
    if not username:
        return

    msg_id = data.get('id')
    if not msg_id:
        return

    conn = get_db()

    # Only the author may delete
    row = conn.execute("SELECT username FROM messages WHERE id=?", (msg_id,)).fetchone()
    if not row or row['username'] != username:
        conn.close()
        emit('error', {'msg': 'Not authorised to delete this message.'})
        return

    conn.execute("DELETE FROM messages WHERE id=?", (msg_id,))
    conn.commit()
    conn.close()

    emit('message_deleted', {'id': msg_id}, broadcast=True)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))   # Render injects $PORT automatically
    socketio.run(app, host='0.0.0.0', port=port)
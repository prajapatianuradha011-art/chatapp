import psycopg2
import os
from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, send, emit
import sqlite3

app = Flask(__name__)
app.secret_key = "secret123"
socketio = SocketIO(app)

def get_db():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

# 🔹 Create DB
def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY,
        username TEXT,
        msg TEXT
    )
    """)

    conn.commit()
    conn.close()
init_db()


# 🟢 SIGNUP
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        c = conn.cursor()
        c = conn.cursor()

        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
        except:
            return "Username already exists!"

        conn.close()
        return redirect('/login')

    return render_template('signup.html')


# 🟢 LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        c = conn.cursor()
        c = conn.cursor()

        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()

        conn.close()

        if user:
            session['user'] = username
            return redirect('/')
        else:
            return "Invalid login!"

    return render_template('login.html')


# 🟢 LOGOUT
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')


# 🟢 HOME (CHAT)
@app.route('/')
def home():
    if 'user' not in session:
        return redirect('/login')

    return render_template('index.html', username=session['user'])


# 🟢 CHAT MESSAGE
@socketio.on('message')
def handle_message(data):
    username = session.get('user')
    msg = data['msg']

    conn = get_db()
    c = conn.cursor()
    c = conn.cursor()

    # save message
    c.execute("INSERT INTO messages (username, msg) VALUES (?, ?)", (username, msg))
    conn.commit()

    msg_id = c.lastrowid  # ✅ get message ID
    conn.close()

    # send message with ID
    send({
        "id": msg_id,
        "username": username,
        "msg": msg
    }, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)

send({
    "username": session.get('user'),
    "msg": data['msg']
}, broadcast=True)

@socketio.on('edit_message')
def edit_message(data):
    msg_id = data['id']
    new_msg = data['msg']

    conn = get_db()
    c = conn.cursor()  # ✅ FIXED
    c = conn.cursor()

    c.execute("UPDATE messages SET msg=? WHERE id=?", (new_msg, msg_id))
    conn.commit()
    conn.close()

    emit('message_edited', {'id': msg_id, 'msg': new_msg}, broadcast=True)


@socketio.on('delete_message')
def delete_message(data):
    msg_id = data['id']

    conn = get_db()
    c = conn.cursor()  # ✅ FIXED
    c = conn.cursor()

    c.execute("DELETE FROM messages WHERE id=?", (msg_id,))
    conn.commit()
    conn.close()

    emit('message_deleted', {'id': msg_id}, broadcast=True)

c.execute("INSERT INTO messages (username, msg) VALUES (%s, %s) RETURNING id",
          (username, msg))
msg_id = c.fetchone()[0]
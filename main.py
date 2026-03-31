import sqlite3
import requests
import asyncio
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# --- CONFIGURATION ---
TELEGRAM_TOKEN = "8598233311:AAEInYVR3hBUVhTSHnLzte1fJKUC1NcjL2Y"
NVIDIA_API_KEY = "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"
API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL_NAME = "meta/llama-3.1-405b-instruct"

# --- DATABASE LOGIC ---
def init_db():
    conn = sqlite3.connect('bestie_memory.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS chats 
                     (user_id BIGINT, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def save_to_db(user_id, role, content):
    conn = sqlite3.connect('bestie_memory.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chats (user_id, role, content) VALUES (?, ?, ?)", (user_id, role, content))
    conn.commit()
    conn.close()

def get_history(user_id, limit=20):
    conn = sqlite3.connect('bestie_memory.db')
    cursor = conn.cursor()
    # Pichle 20 messages uthayenge
    cursor.execute("SELECT role, content FROM chats WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?", (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    # Reverse karke wapas bhejna (taaki oldest se newest order ho)
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

# --- AI LOGIC ---
def ask_ai(user_id, user_msg):
    # 1. History load karo
    history = get_history(user_id)
    
    # 2. Messages array taiyar karo
    messages = [
        {"role": "system", "content": "Tu user ki female best friend hai. Hinglish bol. Pichli 20 baatein yaad rakh aur unke basis par natural reply de. Agar user kuch purana puche toh database se dekh kar bata."}
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": user_msg})

    headers = {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": MODEL_NAME, "messages": messages, "temperature": 0.7, "max_tokens": 200}

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=25)
        if response.status_code == 200:
            ai_reply = response.json()['choices'][0]['message']['content']
            # Save both messages to DB
            save_to_db(user_id, "user", user_msg)
            save_to_db(user_id, "assistant", ai_reply)
            return ai_reply
        return "Yaar, dimag kaam nahi kar raha mera abhi (API Error)."
    except:
        return "Net issue hai shayad, phir se bol?"

# --- TELEGRAM HANDLER ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_text = update.message.text
    chat_id = update.effective_chat.id

    # Continuous Typing
    stop_typing = asyncio.Event()
    async def typing_loop():
        while not stop_typing.is_set():
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(4)
    
    t_task = asyncio.create_task(typing_loop())

    try:
        loop = asyncio.get_running_loop()
        reply = await loop.run_in_executor(None, ask_ai, user_id, user_text)
    finally:
        stop_typing.set()
        await t_task

    await update.message.reply_text(reply)

# --- RENDER PORT FIX ---
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")

def run_server():
    httpd = HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), HealthCheck)
    httpd.serve_forever()

async def main():
    init_db()
    threading.Thread(target=run_server, daemon=True).start()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    async with app:
        await app.initialize(); await app.start(); await app.updater.start_polling()
        await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())

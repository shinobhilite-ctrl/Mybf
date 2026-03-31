import sqlite3
import requests
import asyncio
import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# --- CONFIGURATION ---
TELEGRAM_TOKEN = "8598233311:AAEInYVR3hBUVhTSHnLzte1fJKUC1NcjL2Y"
NVIDIA_API_KEY = "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"
API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL_NAME = "meta/llama-3.1-405b-instruct"

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- DUMMY SERVER FOR RENDER (Port Fix) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"Health check server started on port {port}")
    server.serve_forever()

# --- SQL DATABASE ---
def init_db():
    conn = sqlite3.connect('bestie_chats.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS history 
                     (user_id INTEGER, name TEXT, msg TEXT, reply TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def save_to_sql(user_id, name, msg, reply):
    conn = sqlite3.connect('bestie_chats.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history (user_id, name, msg, reply) VALUES (?, ?, ?, ?)", 
                   (user_id, name, msg, reply))
    conn.commit()
    conn.close()

# --- AI REPLY SYNC ---
def get_ai_reply_sync(user_text):
    headers = {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "Tu ek cute female best friend hai. Hinglish bol. Short reply de. Thoda mazaak kar."},
            {"role": "user", "content": user_text}
        ],
        "temperature": 0.7, "max_tokens": 150
    }
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=20)
        return response.json()['choices'][0]['message']['content'] if response.status_code == 200 else "Mood off hai yaar!"
    except:
        return "Net issue hai, thoda wait kar!"

# --- TYPING HELPER ---
async def keep_typing(context, chat_id, stop_event):
    while not stop_event.is_set():
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(4)

# --- MESSAGE HANDLER ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_msg = update.message.text
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(context, chat_id, stop_typing))

    try:
        loop = asyncio.get_event_loop()
        bot_reply = await loop.run_in_executor(None, get_ai_reply_sync, user_msg)
    finally:
        stop_typing.set()
        await typing_task

    save_to_sql(user_id, user_name, user_msg, bot_reply)
    await update.message.reply_text(bot_reply)

# --- MAIN ---
if __name__ == '__main__':
    init_db()
    # Health server ko background thread mein chalayein
    threading.Thread(target=run_health_server, daemon=True).start()
    
    print("Bot is starting with Port Fix... 🚀")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import asyncio
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# --- CONFIGURATION ---
# 1. Apna Naya Telegram Token yahan daalein
TELEGRAM_TOKEN = "8598233311:AAEInYVR3hBUVhTSHnLzte1fJKUC1NcjL2Y"

# 2. NVIDIA API Key
NVIDIA_API_KEY = "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"

# 3. Supabase Connection URI (Settings > Database > Connection String > URI)
# Isko replace karna mat bhulna!
DB_URI = "YOUR_SUPABASE_CONNECTION_STRING_HERE"

API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL_NAME = "meta/llama-3.1-405b-instruct"

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- POSTGRES DATABASE LOGIC (Permanent Memory) ---
def init_db():
    try:
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS chat_history 
                      (user_id BIGINT, role TEXT, content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        cur.close()
        conn.close()
        print("Database Initialized Successfully!")
    except Exception as e:
        print(f"Database Init Error: {e}")

def save_to_db(user_id, role, content):
    try:
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()
        cur.execute("INSERT INTO chat_history (user_id, role, content) VALUES (%s, %s, %s)", (user_id, role, content))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"DB Save Error: {e}")

def get_history(user_id, limit=20):
    try:
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT role, content FROM chat_history WHERE user_id = %s ORDER BY created_at DESC LIMIT %s", (user_id, limit))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        # Reverse order taaki AI ko sahi sequence mile
        return [{"role": r['role'], "content": r['content']} for r in reversed(rows)]
    except Exception as e:
        print(f"DB Fetch Error: {e}")
        return []

# --- AI LOGIC (NVIDIA API) ---
def get_bestie_reply(user_id, user_text):
    # Purani 20 baatein yaad dilana
    history = get_history(user_id)
    
    messages = [{"role": "system", "content": "Tu user ki female best friend hai. Tera naam 'Aura' hai. Tu Hinglish mein baat karti hai. Pichli baatein yaad rakh kar natural aur caring reply de. Short aur cute ban."}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    headers = {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": MODEL_NAME, "messages": messages, "temperature": 0.7, "max_tokens": 250}

    try:
        res = requests.post(API_URL, headers=headers, json=payload, timeout=25)
        if res.status_code == 200:
            reply = res.json()['choices'][0]['message']['content']
            # User aur Bot dono ki baat save karo
            save_to_db(user_id, "user", user_text)
            save_to_db(user_id, "assistant", reply)
            return reply
        return "Yaar, mera dimag thoda ghum gaya hai. Phir se bolo? 🥺"
    except:
        return "Network bahut slow hai yaar, main connect nahi kar paa rahi! 🙄"

# --- TELEGRAM HANDLER ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.message.from_user.id
    user_text = update.message.text
    chat_id = update.effective_chat.id

    # Continuous Typing Status
    stop_typing = asyncio.Event()
    async def typing_loop():
        while not stop_typing.is_set():
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(4)
    
    t_task = asyncio.create_task(typing_loop())

    try:
        # AI se reply mangwana (Thread safe way)
        loop = asyncio.get_running_loop()
        reply = await loop.run_in_executor(None, get_bestie_reply, user_id, user_text)
    finally:
        stop_typing.set()
        await t_task

    await update.message.reply_text(reply)

# --- RENDER HEALTH CHECK FIX (GET & HEAD) ---
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"Bot is alive!")
    
    def do_HEAD(self):
        self.send_response(200); self.end_headers()

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheck)
    print(f"Health Server running on port {port}")
    server.serve_forever()

# --- MAIN RUNNER ---
async def main():
    # Database aur Health Server start karein
    init_db()
    threading.Thread(target=run_server, daemon=True).start()
    
    print("Bestie Bot is starting... 🚀")
    
    # Bot Setup
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True) # Purane backlog messages ignore karega
        print("Bot is 100% Online!")
        await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot Stopped.")

"""
Telegram AI Bot — PROD версия с Webhook
Используйте для деплоя на Render, Heroku, AWS и др.
"""

import os
import logging
import asyncio
import aiohttp
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from flask import Flask, request, jsonify
import threading

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ====== КОНФИГУРАЦИЯ ======
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # Например: https://your-app.onrender.com
PORT = int(os.environ.get("PORT", 10000))

# AI Настройки
AI_SYSTEM_PROMPT = os.environ.get(
    "AI_SYSTEM_PROMPT",
    "Ты — дружелюбный AI-ассистент, который отвечает на сообщения в Telegram. "
    "Отвечай на русском языке, если обращаются на русском. Будь вежливым и полезным."
)

AI_CONFIG = {
    "provider": os.environ.get("AI_PROVIDER", "openrouter"),
    "model": os.environ.get("AI_MODEL", "meta-llama/llama-3.2-3b-instruct:free"),
}


# ====== AI ======

async def ask_ai(message_text: str, history: list = None) -> str:
    messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": message_text})
    
    if AI_CONFIG["provider"] == "gigachat":
        return await ask_gigachat(messages)
    elif AI_CONFIG["provider"] == "openrouter":
        return await ask_openrouter(messages)
    else:
        return "⚠️ AI не настроен. Укажите AI_PROVIDER и API-ключ."


async def ask_openrouter(messages: list) -> str:
    try:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            return "🔧 OPENROUTER_API_KEY не указан."
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": AI_CONFIG["model"],
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 500,
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
                return f"AI Error: {resp.status}"
    except Exception as e:
        logger.error(f"AI error: {e}")
        return "Извините, произошла ошибка. Попробуйте позже."


async def ask_gigachat(messages: list) -> str:
    try:
        api_key = os.environ.get("GIGACHAT_API_KEY", "")
        if not api_key:
            return "🔧 GIGACHAT_API_KEY не указан."
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": os.environ.get("GIGACHAT_MODEL", "GigaChat-Lite"),
                    "messages": messages,
                    "temperature": 0.7,
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
                return f"GigaChat Error: {resp.status}"
    except Exception as e:
        logger.error(f"GigaChat error: {e}")
        return "Ошибка соединения с AI. Попробуйте позже."


# ====== HANDLERS ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>AI Ассистент активирован!</b>\n\n"
        f"Провайдер: <code>{AI_CONFIG['provider']}</code>\n"
        f"Модель: <code>{AI_CONFIG['model']}</code>",
        parse_mode="HTML",
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    has_key = bool(os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GIGACHAT_API_KEY"))
    status_text = "✅ AI подключён" if has_key else "⚠️ Базовый режим"
    await update.message.reply_text(
        f"<b>Статус:</b> {status_text}\n"
        f"Провайдер: {AI_CONFIG['provider']}",
        parse_mode="HTML",
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🗑 Контекст сброшен!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    
    history = context.user_data.get("history", [])
    response = await ask_ai(update.message.text, history)
    
    history.append({"role": "user", "content": update.message.text})
    history.append({"role": "assistant", "content": response})
    context.user_data["history"] = history[-10:]
    
    await update.message.reply_text(response)


# ====== WEB SERVER ======

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return jsonify({
        "status": "running",
        "service": "telegram-ai-bot",
        "ai_provider": AI_CONFIG["provider"],
        "timestamp": datetime.now().isoformat(),
    })


@flask_app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if not application:
        return "Not ready", 503
    
    update = Update.de_json(request.get_json(), application.bot)
    application.process_update(update)
    return "OK", 200


# ====== MAIN ======

application = None

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)


def main():
    global application
    
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не указан!")
        return
    
    print(f"🚀 Запуск AI-бота (webhook mode)")
    print(f"Провайдер: {AI_CONFIG['provider']}")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Настройка webhook
    if WEBHOOK_URL:
        webhook_path = f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"
        application.bot.set_webhook(webhook_path)
        print(f"🔗 Webhook установлен: {webhook_path}")
    
    # Запуск Flask в отдельном потоке
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Запуск polling как fallback
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

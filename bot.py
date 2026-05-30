"""
Telegram AI Bot с GigaChat-Max (Sber) — OAuth 2.0
Работает через polling, запоминает контекст диалога
"""

import os
import logging
import asyncio
import aiohttp
import base64
import ssl
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ====== КОНФИГУРАЦИЯ ======
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# GigaChat-Max OAuth
GIGACHAT_CLIENT_ID = os.environ.get("GIGACHAT_CLIENT_ID", "")
GIGACHAT_CLIENT_SECRET = os.environ.get("GIGACHAT_CLIENT_SECRET", "")
GIGACHAT_SCOPE = os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY", "")
GIGACHAT_MODEL = os.environ.get("GIGACHAT_MODEL", "GigaChat-Max")

# OAuth endpoints
GIGACHAT_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

# Глобальный токен и время истечения
_gigachat_access_token = None
_gigachat_token_expires = None

# Системный промпт
AI_SYSTEM_PROMPT = """Ты — дружелюбный и умный ассистент, который отвечает на сообщения в Telegram от имени хозяина. 
Ты отвечаешь на русском языке, если к тебе обращаются на русском.
Ты вежливый, с хорошим чувством юмора, даёшь развёрнутые и полезные ответы.
Если тебя спрашивают о личных делах хозяина — отвечай тактично, что хозяин скоро ответит лично.
Ты можешь помогать с информацией, советами, переводами, объяснениями.
Всегда оставайся полезным и дружелюбным."""


# ====== GIGACHAT OAUTH 2.0 ======

def get_ssl_context():
    """Создаём SSL контекст с правильными сертификатами"""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    return ssl_context


async def get_gigachat_token() -> str:
    """
    Получаем Access Token для GigaChat-Max через OAuth 2.0
    Токен живёт ~30 минут, кешируем его
    """
    global _gigachat_access_token, _gigachat_token_expires

    # Проверяем, есть ли ещё живой токен
    if _gigachat_access_token and _gigachat_token_expires and datetime.now() < _gigachat_token_expires:
        return _gigachat_access_token

    try:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": GIGACHAT_CLIENT_ID,
            "Authorization": f"Basic {GIGACHAT_AUTH_KEY}",
        }

        data = {
            "scope": GIGACHAT_SCOPE,
        }

        ssl_context = get_ssl_context()

        async with aiohttp.ClientSession() as session:
            async with session.post(
                GIGACHAT_OAUTH_URL,
                headers=headers,
                data=data,
                ssl=ssl_context,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    _gigachat_access_token = result.get("access_token")
                    expires_in = result.get("expires_in", 1800)  # обычно 1800 сек = 30 мин
                    _gigachat_token_expires = datetime.now() + timedelta(seconds=expires_in - 60)  # -60 сек запас
                    logger.info(f"✅ GigaChat-Max токен получен, истекает через {expires_in} сек")
                    return _gigachat_access_token
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Ошибка OAuth: {response.status} — {error_text}")
                    return None

    except Exception as e:
        logger.error(f"❌ Ошибка получения токена GigaChat-Max: {e}")
        return None


# ====== AI ИНТЕГРАЦИЯ ======

async def ask_gigachat(messages: list) -> str:
    """Отправляем запрос к GigaChat-Max API"""
    try:
        token = await get_gigachat_token()
        if not token:
            return "🔧 Не удалось получить токен GigaChat-Max. Проверьте credentials."

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": GIGACHAT_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1000,
        }

        ssl_context = get_ssl_context()

        async with aiohttp.ClientSession() as session:
            async with session.post(
                GIGACHAT_API_URL,
                headers=headers,
                json=payload,
                ssl=ssl_context,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["message"]["content"]
                elif response.status == 401:
                    # Токен истёк, сбрасываем и пробуем снова
                    global _gigachat_access_token, _gigachat_token_expires
                    _gigachat_access_token = None
                    _gigachat_token_expires = None
                    return "🔄 Токен обновлён, попробуйте ещё раз."
                else:
                    error_text = await response.text()
                    logger.error(f"❌ GigaChat-Max API ошибка: {response.status} — {error_text}")
                    return f"⚠️ Ошибка AI: {response.status}"

    except asyncio.TimeoutError:
        return "⏱️ Запрос к AI занял слишком много времени. Попробуйте позже."
    except Exception as e:
        logger.error(f"❌ Ошибка запроса к GigaChat-Max: {e}")
        return "😔 Произошла ошибка при обращении к AI. Попробуйте позже."


async def ask_ai(message_text: str, context_history: list = None) -> str:
    """Главная функция запроса к AI"""
    messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}]
    
    if context_history:
        messages.extend(context_history)
    
    messages.append({"role": "user", "content": message_text})
    
    return await ask_gigachat(messages)


# ====== ОБРАБОТЧИКИ TELEGRAM ======

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    has_ai = bool(GIGACHAT_CLIENT_ID and GIGACHAT_CLIENT_SECRET)
    status = "✅ GigaChat-Max подключён" if has_ai else "⚠️ AI не настроен"
    
    welcome_text = f"""🤖 <b>AI Ассистент активирован!</b>

{status}
Модель: <code>{GIGACHAT_MODEL}</code>

<b>Мои возможности:</b>
• Отвечаю на сообщения с помощью GigaChat-Max
• Поддерживаю русский язык
• Запоминаю контекст разговора (последние 10 сообщений)

<b>Команды:</b>
/start — запуск
/status — статус AI
/reset — сбросить контекст

Просто напишите мне что-нибудь! 👋"""
    
    await update.message.reply_text(welcome_text, parse_mode="HTML")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
    token_status = "✅ Токен активен" if (_gigachat_access_token and datetime.now() < _gigachat_token_expires) else "🔄 Токен не получен"
    
    await update.message.reply_text(
        f"<b>Статус AI:</b>\n"
        f"Провайдер: GigaChat-Max (Sber)\n"
        f"Модель: {GIGACHAT_MODEL}\n"
        f"OAuth: {token_status}\n"
        f"Client ID: {GIGACHAT_CLIENT_ID[:8]}...",
        parse_mode="HTML",
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сброс контекста"""
    context.user_data.clear()
    await update.message.reply_text("🗑 Контекст разговора сброшен!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка входящих сообщений"""
    
    if not update.message or not update.message.text:
        return
    
    user_message = update.message.text
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    logger.info(f"💬 Сообщение от {user_id}: {user_message[:50]}...")
    
    # Показываем "печатает..."
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    # Получаем историю
    context_history = context.user_data.get("history", [])
    
    # Запрашиваем ответ у AI
    ai_response = await ask_ai(user_message, context_history)
    
    # Сохраняем в историю (последние 10 сообщений = 5 пар вопрос-ответ)
    context_history.append({"role": "user", "content": user_message})
    context_history.append({"role": "assistant", "content": ai_response})
    context.user_data["history"] = context_history[-20:]  # 20 = 10 пар
    
    # Отправляем ответ
    await update.message.reply_text(ai_response)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error(f"❌ Ошибка при обработке {update}: {context.error}")
    if update and update.message:
        await update.message.reply_text("😔 Произошла ошибка. Попробуйте ещё раз.")


# ====== ЗАПУСК ======

def main():
    """Главная функция"""
    
    if not BOT_TOKEN:
        print("❌ ОШИБКА: BOT_TOKEN не указан!")
        print("Добавьте BOT_TOKEN в файл .env")
        return
    
    if not GIGACHAT_CLIENT_ID or not GIGACHAT_CLIENT_SECRET:
        print("⚠️ ПРЕДУПРЕЖДЕНИЕ: GigaChat-Max credentials не указаны!")
        print("Бот будет работать, но AI не ответит.")
    
    print("🚀 Запуск AI-бота...")
    print(f"🤖 Telegram бот: подключён")
    print(f"🧠 AI: GigaChat-Max ({GIGACHAT_MODEL})")
    print(f"📡 OAuth: {GIGACHAT_OAUTH_URL}")
    print("⏹️  Нажмите Ctrl+C для остановки\n")
    
    # Создаём приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
#!/bin/bash

# Скрипт запуска Telegram AI Bot с GigaChat

echo "🤖 Telegram AI Bot — Запуск"
echo "============================"

# Проверяем Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 не найден! Установите Python 3.10+"
    exit 1
fi

# Проверяем наличие .env
if [ ! -f ".env" ]; then
    echo "⚠️  Файл .env не найден!"
    echo "Создайте файл .env и добавьте:"
    echo "  BOT_TOKEN=your_token"
    echo "  GIGACHAT_CLIENT_ID=your_id"
    echo "  GIGACHAT_CLIENT_SECRET=your_secret"
    exit 1
fi

# Проверяем наличие виртуального окружения
if [ ! -d "venv" ]; then
    echo "📦 Создаю виртуальное окружение..."
    python3 -m venv venv
fi

# Активируем виртуальное окружение
echo "🔄 Активирую виртуальное окружение..."
source venv/bin/activate

# Устанавливаем/обновляем зависимости
echo "📥 Устанавливаю зависимости..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Проверяем токен
if grep -q "BOT_TOKEN=.*your" .env || grep -q "BOT_TOKEN=$" .env; then
    echo "❌ ОШИБКА: BOT_TOKEN не указан в .env!"
    echo "Отредактируйте файл .env и вставьте токен от @BotFather"
    exit 1
fi

# Запускаем бота
echo ""
echo "🚀 Запускаю бота..."
echo "   Нажмите Ctrl+C для остановки"
echo ""
python3 bot.py
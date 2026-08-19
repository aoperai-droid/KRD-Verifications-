"""
Основной файл Telegram-бота для верификации пользователей.
Версия: 1.0.2
Python: 3.12
"""

import asyncio
import logging
import sys
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramAPIError

from database import Database
from handlers import register_handlers

# Загрузка .env файла если существует
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class VerificationBot:
    """Основной класс бота"""
    
    def __init__(self):
        self.bot = None
        self.dp = None
        self.db = Database()
        
    async def initialize(self):
        """Инициализация бота и базы данных"""
        token = os.getenv('BOT_TOKEN')
        if not token:
            logger.error("BOT_TOKEN не найден в переменных окружения")
            raise ValueError("BOT_TOKEN не найден")
        
        # Инициализация базы данных
        await self.db.initialize()
        logger.info("База данных инициализирована")
        
        # Создание бота с HTML-разметкой по умолчанию
        self.bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        
        # Инициализация диспетчера
        self.dp = Dispatcher(storage=MemoryStorage())
        
        # Регистрация обработчиков
        register_handlers(self.dp, self.bot, self.db)
        logger.info("Обработчики зарегистрированы")
    
    async def start_polling(self):
        """Запуск поллинга"""
        try:
            logger.info("Бот запущен")
            await self.dp.start_polling(
                self.bot,
                allowed_updates=[
                    'message',
                    'callback_query',
                    'chat_member'
                ]
            )
        except TelegramAPIError as e:
            logger.error(f"Ошибка Telegram API: {e}")
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}", exc_info=True)
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Корректное завершение работы"""
        logger.info("Завершение работы бота")
        if self.bot:
            await self.bot.session.close()
        if hasattr(self, 'db'):
            await self.db.close()
        logger.info("Бот остановлен")


async def main():
    """Главная функция"""
    bot_app = VerificationBot()
    
    try:
        await bot_app.initialize()
        await bot_app.start_polling()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка при запуске: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
"""
Модуль обработчиков событий Telegram-бота.
Содержит всю бизнес-логику обработки сообщений и callback'ов.
"""

import asyncio
import logging
import os
import csv
import io
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError

from database import Database
from keyboards import (
    CallbackData,
    generate_math_problem,
    create_verification_keyboard,
    create_admin_menu_keyboard,
    create_back_button,
    create_groups_list_keyboard,
    create_period_filter_keyboard,
    create_user_actions_keyboard
)

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = """
👋 Добро пожаловать, <b>{user_name}</b>! 🎉 Рады видеть тебя в Вейп-Барахолке Краснодара ✨

Перед публикацией объявлений ознакомься с правилами.

🚫 Запрещено:
• Не вейп-тематика
• Оскорбления и спам

⚠️ При скаме пишите: @callumom

🏪 Лучшие вейп-шопы:
https://telegram.me/mixvape1

С уважением,
Ваша Вейп-Барахолка 🫶

---

❗️ Администрация не является стороной сделок между участниками и не может гарантировать их безопасность. Всегда проверяйте информацию самостоятельно и соблюдайте осторожность.
"""


def get_user_display_name(user) -> str:
    """Получение отображаемого имени пользователя"""
    if user.username:
        return f"@{user.username}"
    return user.first_name or "Пользователь"


async def restrict_user(bot: Bot, chat_id: int, user_id: int):
    """Ограничение пользователя в чате"""
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions={
                'can_send_messages': False,
                'can_send_media_messages': False,
                'can_send_other_messages': False,
                'can_add_web_page_previews': False
            }
        )
    except TelegramAPIError as e:
        logger.warning(f"Не удалось ограничить пользователя {user_id}: {e}")


async def unrestrict_user(bot: Bot, chat_id: int, user_id: int):
    """Снятие ограничений с пользователя"""
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions={
                'can_send_messages': True,
                'can_send_media_messages': True,
                'can_send_other_messages': True,
                'can_add_web_page_previews': True
            }
        )
    except TelegramAPIError as e:
        logger.warning(f"Не удалось снять ограничения с пользователя {user_id}: {e}")


async def delete_message_safe(bot: Bot, chat_id: int, message_id: int):
    """Безопасное удаление сообщения"""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramAPIError:
        pass


async def send_welcome_message(bot: Bot, chat_id: int, user_id: int, user_name: str):
    """Отправка и автоудаление приветственного сообщения"""
    try:
        message = await bot.send_message(
            chat_id=chat_id,
            text=WELCOME_MESSAGE.format(user_name=user_name),
            parse_mode="HTML"
        )
        
        await asyncio.sleep(60)
        await delete_message_safe(bot, chat_id, message.message_id)
    except TelegramAPIError as e:
        logger.error(f"Ошибка при отправке приветствия: {e}")


async def handle_new_member(bot: Bot, db: Database, event: ChatMemberUpdated):
    """Обработка входа нового участника"""
    user = event.new_chat_member.user
    chat_id = event.chat.id
    
    if user.is_bot:
        return
    
    existing_user = await db.get_user(user.id, chat_id)
    if existing_user and existing_user['status'] == 'passed':
        await unrestrict_user(bot, chat_id, user.id)
        return
    
    await db.add_user(
        user_id=user.id,
        group_id=chat_id,
        username=user.username,
        first_name=user.first_name
    )
    
    await restrict_user(bot, chat_id, user.id)
    
    problem, correct, answers = generate_math_problem()
    keyboard = create_verification_keyboard(user.id, chat_id, correct, answers)
    
    try:
        message = await bot.send_message(
            chat_id=chat_id,
            text=f"🔐 <b>Проверка для {get_user_display_name(user)}</b>\n\n"
                 f"Решите пример, чтобы получить доступ к чату:\n"
                 f"<code>{problem} = ?</code>\n\n"
                 f"⚠️ Осталось попыток: 3",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        await db.save_verification_message(
            user_id=user.id,
            group_id=chat_id,
            message_id=message.message_id,
            correct_answer=correct
        )
    except TelegramAPIError as e:
        logger.error(f"Ошибка при отправке проверки: {e}")


async def handle_verification_callback(bot: Bot, db: Database, 
                                       callback: CallbackQuery):
    """Обработка callback'а проверки"""
    try:
        _, user_id, group_id, answer, correct = callback.data.split(':')
        user_id = int(user_id)
        group_id = int(group_id)
        answer = int(answer)
        correct = int(correct)
        
        if callback.from_user.id != user_id:
            await callback.answer("❌ Эта проверка не для вас!", show_alert=True)
            return
        
        user_data = await db.get_user(user_id, group_id)
        if not user_data or user_data['status'] in ['passed', 'failed']:
            await callback.answer("⏰ Проверка уже завершена", show_alert=True)
            await delete_message_safe(bot, group_id, callback.message.message_id)
            return
        
        if answer == correct:
            await db.update_user_status(user_id, group_id, 'passed')
            await unrestrict_user(bot, group_id, user_id)
            
            await callback.answer("✅ Верно! Доступ открыт.", show_alert=True)
            await delete_message_safe(bot, group_id, callback.message.message_id)
            
            user_name = get_user_display_name(callback.from_user)
            asyncio.create_task(send_welcome_message(bot, group_id, user_id, user_name))
        else:
            attempts = await db.increment_attempts(user_id, group_id)
            remaining = 3 - attempts
            
            if remaining <= 0:
                await db.update_user_status(user_id, group_id, 'failed')
                await callback.answer("❌ Попытки закончились. Доступ закрыт.", show_alert=True)
                await delete_message_safe(bot, group_id, callback.message.message_id)
            else:
                problem, new_correct, new_answers = generate_math_problem()
                keyboard = create_verification_keyboard(user_id, group_id, new_correct, new_answers)
                
                await callback.message.edit_text(
                    f"🔐 <b>Проверка для {get_user_display_name(callback.from_user)}</b>\n\n"
                    f"❌ Неверный ответ. Попробуйте снова:\n"
                    f"<code>{problem} = ?</code>\n\n"
                    f"⚠️ Осталось попыток: {remaining}",
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                
                await db.save_verification_message(
                    user_id=user_id,
                    group_id=group_id,
                    message_id=callback.message.message_id,
                    correct_answer=new_correct
                )
                
                await callback.answer(f"❌ Неверно. Осталось попыток: {remaining}")
    
    except ValueError as e:
        logger.error(f"Ошибка парсинга callback данных: {e}")
    except TelegramAPIError as e:
        logger.error(f"Ошибка Telegram API: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка в обработке callback: {e}", exc_info=True)


async def handle_admin_command(bot: Bot, db: Database, message: Message):
    """Обработка команды /admin"""
    admin_id = int(os.getenv('ADMIN_ID', 0))
    
    if message.from_user.id != admin_id:
        return
    
    keyboard = create_admin_menu_keyboard()
    await message.answer(
        "🔐 <b>Админ-панель</b>\n\nВыберите действие:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def handle_admin_callback(bot: Bot, db: Database, callback: CallbackQuery):
    """Обработка callback'ов админ-панели"""
    admin_id = int(os.getenv('ADMIN_ID', 0))
    
    if callback.from_user.id != admin_id:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    data = callback.data
    
    try:
        if data == CallbackData.ADMIN_MENU:
            await callback.message.edit_text(
                "🔐 <b>Админ-панель</b>\n\nВыберите действие:",
                reply_markup=create_admin_menu_keyboard(),
                parse_mode="HTML"
            )
        
        elif data == CallbackData.ADMIN_STATS:
            groups = await db.get_all_groups()
            if not groups:
                await callback.message.edit_text(
                    "📊 <b>Статистика</b>\n\nНет данных для отображения.",
                    reply_markup=create_back_button(CallbackData.ADMIN_MENU),
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    "📊 <b>Статистика</b>\n\nВыберите группу:",
                    reply_markup=create_groups_list_keyboard(groups),
                    parse_mode="HTML"
                )
        
        elif data == CallbackData.ADMIN_USERS:
            groups = await db.get_all_groups()
            if not groups:
                await callback.message.edit_text(
                    "👤 <b>Пользователи</b>\n\nНет пользователей для отображения.",
                    reply_markup=create_back_button(CallbackData.ADMIN_MENU),
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    "👤 <b>Пользователи</b>\n\nВыберите группу:",
                    reply_markup=create_groups_list_keyboard(groups),
                    parse_mode="HTML"
                )
        
        elif data.startswith(CallbackData.STATS_GROUP):
            group_id = int(data.split(':')[1])
            await callback.message.edit_text(
                f"📊 <b>Группа {group_id}</b>\n\nВыберите период:",
                reply_markup=create_period_filter_keyboard(group_id),
                parse_mode="HTML"
            )
        
        elif data.startswith(CallbackData.STATS_PERIOD):
            _, group_id, period = data.split(':')
            group_id = int(group_id)
            
            stats = await db.get_statistics(group_id, period)
            users = await db.get_users_by_group(group_id, period)
            
            text = (
                f"📈 <b>Статистика группы {group_id}</b>\n\n"
                f"• Всего участников: {stats['total']}\n"
                f"• Успешно прошли: {stats['passed']}\n"
                f"• Не прошли: {stats['failed']}\n"
                f"• Ожидают проверки: {stats['pending']}\n"
                f"• Процент успешных: {stats['success_rate']}%\n\n"
                f"<b>Последние пользователи:</b>\n"
            )
            
            for user in users[:10]:
                status_emoji = "✅" if user['status'] == 'passed' else "❌" if user['status'] == 'failed' else "⏳"
                text += f"\n{status_emoji} {user['first_name'] or 'N/A'} "
                if user['username']:
                    text += f"(@{user['username']}) "
                text += f"\n   ID: {user['user_id']}"
            
            await callback.message.edit_text(
                text,
                reply_markup=create_back_button(f"{CallbackData.STATS_GROUP}:{group_id}"),
                parse_mode="HTML"
            )
        
        elif data == CallbackData.ADMIN_EXPORT:
            await export_statistics_csv(bot, db, callback)
        
        elif data == CallbackData.ADMIN_UPDATE:
            await callback.message.edit_text(
                "🔐 <b>Админ-панель</b>\n\nДанные обновлены.",
                reply_markup=create_admin_menu_keyboard(),
                parse_mode="HTML"
            )
        
        elif data.startswith(CallbackData.USER_ACTION):
            _, action, user_id, group_id = data.split(':')
            user_id = int(user_id)
            group_id = int(group_id)
            
            if action == 'reset':
                await db.remove_verification(user_id, group_id)
                await callback.answer("✅ Проверка сброшена", show_alert=True)
            
            elif action == 'approve':
                await db.update_user_status(user_id, group_id, 'passed')
                await unrestrict_user(bot, group_id, user_id)
                await callback.answer("✅ Пользователь подтвержден", show_alert=True)
        
        await callback.answer()
    
    except Exception as e:
        logger.error(f"Ошибка в админ-панели: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка", show_alert=True)


async def export_statistics_csv(bot: Bot, db: Database, callback: CallbackQuery):
    """Экспорт статистики в CSV"""
    try:
        groups = await db.get_all_groups()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Group ID', 'User ID', 'Username', 'First Name', 
                         'Status', 'Join Date', 'Verification Date'])
        
        for group_id in groups:
            users = await db.get_users_by_group(group_id)
            for user in users:
                writer.writerow([
                    group_id,
                    user['user_id'],
                    user['username'] or '',
                    user['first_name'] or '',
                    user['status'],
                    user['join_date'],
                    user['verification_date'] or ''
                ])
        
        output.seek(0)
        
        await callback.message.answer_document(
            document=io.BytesIO(output.getvalue().encode('utf-8')),
            filename=f'statistics_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
            caption="📊 Экспорт статистики"
        )
    except Exception as e:
        logger.error(f"Ошибка экспорта: {e}")
        await callback.answer("❌ Ошибка при экспорте", show_alert=True)


async def handle_left_member(bot: Bot, db: Database, event: ChatMemberUpdated):
    """Обработка выхода участника"""
    user = event.old_chat_member.user
    chat_id = event.chat.id
    
    await db.remove_verification(user.id, chat_id)


def register_handlers(dp: Dispatcher, bot: Bot, db: Database):
    """Регистрация всех обработчиков"""
    
    @dp.chat_member()
    async def on_chat_member_update(event: ChatMemberUpdated):
        """Обработчик изменения статуса участника"""
        if event.new_chat_member.status == 'member' and event.old_chat_member.status == 'left':
            await handle_new_member(bot, db, event)
        elif event.new_chat_member.status == 'left':
            await handle_left_member(bot, db, event)
    
    @dp.callback_query(F.data.startswith(CallbackData.VERIFY))
    async def on_verification_callback(callback: CallbackQuery):
        """Обработчик callback'ов верификации"""
        await handle_verification_callback(bot, db, callback)
    
    @dp.message(Command('admin'))
    async def on_admin_command(message: Message):
        """Обработчик команды /admin"""
        await handle_admin_command(bot, db, message)
    
    @dp.callback_query(F.data.startswith('admin_') | 
                       F.data.startswith('stats_') | 
                       F.data.startswith('user_action'))
    async def on_admin_callback(callback: CallbackQuery):
        """Обработчик callback'ов админ-панели"""
        await handle_admin_callback(bot, db, callback)
    
    @dp.message(F.chat.type == 'private')
    async def on_private_message(message: Message):
        """Игнорирование личных сообщений от не-админов"""
        admin_id = int(os.getenv('ADMIN_ID', 0))
        if message.from_user.id != admin_id:
            return
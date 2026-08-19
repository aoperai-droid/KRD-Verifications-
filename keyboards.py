"""
Модуль клавиатур для Telegram-бота.
Содержит все используемые клавиатуры и callback-данные.
"""

import random
from typing import List, Tuple
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class CallbackData:
    """Класс для хранения callback-данных"""
    VERIFY = "verify"
    ADMIN_MENU = "admin_menu"
    ADMIN_STATS = "admin_stats"
    ADMIN_USERS = "admin_users"
    ADMIN_EXPORT = "admin_export"
    ADMIN_RESET = "admin_reset"
    ADMIN_APPROVE = "admin_approve"
    ADMIN_BACK = "admin_back"
    ADMIN_UPDATE = "admin_update"
    STATS_GROUP = "stats_group"
    STATS_PERIOD = "stats_period"
    USER_ACTION = "user_action"


def generate_math_problem() -> Tuple[str, int, List[int]]:
    """
    Генерация математического примера.
    
    Returns:
        Tuple[str, int, List[int]]: (текст примера, правильный ответ, варианты ответов)
    """
    operations = [
        ('+', lambda a, b: a + b),
        ('−', lambda a, b: a - b),
        ('×', lambda a, b: a * b),
        ('÷', lambda a, b: a // b if b != 0 else a)
    ]
    
    operation, func = random.choice(operations)
    
    if operation == '+':
        a = random.randint(1, 20)
        b = random.randint(1, 20)
    elif operation == '−':
        a = random.randint(5, 20)
        b = random.randint(1, a)
    elif operation == '×':
        a = random.randint(1, 10)
        b = random.randint(1, 10)
    else:
        b = random.randint(1, 10)
        a = b * random.randint(1, 10)
    
    correct = func(a, b)
    
    wrong_answers = set()
    while len(wrong_answers) < 2:
        wrong = correct + random.randint(-5, 5)
        if wrong != correct and wrong >= 0:
            wrong_answers.add(wrong)
    
    problem = f"{a} {operation} {b}"
    answers = [correct] + list(wrong_answers)
    random.shuffle(answers)
    
    return problem, correct, answers


def create_verification_keyboard(user_id: int, group_id: int,
                                 correct_answer: int, 
                                 answers: List[int]) -> InlineKeyboardMarkup:
    """
    Создание клавиатуры для проверки.
    
    Args:
        user_id: ID пользователя
        group_id: ID группы
        correct_answer: Правильный ответ
        answers: Перемешанные варианты ответов
    """
    builder = InlineKeyboardBuilder()
    
    for answer in answers:
        callback_data = f"{CallbackData.VERIFY}:{user_id}:{group_id}:{answer}:{correct_answer}"
        builder.button(text=str(answer), callback_data=callback_data)
    
    builder.adjust(3)
    return builder.as_markup()


def create_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Создание главного меню администратора"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="📊 Статистика", callback_data=CallbackData.ADMIN_STATS)
    builder.button(text="👤 Пользователи", callback_data=CallbackData.ADMIN_USERS)
    builder.button(text="📥 Экспорт CSV", callback_data=CallbackData.ADMIN_EXPORT)
    builder.button(text="🔄 Обновить", callback_data=CallbackData.ADMIN_UPDATE)
    
    builder.adjust(1)
    return builder.as_markup()


def create_back_button(callback_data: str) -> InlineKeyboardMarkup:
    """Создание кнопки 'Назад'"""
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data=callback_data)
    return builder.as_markup()


def create_groups_list_keyboard(groups: List[int]) -> InlineKeyboardMarkup:
    """Создание клавиатуры со списком групп"""
    builder = InlineKeyboardBuilder()
    
    for group_id in groups:
        callback_data = f"{CallbackData.STATS_GROUP}:{group_id}"
        builder.button(text=f"Группа {group_id}", callback_data=callback_data)
    
    builder.button(text="◀️ Назад", callback_data=CallbackData.ADMIN_MENU)
    builder.adjust(1)
    return builder.as_markup()


def create_period_filter_keyboard(group_id: int) -> InlineKeyboardMarkup:
    """Создание клавиатуры фильтра по периоду"""
    builder = InlineKeyboardBuilder()
    
    periods = [
        ("Сегодня", "today"),
        ("Вчера", "yesterday"),
        ("7 дней", "7days"),
        ("30 дней", "30days"),
        ("Всё время", "all")
    ]
    
    for name, period in periods:
        callback_data = f"{CallbackData.STATS_PERIOD}:{group_id}:{period}"
        builder.button(text=name, callback_data=callback_data)
    
    builder.button(text="◀️ Назад", callback_data=CallbackData.ADMIN_STATS)
    builder.adjust(2)
    return builder.as_markup()


def create_user_actions_keyboard(user_id: int, group_id: int) -> InlineKeyboardMarkup:
    """Создание клавиатуры действий с пользователем"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="🔄 Сбросить проверку",
        callback_data=f"{CallbackData.USER_ACTION}:reset:{user_id}:{group_id}"
    )
    builder.button(
        text="✅ Подтвердить вручную",
        callback_data=f"{CallbackData.USER_ACTION}:approve:{user_id}:{group_id}"
    )
    builder.button(
        text="◀️ Назад",
        callback_data=f"{CallbackData.ADMIN_USERS}"
    )
    
    builder.adjust(1)
    return builder.as_markup()
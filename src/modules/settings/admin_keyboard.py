# src/modules/settings/admin_keyboard.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Префікс для колбеків адмін-панелі, щоб уникнути конфліктів
ADMIN_PANEL_PREFIX = "admin_p"

# Колбеки для адмін-функцій
CB_ADMIN_LIST_USERS = f"{ADMIN_PANEL_PREFIX}:list_users"
CB_ADMIN_USER_INFO = f"{ADMIN_PANEL_PREFIX}:user_info" # Потребуватиме введення ID
CB_ADMIN_BLOCK_USER = f"{ADMIN_PANEL_PREFIX}:block_user" # Потребуватиме введення ID
CB_ADMIN_UNBLOCK_USER = f"{ADMIN_PANEL_PREFIX}:unblock_user" # Потребуватиме введення ID
CB_ADMIN_BACK_TO_SETTINGS = f"{ADMIN_PANEL_PREFIX}:back_settings" # Повернення до головного меню налаштувань


def get_admin_panel_main_keyboard() -> InlineKeyboardMarkup:
    """
    Головна клавіатура адмін-панелі.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Список користувачів", callback_data=CB_ADMIN_LIST_USERS)
    builder.button(text="ℹ️ Інфо про користувача", callback_data=CB_ADMIN_USER_INFO)
    builder.button(text="🚫 Заблокувати користувача", callback_data=CB_ADMIN_BLOCK_USER)
    builder.button(text="✅ Розблокувати користувача", callback_data=CB_ADMIN_UNBLOCK_USER)
    
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад до Налаштувань", callback_data=CB_ADMIN_BACK_TO_SETTINGS)
    )
    builder.adjust(1) # Кожна кнопка в окремому рядку для кращої читабельності
    return builder.as_markup()

# Тут можна буде додати інші клавіатури, наприклад, для пагінації списку користувачів
# або для підтвердження дій.

# В майбутньому можна буде додати функції для генерації клавіатур для конкретних дій
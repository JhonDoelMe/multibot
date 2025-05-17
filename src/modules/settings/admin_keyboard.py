# src/modules/settings/admin_keyboard.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List

# Импортируем модель User для тайп-хинтинга
from src.db.models import User

ADMIN_PANEL_PREFIX = "admin_p"

CB_ADMIN_LIST_USERS = f"{ADMIN_PANEL_PREFIX}:list_users"
CB_ADMIN_USER_INFO_SELECT_MODE = f"{ADMIN_PANEL_PREFIX}:user_info_select_mode" # Для входа в режим выбора юзера для инфо
CB_ADMIN_BLOCK_USER_ID_INPUT = f"{ADMIN_PANEL_PREFIX}:block_user_id_input"  # Для входа в режим ввода ID для блокировки
CB_ADMIN_UNBLOCK_USER_ID_INPUT = f"{ADMIN_PANEL_PREFIX}:unblock_user_id_input" # Для входа в режим ввода ID для разблокировки
CB_ADMIN_BACK_TO_SETTINGS = f"{ADMIN_PANEL_PREFIX}:back_settings"

# Пагинация для общего списка пользователей
CB_ADMIN_USERS_PAGE_PREFIX = f"{ADMIN_PANEL_PREFIX}:users_page:"
# Пагинация для списка пользователей в режиме выбора для инфо
CB_ADMIN_USER_INFO_PAGE_PREFIX = f"{ADMIN_PANEL_PREFIX}:user_info_page:"

# Выбор конкретного пользователя из списка для показа информации
CB_ADMIN_USER_SELECT_FOR_INFO_PREFIX = f"{ADMIN_PANEL_PREFIX}:user_select_info:"

CB_ADMIN_USERS_BACK_TO_PANEL = f"{ADMIN_PANEL_PREFIX}:users_back_panel"


def get_admin_panel_main_keyboard() -> InlineKeyboardMarkup:
    """
    Головна клавіатура адмін-панелі.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Список користувачів (огляд)", callback_data=CB_ADMIN_LIST_USERS)
    builder.button(text="ℹ️ Інфо про користувача (вибір)", callback_data=CB_ADMIN_USER_INFO_SELECT_MODE)
    builder.button(text="🚫 Заблокувати (ID)", callback_data=CB_ADMIN_BLOCK_USER_ID_INPUT)
    builder.button(text="✅ Розблокувати (ID)", callback_data=CB_ADMIN_UNBLOCK_USER_ID_INPUT)

    builder.row(
        InlineKeyboardButton(text="⬅️ Назад до Налаштувань", callback_data=CB_ADMIN_BACK_TO_SETTINGS)
    )
    builder.adjust(1)
    return builder.as_markup()

def get_admin_users_list_keyboard(
    users_on_page: List[User],
    current_page: int,
    total_pages: int,
    page_callback_prefix: str, # Префикс для кнопок пагинации (разный для разных режимов)
    user_action_callback_prefix: str = "" # Префикс для кнопок действий с юзером (если нужен)
) -> InlineKeyboardMarkup:
    """
    Універсальна клавіатура для списку користувачів з пагінацією.
    Також може включати кнопки для кожного користувача.

    :param users_on_page: Список об'єктів User для поточної сторінки.
    :param current_page: Поточний номер сторінки.
    :param total_pages: Загальна кількість сторінок.
    :param page_callback_prefix: Префікс для callback_data кнопок пагінації
                                (наприклад, CB_ADMIN_USERS_PAGE_PREFIX або CB_ADMIN_USER_INFO_PAGE_PREFIX).
    :param user_action_callback_prefix: Префікс для callback_data кнопок, що генеруються для кожного користувача
                                       (наприклад, CB_ADMIN_USER_SELECT_FOR_INFO_PREFIX).
    """
    builder = InlineKeyboardBuilder()

    if users_on_page:
        for user in users_on_page:
            username_display = f" (@{user.username})" if user.username else ""
            blocked_char = "🚫" if user.is_blocked else "✅"
            button_text = f"{blocked_char} ID: {user.user_id} - {user.first_name or 'N/A'}{username_display}"
            
            # Якщо user_action_callback_prefix передано, робимо кнопки користувачів клікабельними
            if user_action_callback_prefix:
                builder.button(
                    text=button_text,
                    callback_data=f"{user_action_callback_prefix}{user.user_id}"
                )
            # Якщо user_action_callback_prefix не передано, кнопки користувачів не додаються
            # (список буде лише текстовим, а ця функція генерує тільки навігацію)
            # В цьому випадку, текстовий список користувачів формується в хендлері.
            # Однак, для режиму "Інфо про користувача (вибір)", нам потрібні клікабельні юзери.

        if user_action_callback_prefix: # Якщо були кнопки користувачів, розташовуємо їх по одній в рядку
            builder.adjust(1)

    navigation_buttons = []
    if current_page > 1:
        navigation_buttons.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{page_callback_prefix}{current_page - 1}")
        )

    if total_pages > 1:
         navigation_buttons.append(
            InlineKeyboardButton(text=f"📄 {current_page}/{total_pages}", callback_data="admin_p:page_indicator")
        )

    if current_page < total_pages:
        navigation_buttons.append(
            InlineKeyboardButton(text="Вперед ➡️", callback_data=f"{page_callback_prefix}{current_page + 1}")
        )

    if navigation_buttons:
        builder.row(*navigation_buttons)

    builder.row(
        InlineKeyboardButton(text="↩️ В адмін-панель", callback_data=CB_ADMIN_USERS_BACK_TO_PANEL)
    )
    return builder.as_markup()
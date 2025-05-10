# src/modules/alert/handlers.py

import logging
from typing import Union
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery # InlineKeyboardMarkup не потрібен

# sqlalchemy.ext.asyncio.AsyncSession поки не використовується
# from src.handlers.utils import show_main_menu_message # Не використовується тут

from .service import get_active_alerts, format_alerts_message # selected_region_name передається з FSM, якщо потрібно
from .keyboard import get_alert_keyboard, CALLBACK_ALERT_REFRESH

logger = logging.getLogger(__name__)
router = Router(name="alert-module")

async def _show_alerts(bot: Bot, target: Union[Message, CallbackQuery], selected_region_name: str = ""):
    """
    Запитує та відображає статус тривог.
    selected_region_name: Опціонально, для форматування повідомлення, якщо запит був для конкретного регіону.
                          Сервіс get_active_alerts сам обробляє region_id (якщо він є).
    """
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None
    answered_callback = False

    if isinstance(target, CallbackQuery):
        try:
            await target.answer()
            answered_callback = True
        except Exception as e:
            logger.warning(f"Could not answer callback immediately in _show_alerts for user {user_id}: {e}")

    try:
        loading_text = "⏳ Отримую актуальний статус тривог..."
        if selected_region_name: # Якщо є назва регіону, можна додати її до тексту завантаження
            loading_text = f"⏳ Отримую статус тривог для регіону <b>{selected_region_name}</b>..."
        
        if isinstance(target, CallbackQuery):
            status_message = await message_to_edit_or_answer.edit_text(loading_text)
        else: # Message
            status_message = await message_to_edit_or_answer.answer(loading_text)
    except Exception as e:
        logger.warning(f"Could not send/edit 'loading' status message for alerts, user {user_id}: {e}")
        # Якщо не вдалося відправити/відредагувати, status_message залишиться None

    # У get_active_alerts передаємо порожній region_id, якщо selected_region_name не вказано.
    # Якщо в майбутньому буде логіка вибору регіону, тут треба буде передавати відповідний ID.
    # Поки що, для загального статусу, region_id залишається порожнім.
    # Якщо selected_region_name передано, це лише для заголовка повідомлення.
    # Припускаємо, що якщо selected_region_name є, то get_active_alerts був викликаний з відповідним region_id раніше,
    # або selected_region_name використовується лише для контексту в повідомленні.
    # Для простоти, поки що get_active_alerts викликається без region_id (для всієї України).
    # Якщо у вас є логіка для отримання region_id з selected_region_name, її треба додати.
    # Наразі, `selected_region_name` використовується тільки для форматування.
    
    api_response = await get_active_alerts(bot) # Запит по всій Україні
    
    # Передаємо selected_region_name у форматувальник, якщо він є, для коректного заголовка
    message_text = format_alerts_message(api_response, selected_region_name=selected_region_name if selected_region_name else None)
    reply_markup = get_alert_keyboard()

    target_message_for_result = status_message if status_message else message_to_edit_or_answer

    try:
        if status_message:
            await target_message_for_result.edit_text(message_text, reply_markup=reply_markup)
        else:
            await message_to_edit_or_answer.answer(message_text, reply_markup=reply_markup) # Використовуємо вихідне повідомлення
        logger.info(f"Sent alert status (region: '{selected_region_name or 'all'}') to user {user_id}.")
    except Exception as e:
        logger.error(f"Failed to send/edit final alert status message to user {user_id}: {e}")
        try:
            if not status_message: # Якщо початкове повідомлення не було відправлено
                await message_to_edit_or_answer.answer("😥 Вибачте, сталася помилка при відображенні статусу тривог.", reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Truly unable to communicate alert status error to user {user_id}: {e2}")
    finally:
        if isinstance(target, CallbackQuery) and not answered_callback:
            try:
                await target.answer()
            except Exception as e:
                logger.warning(f"Final attempt to answer alert callback for user {user_id} also failed: {e}")


async def alert_entry_point(target: Union[Message, CallbackQuery], bot: Bot):
    user_id = target.from_user.id
    logger.info(f"User {user_id} requested alert status (main entry point).")
    # Для точки входу ми не маємо обраного регіону, тому selected_region_name порожній
    await _show_alerts(bot, target, selected_region_name="")

@router.callback_query(F.data == CALLBACK_ALERT_REFRESH)
async def handle_alert_refresh(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} requested alert status refresh.")
    # При оновленні також використовуємо загальний статус по Україні,
    # якщо немає механізму збереження/передачі обраного регіону.
    # Якщо ви додасте FSM для вибору регіону, тут треба буде отримувати region_name зі стану.
    await _show_alerts(bot, callback, selected_region_name="")
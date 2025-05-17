# src/modules/alert/handlers.py

import logging
from typing import Union, Optional # Добавлен Optional
from datetime import datetime

from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
# Импортируем TelegramBadRequest для обработки ошибок API Telegram
from aiogram.exceptions import TelegramBadRequest


from src import config as app_config

from .service import get_active_alerts, format_alerts_message
from .keyboard import get_alert_keyboard, CALLBACK_ALERT_REFRESH
# Меняем импорт на функцию генерации PNG
from .map_generator import generate_alert_map_image_png, generate_alert_map_image_svg # SVG для fallback

logger = logging.getLogger(__name__)
router = Router(name="alert-module")

async def _show_alerts_map_or_text(bot: Bot, target: Union[Message, CallbackQuery], selected_region_name: str = ""):
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message: Optional[Message] = None # Явно указываем тип и возможность None
    answered_callback = False

    if isinstance(target, CallbackQuery):
        try:
            await target.answer()
            answered_callback = True
        except Exception as e:
            logger.warning(f"Could not answer callback immediately for user {user_id}: {e}")

    try:
        loading_text = "⏳ Оновлюю карту/статус тривог..."
        if isinstance(target, CallbackQuery) and message_to_edit_or_answer:
            # Убедимся, что message_to_edit_or_answer существует, прежде чем вызывать edit_text
            status_message = await message_to_edit_or_answer.edit_text(loading_text, reply_markup=None)
        elif isinstance(target, Message): # Явное условие для Message
            status_message = await message_to_edit_or_answer.answer(loading_text)
        # Если target - CallbackQuery, но message_to_edit_or_answer - None, status_message останется None
        # Это может произойти, если target.message не существует, что маловероятно для валидного CallbackQuery
    except Exception as e:
        logger.warning(f"Could not send/edit 'loading' status for alerts map, user {user_id}: {e}")
        # Если не удалось отправить/отредактировать, status_message останется None

    api_response = await get_active_alerts(bot)
    reply_markup_for_message = get_alert_keyboard()

    map_png_bytes: Optional[bytes] = None
    map_svg_bytes: Optional[bytes] = None # Для fallback на SVG документ

    if api_response.get("status") == "success" and isinstance(api_response.get("data"), list):
        map_png_bytes = await generate_alert_map_image_png(api_response["data"])
        if not map_png_bytes: # Если PNG не сгенерировался, пытаемся получить SVG
            logger.warning(f"PNG map generation failed for user {user_id}. Attempting SVG fallback.")
            map_svg_bytes = await generate_alert_map_image_svg(api_response["data"])

    current_time_str = datetime.now(app_config.TZ_KYIV).strftime('%H:%M %d.%m.%Y')
    caption_text = f"🗺️ Карта повітряних тривог України.\nОновлено: {current_time_str}"

    message_sent_successfully = False
    try:
        if map_png_bytes:
            photo_to_send = BufferedInputFile(map_png_bytes, filename="ukraine_alerts_map.png")
            if status_message: # Если сообщение "Оновлюю..." было успешно отправлено/отредактировано
                try:
                    await bot.delete_message(chat_id=status_message.chat.id, message_id=status_message.message_id)
                except TelegramBadRequest as e_del:
                    logger.warning(f"Non-critical: Failed to delete status_message (PNG block) for user {user_id}: {e_del}")

                # Теперь отправляем новое фото в любом случае (если status_message был или не был)
                # Тип target уже не важен здесь, так как мы используем bot.send_photo
                # или target.answer_photo для Message, если status_message изначально не было.
                # Но так как мы удалили status_message, всегда отправляем новое через bot.send_photo
                # или через target.answer_photo если status_message не было.
                # Для унификации, после удаления, используем bot.send_photo
                chat_id_to_send = target.message.chat.id if isinstance(target, CallbackQuery) else target.chat.id
                await bot.send_photo(
                    chat_id=chat_id_to_send,
                    photo=photo_to_send,
                    caption=caption_text,
                    reply_markup=reply_markup_for_message
                )
            else: # status_message is None (сообщение "Оновлюю..." не удалось отправить/отредактировать) - отправляем новое сообщение
                 if isinstance(target, CallbackQuery):
                    if not answered_callback:
                        try: await target.answer()
                        except Exception: pass
                        answered_callback = True
                    await bot.send_photo(
                        chat_id=target.message.chat.id,
                        photo=photo_to_send,
                        caption=caption_text,
                        reply_markup=reply_markup_for_message
                    )
                 elif isinstance(target, Message):
                     await target.answer_photo(
                        photo=photo_to_send,
                        caption=caption_text,
                        reply_markup=reply_markup_for_message
                     )
            logger.info(f"Sent alert map (PNG photo) to user {user_id}.")
            message_sent_successfully = True
        elif map_svg_bytes: # Fallback на SVG документ, если PNG не удалось
            logger.info(f"Sending SVG document as fallback for user {user_id}.")
            document_to_send = BufferedInputFile(map_svg_bytes, filename="ukraine_alerts_map.svg")
            if status_message:
                try:
                    await bot.delete_message(chat_id=status_message.chat.id, message_id=status_message.message_id)
                except TelegramBadRequest as e_del:
                    logger.warning(f"Non-critical: Failed to delete status_message (SVG block) for user {user_id}: {e_del}")
                
                chat_id_to_send = target.message.chat.id if isinstance(target, CallbackQuery) else target.chat.id
                await bot.send_document(
                    chat_id=chat_id_to_send,
                    document=document_to_send,
                    caption=caption_text,
                    reply_markup=reply_markup_for_message
                )
            else: # status_message is None
                 if isinstance(target, CallbackQuery):
                    if not answered_callback:
                        try: await target.answer()
                        except Exception: pass
                        answered_callback = True
                    await bot.send_document(
                        chat_id=target.message.chat.id,
                        document=document_to_send,
                        caption=caption_text,
                        reply_markup=reply_markup_for_message
                    )
                 elif isinstance(target, Message):
                     await target.answer_document(
                        document=document_to_send,
                        caption=caption_text,
                        reply_markup=reply_markup_for_message
                     )
            logger.info(f"Sent alert map (SVG document fallback) to user {user_id}.")
            message_sent_successfully = True

        if not message_sent_successfully: # Если ни PNG, ни SVG не сгенерировались/отправились
            logger.warning(f"Failed to generate/send any map for user {user_id}. Falling back to text.")
            text_message_fallback = "😥 Не вдалося згенерувати карту тривог.\n"
            if api_response.get("status") == "error":
                text_message_fallback += f"Помилка API: {api_response.get('message', 'Невідома помилка')}"
            else:
                # Убедимся, что selected_region_name передается, если он есть
                region_name_for_format = selected_region_name if selected_region_name else None
                text_message_fallback += "\n" + format_alerts_message(api_response, selected_region_name=region_name_for_format)

            if status_message: # Если было сообщение "Оновлюю...", редактируем его
                await status_message.edit_text(text_message_fallback, reply_markup=reply_markup_for_message)
            elif message_to_edit_or_answer: # Если status_message не было, но есть исходное сообщение (для Message)
                 # Для CallbackQuery message_to_edit_or_answer это target.message
                 # Для Message target это message_to_edit_or_answer
                if isinstance(target, CallbackQuery) and target.message:
                    await target.message.answer(text_message_fallback, reply_markup=reply_markup_for_message)
                elif isinstance(target, Message):
                    await target.answer(text_message_fallback, reply_markup=reply_markup_for_message)
            else: # Крайний случай, если ничего нет
                chat_id_to_send = target.message.chat.id if isinstance(target, CallbackQuery) and target.message else target.chat.id if isinstance(target, Message) else None
                if chat_id_to_send:
                    await bot.send_message(chat_id_to_send, text_message_fallback, reply_markup=reply_markup_for_message)


    except Exception as e_send:
        logger.exception(f"Failed to send/edit final alert message (map or text) to user {user_id}:", exc_info=True)
        try:
            fallback_error_text = "Виникла помилка при оновленні статусу тривог. Спробуйте пізніше."
            # Попытка отправить новое сообщение об ошибке, если редактирование не удалось или status_message нет
            chat_id_to_send = None
            if isinstance(target, Message):
                chat_id_to_send = target.chat.id
            elif isinstance(target, CallbackQuery) and target.message:
                chat_id_to_send = target.message.chat.id
            
            if chat_id_to_send:
                 # Если status_message есть и его можно отредактировать
                if status_message:
                    try:
                        await status_message.edit_text(fallback_error_text, reply_markup=None) # Убираем клавиатуру при ошибке
                        return # Успешно отредактировали
                    except Exception:
                        pass # Если редактирование не удалось, отправим новое сообщение ниже
                
                # Если status_message не было или его не удалось отредактировать
                await bot.send_message(chat_id_to_send, fallback_error_text, reply_markup=None)

        except Exception as e_final_fallback:
            logger.error(f"Truly unable to communicate any alert status error to user {user_id}: {e_final_fallback}")

    # Убедимся, что на колбэк ответили, если это не было сделано ранее и это CallbackQuery
    if isinstance(target, CallbackQuery) and not answered_callback:
        try: await target.answer()
        except Exception: pass


async def alert_entry_point(target: Union[Message, CallbackQuery], bot: Bot):
    user_id = target.from_user.id
    logger.info(f"User {user_id} requested alert status (map entry point).")
    await _show_alerts_map_or_text(bot, target, selected_region_name="")

@router.callback_query(F.data == CALLBACK_ALERT_REFRESH)
async def handle_alert_refresh(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} requested alert status map refresh.")
    await _show_alerts_map_or_text(bot, callback, selected_region_name="")
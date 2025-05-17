# src/modules/alert_backup/handlers.py

import logging
from typing import Union, Optional, List, Dict, Any # Добавлены List, Dict, Any, Optional
from datetime import datetime

from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.exceptions import TelegramBadRequest

from src import config as app_config # Для TZ_KYIV

# Импорты сервиса и клавиатур этого модуля
from .service import get_backup_alerts, format_backup_alerts_message
from .keyboard import get_alert_backup_keyboard, CALLBACK_ALERT_BACKUP_REFRESH

# Импортируем генератор карт из основного модуля тревог и его маппинг
from src.modules.alert.map_generator import (
    generate_alert_map_image_png,
    generate_alert_map_image_svg,
    REGION_NAME_TO_SVG_ID_MAP # Нужен для трансформации данных
)

logger = logging.getLogger(__name__)
router = Router(name="alert-backup-module")


def _transform_backup_alerts_for_map(raw_alerts_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Преобразует "плоский" список тревог от alerts.in.ua в структуру,
    ожидаемую map_generator.py (список регионов с флагом активной тревоги).
    """
    map_formatted_alerts: List[Dict[str, Any]] = []
    active_alert_regions_for_map = set()

    known_map_region_names = set(REGION_NAME_TO_SVG_ID_MAP.keys())

    for alert_item in raw_alerts_list:
        if not isinstance(alert_item, dict):
            continue

        # Извлекаем названия местоположений из ответа API alerts.in.ua
        location_title = alert_item.get("location_title", "").strip()
        location_oblast = alert_item.get("location_oblast", "").strip()
        
        matched_region_name = None
        # Проверяем, соответствует ли location_title напрямую ключу в REGION_NAME_TO_SVG_ID_MAP (например, "м. Київ")
        if location_title in known_map_region_names:
            matched_region_name = location_title
        # Иначе проверяем, соответствует ли location_oblast ключу
        elif location_oblast in known_map_region_names:
            matched_region_name = location_oblast
        
        if matched_region_name:
            active_alert_regions_for_map.add(matched_region_name)
        # else:
            # logger.debug(f"Backup alert location not directly mappable to primary map regions: title='{location_title}', oblast='{location_oblast}'")

    # Создаем список словарей для генератора карты
    for region_name in active_alert_regions_for_map:
        # map_generator ожидает "regionName" и "activeAlerts" (непустой список/массив)
        map_formatted_alerts.append({"regionName": region_name, "activeAlerts": [True]})
    
    # logger.debug(f"Transformed backup alerts for map: {map_formatted_alerts}")
    return map_formatted_alerts


async def _show_backup_alerts(bot: Bot, target: Union[Message, CallbackQuery]):
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message: Optional[Message] = None
    answered_callback = False

    if isinstance(target, CallbackQuery):
        try:
            await target.answer()
            answered_callback = True
        except Exception as e:
            logger.warning(f"Could not answer callback immediately in _show_backup_alerts for user {user_id}: {e}")
    
    try:
        loading_text = "⏳ Отримую резервний статус тривог (з картою)..."
        if isinstance(target, CallbackQuery) and message_to_edit_or_answer:
            status_message = await message_to_edit_or_answer.edit_text(loading_text, reply_markup=None)
        elif isinstance(target, Message):
            status_message = await message_to_edit_or_answer.answer(loading_text)
    except Exception as e:
        logger.warning(f"Could not send/edit 'loading' status message for backup alerts, user {user_id}: {e}")

    api_response = await get_backup_alerts(bot) # Это словарь от backup_service
    reply_markup_for_message = get_alert_backup_keyboard()

    map_png_bytes: Optional[bytes] = None
    map_svg_bytes: Optional[bytes] = None
    transformed_alerts_for_map: List[Dict[str, Any]] = []

    # Пытаемся сгенерировать карту, если API вернуло успешные данные
    if api_response.get("status") == "success":
        raw_alerts_list = api_response.get("data", [])
        if isinstance(raw_alerts_list, list):
            transformed_alerts_for_map = _transform_backup_alerts_for_map(raw_alerts_list)
            if transformed_alerts_for_map: # Если есть что отображать на карте
                map_png_bytes = await generate_alert_map_image_png(transformed_alerts_for_map)
                if not map_png_bytes:
                    logger.warning(f"Backup Alert: PNG map generation failed for user {user_id}. Attempting SVG fallback.")
                    map_svg_bytes = await generate_alert_map_image_svg(transformed_alerts_for_map)
            # else: # Если список регионов для карты пуст (например, нет тревог или не удалось сопоставить)
                # logger.info(f"Backup Alert: No regions to display on map for user {user_id} after transformation.")
        # else:
            # logger.error(f"Backup Alert: API data for alerts is not a list for user {user_id}.")
            

    current_time_str = datetime.now(app_config.TZ_KYIV).strftime('%H:%M %d.%m.%Y')
    # Используем '(резерв)' в заголовке карты
    caption_text = f"🗺️ Карта повітряних тривог (резерв).\nОновлено: {current_time_str}"

    message_sent_successfully = False
    try:
        if map_png_bytes:
            photo_to_send = BufferedInputFile(map_png_bytes, filename="ukraine_alerts_map_backup.png")
            if status_message:
                try:
                    await bot.delete_message(chat_id=status_message.chat.id, message_id=status_message.message_id)
                except TelegramBadRequest as e_del:
                    logger.warning(f"Non-critical: Failed to delete status_message (PNG backup block) for user {user_id}: {e_del}")
                
                chat_id_to_send = target.message.chat.id if isinstance(target, CallbackQuery) else target.chat.id
                await bot.send_photo(
                    chat_id=chat_id_to_send,
                    photo=photo_to_send,
                    caption=caption_text,
                    reply_markup=reply_markup_for_message
                )
            else: # status_message is None
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
            logger.info(f"Sent backup alert map (PNG photo) to user {user_id}.")
            message_sent_successfully = True
        elif map_svg_bytes:
            logger.info(f"Sending backup SVG document as fallback for user {user_id}.")
            document_to_send = BufferedInputFile(map_svg_bytes, filename="ukraine_alerts_map_backup.svg")
            if status_message:
                try:
                    await bot.delete_message(chat_id=status_message.chat.id, message_id=status_message.message_id)
                except TelegramBadRequest as e_del:
                    logger.warning(f"Non-critical: Failed to delete status_message (SVG backup block) for user {user_id}: {e_del}")

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
            logger.info(f"Sent backup alert map (SVG document fallback) to user {user_id}.")
            message_sent_successfully = True

        # Фоллбэк на текстовое сообщение, если карта не отправлена
        if not message_sent_successfully:
            logger.info(f"Backup Alert: Falling back to text message for user {user_id} (map not sent/generated).")
            text_message_fallback = format_backup_alerts_message(api_response) # Используем существующий форматер текста

            if status_message:
                await status_message.edit_text(text_message_fallback, reply_markup=reply_markup_for_message)
            elif message_to_edit_or_answer :
                if isinstance(target, CallbackQuery) and target.message:
                     await target.message.answer(text_message_fallback, reply_markup=reply_markup_for_message)
                elif isinstance(target, Message):
                     await target.answer(text_message_fallback, reply_markup=reply_markup_for_message)
            else: # Крайний случай
                chat_id_to_send = target.message.chat.id if isinstance(target, CallbackQuery) and target.message else target.chat.id if isinstance(target, Message) else None
                if chat_id_to_send:
                    await bot.send_message(chat_id_to_send, text_message_fallback, reply_markup=reply_markup_for_message)
            logger.info(f"Sent backup alert status (text fallback) to user {user_id}.")


    except Exception as e_send:
        logger.exception(f"Failed to send/edit final backup alert message (map or text) to user {user_id}:", exc_info=True)
        try:
            fallback_error_text = "Виникла помилка при оновленні резервного статусу тривог. Спробуйте пізніше."
            chat_id_to_send = None
            if isinstance(target, Message):
                chat_id_to_send = target.chat.id
            elif isinstance(target, CallbackQuery) and target.message:
                chat_id_to_send = target.message.chat.id
            
            if chat_id_to_send:
                if status_message:
                    try:
                        await status_message.edit_text(fallback_error_text, reply_markup=None)
                        return 
                    except Exception:
                        pass 
                await bot.send_message(chat_id_to_send, fallback_error_text, reply_markup=None)

        except Exception as e_final_fallback:
            logger.error(f"Truly unable to communicate any backup alert status error to user {user_id}: {e_final_fallback}")

    if isinstance(target, CallbackQuery) and not answered_callback:
        try: await target.answer()
        except Exception: pass


async def alert_backup_entry_point(target: Union[Message, CallbackQuery], bot: Bot):
    user_id = target.from_user.id
    logger.info(f"User {user_id} requested backup alert status (map entry point).")
    await _show_backup_alerts(bot, target)

@router.callback_query(F.data == CALLBACK_ALERT_BACKUP_REFRESH)
async def handle_alert_backup_refresh(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} requested backup alert status map refresh.")
    await _show_backup_alerts(bot, callback)
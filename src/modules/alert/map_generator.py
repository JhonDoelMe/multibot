# src/modules/alert/map_generator.py

import xml.etree.ElementTree as ET
import io
import os
from typing import List, Dict, Optional
import logging
import cairosvg

logger = logging.getLogger(__name__)

SVG_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'ukraine_regions_map.svg')

# ВАЖНО: Ключи здесь должны ТОЧНО соответствовать полю "regionName" из ответа API UkraineAlarm для ОБЛАСТЕЙ
REGION_NAME_TO_SVG_ID_MAP: Dict[str, str] = {
    "м. Київ": "UA-30",
    "Київська область": "UA-32",
    "Вінницька область": "UA-05",
    "Волинська область": "UA-07",
    "Дніпропетровська область": "UA-12",
    "Донецька область": "UA-14",
    "Житомирська область": "UA-18",
    "Закарпатська область": "UA-21",
    "Запорізька область": "UA-23",
    "Івано-Франківська область": "UA-26",
    "Кіровоградська область": "UA-35",
    "Луганська область": "UA-09",
    "Львівська область": "UA-46",
    "Миколаївська область": "UA-48",
    "Одеська область": "UA-51",
    "Полтавська область": "UA-53",
    "Рівненська область": "UA-56",
    "Сумська область": "UA-59",
    "Тернопільська область": "UA-61",
    "Харківська область": "UA-63",
    "Херсонська область": "UA-65",
    "Хмельницька область": "UA-68",
    "Черкаська область": "UA-71",
    "Чернівецька область": "UA-77",
    "Чернігівська область": "UA-74",
    "Автономна Республіка Крим": "UA-43",
    "м. Севастополь": "UA-40",
    # Дополнительные возможные варианты написания от API (если отличаются)
    # Например, если API иногда возвращает "Київ" вместо "м. Київ" для города:
    # "Київ": "UA-30",
}

ALERT_COLOR = "#FF0000"
NO_ALERT_COLOR = "#B0B0B0"
# Можно добавить цвета для обводки, если хотите
# DEFAULT_STROKE_COLOR = "#333333"
# ALERT_STROKE_COLOR = "#8B0000"
# STROKE_WIDTH = "1"
# ALERT_STROKE_WIDTH = "1.5"

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
ET.register_namespace('', SVG_NAMESPACE)


async def _generate_modified_svg_bytes(api_regions_data: List[Dict]) -> Optional[bytes]:
    if not os.path.exists(SVG_TEMPLATE_PATH):
        logger.error(f"SVG template not found at {SVG_TEMPLATE_PATH}")
        return None

    try:
        tree = ET.parse(SVG_TEMPLATE_PATH)
        root = tree.getroot()
        active_svg_ids = set()
        all_known_svg_ids_from_map = set(REGION_NAME_TO_SVG_ID_MAP.values())

        for region_api_object in api_regions_data: # region_api_object - это словарь для одной области/основного региона из API
            # Получаем название области из объекта региона
            oblast_name_from_api = region_api_object.get("regionName")

            if not oblast_name_from_api:
                logger.warning(f"Skipping API region object due to missing 'regionName': {region_api_object}")
                continue

            # Проверяем, есть ли активные тревоги в этой области
            if region_api_object.get("activeAlerts"):
                svg_id = REGION_NAME_TO_SVG_ID_MAP.get(oblast_name_from_api)
                if svg_id:
                    active_svg_ids.add(svg_id)
                else:
                    # Логируем предупреждение только если название ОБЛАСТИ из API не найдено в маппинге.
                    # Это поможет отловить неточности в REGION_NAME_TO_SVG_ID_MAP.
                    # Названия громад/районов из activeAlerts[...].locationTitle здесь не используются для поиска ключа.
                    logger.warning(f"No SVG ID mapping in REGION_NAME_TO_SVG_ID_MAP for API 'regionName': '{oblast_name_from_api}'")
            # else:
                # logger.debug(f"No active alerts for region: '{oblast_name_from_api}'")


        logger.debug(f"SVG IDs to color RED for alerts: {active_svg_ids}")

        for path_element in root.findall(f".//{{{SVG_NAMESPACE}}}path[@id]"):
            current_id = path_element.get("id")
            if current_id in all_known_svg_ids_from_map: # Обрабатываем только известные нам регионы
                is_alert_active_for_this_id = current_id in active_svg_ids
                path_element.set('fill', ALERT_COLOR if is_alert_active_for_this_id else NO_ALERT_COLOR)
                # Опционально: установка обводки
                # path_element.set('stroke', ALERT_STROKE_COLOR if is_alert_active_for_this_id else DEFAULT_STROKE_COLOR)
                # path_element.set('stroke-width', ALERT_STROKE_WIDTH if is_alert_active_for_this_id else STROKE_WIDTH)

        svg_bytes_io = io.BytesIO()
        tree.write(svg_bytes_io, encoding='utf-8', xml_declaration=True)
        return svg_bytes_io.getvalue()

    except FileNotFoundError:
        logger.error(f"SVG template file not found at {SVG_TEMPLATE_PATH} (during generation).")
        return None
    except ET.ParseError as e_parse:
        logger.error(f"Error parsing SVG template: {e_parse}")
        return None
    except Exception as e:
        logger.exception("Unexpected error generating modified SVG bytes:", exc_info=True)
        return None


async def generate_alert_map_image_png(api_regions_data: List[Dict], output_width: int = 700) -> Optional[bytes]:
    svg_bytes = await _generate_modified_svg_bytes(api_regions_data)
    if not svg_bytes:
        logger.error("SVG generation failed, cannot convert to PNG.")
        return None
    try:
        png_bytes = cairosvg.svg2png(bytestring=svg_bytes, output_width=output_width, dpi=150)
        logger.info(f"SVG map successfully converted to PNG using CairoSVG (width: {output_width}px).")
        return png_bytes
    except Exception as e:
        logger.exception("Error converting SVG to PNG using CairoSVG:", exc_info=True)
        return None

async def generate_alert_map_image_svg(api_regions_data: List[Dict]) -> Optional[bytes]:
    return await _generate_modified_svg_bytes(api_regions_data)
# src/modules/alert/map_generator.py

import xml.etree.ElementTree as ET
import io
import os
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

SVG_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'ukraine_regions_map.svg')

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
}

ALERT_COLOR = "#FF0000"
NO_ALERT_COLOR = "#B0B0B0"
DEFAULT_PATH_COLOR = "#CCCCCC" 

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
ET.register_namespace('', SVG_NAMESPACE)

async def _generate_modified_svg_bytes(api_regions_data: List[Dict]) -> Optional[bytes]:
    """
    Внутренняя функция для генерации модифицированных SVG-байт.
    """
    if not os.path.exists(SVG_TEMPLATE_PATH):
        logger.error(f"SVG template not found at {SVG_TEMPLATE_PATH}")
        return None
    try:
        tree = ET.parse(SVG_TEMPLATE_PATH)
        root = tree.getroot()
        active_svg_ids = set()
        all_known_svg_ids_from_map = set(REGION_NAME_TO_SVG_ID_MAP.values())

        for region_api_data in api_regions_data:
            if region_api_data.get("activeAlerts"):
                region_name_from_api = region_api_data.get("regionName")
                if region_name_from_api:
                    svg_id = REGION_NAME_TO_SVG_ID_MAP.get(region_name_from_api)
                    if svg_id:
                        active_svg_ids.add(svg_id)
                    else:
                        logger.warning(f"No SVG ID mapping found for API region: '{region_name_from_api}'")
        
        logger.debug(f"SVG IDs to color RED for alerts: {active_svg_ids}")

        for path_element in root.findall(f".//{{{SVG_NAMESPACE}}}path[@id]"):
            current_id = path_element.get("id")
            if current_id in all_known_svg_ids_from_map:
                if current_id in active_svg_ids:
                    path_element.set('fill', ALERT_COLOR)
                else:
                    path_element.set('fill', NO_ALERT_COLOR)
            # else: # Опционально: цвет для неизвестных регионов, если они есть в SVG, но не в маппинге
            #     path_element.set('fill', DEFAULT_PATH_COLOR) 
        
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
    """
    Генерирует PNG изображение карты тревог.
    Сначала создает SVG, затем конвертирует его в PNG.
    """
    svg_bytes = await _generate_modified_svg_bytes(api_regions_data)
    if not svg_bytes:
        logger.error("SVG generation failed, cannot convert to PNG.")
        return None
    try:
        import cairosvg
        # Увеличим DPI для лучшего качества, если понадобится, или `scale`
        # parent_width и parent_height можно использовать, если SVG имеет относительные размеры
        png_bytes = cairosvg.svg2png(bytestring=svg_bytes, output_width=output_width, dpi=150) 
        logger.info(f"SVG map successfully converted to PNG (width: {output_width}px, dpi: 150).")
        return png_bytes
    except ImportError:
        logger.error("cairosvg library is not installed or importable. Cannot convert SVG to PNG.")
        return None # Важно вернуть None, чтобы хендлер знал, что PNG не готов
    except Exception as e:
        logger.exception("Error converting SVG to PNG:", exc_info=True)
        return None

# Оставляем функцию генерации SVG, если она понадобится для отправки как документа или для отладки
async def generate_alert_map_image_svg(api_regions_data: List[Dict]) -> Optional[bytes]:
    return await _generate_modified_svg_bytes(api_regions_data)
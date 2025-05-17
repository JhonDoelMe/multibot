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

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
ET.register_namespace('', SVG_NAMESPACE)

async def _generate_modified_svg_bytes(api_regions_data: List[Dict]) -> Optional[bytes]:
    # ... (эта функция остается такой же, как в предыдущем ответе, 
    #    она генерирует модифицированные SVG байты) ...
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
    Генерирует PNG изображение карты тревог используя svglib и reportlab.
    """
    svg_bytes = await _generate_modified_svg_bytes(api_regions_data)
    if not svg_bytes:
        logger.error("SVG generation failed, cannot convert to PNG.")
        return None
    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM
        from reportlab.lib.utils import ImageReader # Для BytesIO
        from PIL import Image # Для определения DPI и масштабирования

        # Читаем SVG из байтов
        svg_file_like = io.BytesIO(svg_bytes)
        drawing = svg2rlg(svg_file_like)

        if not drawing:
            logger.error("svglib.svg2rlg returned None, cannot render PNG.")
            return None
            
        # Масштабирование для достижения нужной ширины
        # reportlab работает с точками (1/72 дюйма)
        # Нам нужно отмасштабировать drawing, чтобы его ширина стала output_width пикселей при разумном DPI
        # По умолчанию reportlab может рендерить с DPI=72. Если мы хотим output_width, то
        # scale_factor = output_width / drawing.width (если drawing.width в точках)
        
        # Более простой способ - использовать Pillow для финального ресайза,
        # или рендерить в PIL Image и затем масштабировать.
        # renderPM.drawToFile(drawing, "temp_map.png", fmt="PNG") # Временный файл
        # with Image.open("temp_map.png") as img:
        #     img = img.resize((output_width, int(img.height * output_width / img.width)))
        #     png_bytes_io = io.BytesIO()
        #     img.save(png_bytes_io, format="PNG")
        #     png_bytes = png_bytes_io.getvalue()
        # os.remove("temp_map.png")
        
        # Прямой рендеринг в байты с ReportLab, но контроль размера сложнее.
        # Попробуем рендерить в PIL Image, а затем получить байты.
        pil_image = renderPM.drawToPIL(drawing, bg=0xffffff, dpi=150) # bg - цвет фона (белый)
        
        if pil_image:
            # Масштабируем изображение PIL до нужной ширины, сохраняя пропорции
            original_width, original_height = pil_image.size
            if original_width == 0 : # Предохранитель
                logger.error("PIL image from renderPM has zero width.")
                return None

            aspect_ratio = original_height / original_width
            new_height = int(output_width * aspect_ratio)
            
            resized_image = pil_image.resize((output_width, new_height), Image.Resampling.LANCZOS)
            
            png_bytes_io = io.BytesIO()
            resized_image.save(png_bytes_io, format="PNG")
            png_bytes = png_bytes_io.getvalue()
            logger.info(f"SVG map successfully converted to PNG using svglib/reportlab (width: {output_width}px).")
            return png_bytes
        else:
            logger.error("renderPM.drawToPIL returned None.")
            return None

    except ImportError:
        logger.error("svglib or reportlab or Pillow is not installed. Cannot convert SVG to PNG.")
        return None
    except Exception as e:
        logger.exception("Error converting SVG to PNG using svglib/reportlab:", exc_info=True)
        return None

async def generate_alert_map_image_svg(api_regions_data: List[Dict]) -> Optional[bytes]:
    return await _generate_modified_svg_bytes(api_regions_data)
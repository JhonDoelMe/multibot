# test_reportlab.py
from reportlab.graphics import renderPM
from reportlab.graphics.shapes import Rect, Drawing
from reportlab.lib.colors import red

try:
    d = Drawing(100, 100)
    d.add(Rect(10, 10, 80, 80, fillColor=red))
    renderPM.drawToFile(d, "test_rect.png", fmt="PNG")
    print("ReportLab test_rect.png created successfully.")
except Exception as e:
    print(f"ReportLab test error: {e}")
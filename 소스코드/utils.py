# utils.py
import os
import sys
from pathlib import Path
from config import ROLE_COLOR, AREA_TINT, GOOGLE_CREDENTIALS_FILENAME

# ---------- 색상 유틸 ----------
def _clamp(x):
    return max(0, min(255, int(round(x))))

def adjust_color(hex_color, factor):
    """factor>0 밝게, factor<0 어둡게."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    if factor >= 0:
        r = _clamp(r + (255 - r) * factor)
        g = _clamp(g + (255 - g) * factor)
        b = _clamp(b + (255 - b) * factor)
    else:
        k = 1.0 + factor
        r = _clamp(r * k); g = _clamp(g * k); b = _clamp(b * k)
    return f"#{r:02x}{g:02x}{b:02x}"

def color_for(area, role):
    base = ROLE_COLOR.get(role, ROLE_COLOR["빈칸"])
    tint = AREA_TINT.get(area, 0.0)
    return adjust_color(base, tint)

# ---------- 데이터 경로 유틸 ----------
def google_credentials_path() -> str:
    # 이 스크립트 파일의 위치를 기준으로 키 파일의 절대 경로를 찾습니다.
    # pyinstaller로 원-파일 EXE를 만들 경우, sys._MEIPASS를 사용해야 할 수 있습니다.
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, GOOGLE_CREDENTIALS_FILENAME)

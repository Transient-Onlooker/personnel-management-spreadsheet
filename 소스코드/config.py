# config.py

# ---------- App Info ----------
APP_TITLE = "송파교육박람회 인원관리 프로그램"
VERSION = "v2.0 (Refactored)"

# ---------- Roster Config ----------
ROLE_COLOR = {
    "부스": "#cfe8ff",
    "홍보": "#d7f9db",
    "상주": "#ffe3cf",
    "빈칸": "#f3f4f6",
}
AREA_TINT = {"inside": 0.00, "outside": -0.10, "rest": 0.18}
SESSIONS = ["1부(10:00-13:00)", "2부(14:00-17:00)"]

# ---------- Reservation (Spreadsheet) Config ----------
SPREADSHEET_NAME = "송파교육박람회_인원관리"
WORKSHEET_NAME_DATA = "예약"
WORKSHEET_NAME_CONF = "설정"
CATEGORIES = ("우주정거장", "우주탐사차량")
HEADERS = ["ID", "시간", "이름", "전화뒷4자리", "체험", "참여", "참여시각"]

CHECK_EMPTY = "☐"
CHECK_DONE  = "☑"

THRESHOLDS = {10, 5, 4, 3, 2, 1, 0}

# ---------- Google API Config ----------
# 구글 인증 키 파일명 (반드시 프로그램과 같은 폴더에 위치해야 함)
# 기존 `인원관리(spreadsheet - old)` 폴더에 있던 json 파일을 복사해서 사용하세요.
GOOGLE_CREDENTIALS_FILENAME = "gen-lang-client-0094187890-a949d3db2173.json"

WORKSHEET_NAME_PEOPLE = "인원명단"
PEOPLE_HEADERS = ["이름", "전화번호", "역할", "참여시간"]


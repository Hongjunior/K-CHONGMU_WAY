FACILITY_TYPES = [
    ("meeting_room", "회의실"),
    ("lecture_room", "교육장"),
    ("office", "사무실"),
    ("cafeteria", "식당"),
    ("shuttle_stop", "셔틀 탑승장"),
    ("entrance_auth", "출입카드 인증 위치"),
    ("inspection_site", "현장점검 장소"),
    ("etc", "기타"),
]
FACILITY_TYPE_LABELS = dict(FACILITY_TYPES)

EDGE_NODE_TYPES = ["facility", "floor", "building"]
EDGE_NODE_TYPE_LABELS = {"facility": "시설", "floor": "층", "building": "건물"}

EDGE_MODES = [
    ("walk", "도보"),
    ("elevator", "엘리베이터"),
    ("shuttle", "셔틀"),
]
EDGE_MODE_LABELS = dict(EDGE_MODES)

ROLES = ["user", "admin"]
ROLE_LABELS = {"user": "일반 사용자", "admin": "관리자"}

PRIORITIES = [("low", "낮음"), ("normal", "보통"), ("high", "높음")]
PRIORITY_LABELS = dict(PRIORITIES)

STATUSES = [("planned", "예정"), ("done", "완료"), ("on_hold", "보류")]
STATUS_LABELS = dict(STATUSES)

SCHEDULE_CATEGORIES = [
    ("inspection", "점검"),
    ("meeting", "회의"),
    ("supply", "비품"),
    ("settlement", "정산"),
    ("etc", "기타"),
]
SCHEDULE_CATEGORY_LABELS = dict(SCHEDULE_CATEGORIES)

DURATION_OPTIONS = [15, 30, 45, 60, 90, 120, 180]

# Landmarks that exist on the real, larger campus but are not part of the
# limited set of buildings Etners staff actually use — shown on maps for
# scale/realism only, never clickable and never tied to real building rows.
# (Lives here, not in blueprints/mapview.py, so blueprints/schedules.py can
# also use it for the inline "동선" section on the day view without a
# circular import between the two blueprints.)
DECORATIVE_LANDMARKS = [
    {"name": "본관", "pos_x": 8, "pos_y": 8},
    {"name": "복지동", "pos_x": 65, "pos_y": 88},
    {"name": "교육원", "pos_x": 50, "pos_y": 12},
    {"name": "주차타워", "pos_x": 92, "pos_y": 65},
]

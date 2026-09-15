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

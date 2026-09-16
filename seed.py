from sqlalchemy import text
from werkzeug.security import generate_password_hash


def seed_demo_data(engine):
    with engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) AS c FROM worksites")).mappings().first()["c"]
        if count > 0:
            return

        worksite_id = conn.execute(
            text("INSERT INTO worksites (name, description) VALUES (:name, :desc) RETURNING id"),
            {"name": "삼성전자 WS센터 (수원)", "desc": "테스트용 시드 사업장 (건물/시설/셔틀 데이터 포함)"},
        ).scalar()

        conn.execute(
            text(
                "INSERT INTO users (username, password_hash, role, current_worksite_id) "
                "VALUES (:u, :p, :r, :w)"
            ),
            [
                {"u": "admin", "p": generate_password_hash("admin1234"), "r": "admin", "w": worksite_id},
                {"u": "user1", "p": generate_password_hash("user1234"), "r": "user", "w": worksite_id},
            ],
        )

        building_ids = {}
        for name, pos_x, pos_y in [
            ("A동", 20, 30),
            ("B동", 50, 20),
            ("C동", 80, 30),
            ("식당동", 50, 70),
            # Two of the original "decorative, no-access" landmarks promoted to real,
            # selectable buildings (see mapview.py's DECORATIVE_LANDMARKS) so schedule
            # registration has more than just A/B/C동 to pick from.
            ("연구동", 12, 60),
            ("제2연구센터", 35, 88),
        ]:
            bid = conn.execute(
                text(
                    "INSERT INTO buildings (worksite_id, name, pos_x, pos_y) "
                    "VALUES (:w, :n, :x, :y) RETURNING id"
                ),
                {"w": worksite_id, "n": name, "x": pos_x, "y": pos_y},
            ).scalar()
            building_ids[name] = bid

        floor_ids = {}
        floor_plan = [
            ("A동", "1층", 1),
            ("A동", "6층", 2),
            ("B동", "1층", 1),
            ("B동", "5층", 2),
            ("C동", "1층", 1),
            ("C동", "12층", 2),
            ("식당동", "1층", 1),
            ("연구동", "1층", 1),
            ("연구동", "2층", 2),
            ("제2연구센터", "1층", 1),
            ("제2연구센터", "2층", 2),
        ]
        for building, label, order in floor_plan:
            fid = conn.execute(
                text(
                    "INSERT INTO floors (building_id, floor_label, floor_order) "
                    "VALUES (:b, :l, :o) RETURNING id"
                ),
                {"b": building_ids[building], "l": label, "o": order},
            ).scalar()
            floor_ids[(building, label)] = fid

        # Facility names are intentionally short (no building/floor prefix) — every
        # place that displays them already prepends "{building} {floor}", so baking
        # the same prefix into the name itself produced doubled-up labels like
        # "C동 12층 C동 12층 회의실". Keyed by (building, name) since these short
        # names repeat across buildings (e.g. every building's shuttle stop).
        facility_ids = {}
        facility_plan = [
            # building, floor, name, type, desc, open, close, x, y, w, h
            ("A동", "6층", "회의실", "meeting_room", "본관 A동 6층 대회의실", "09:00", "19:00", 30, 40, 20, 18),
            ("A동", "6층", "제1교육장", "lecture_room", "사내 교육/강의용 공간", "09:00", "19:00", 70, 40, 22, 18),
            ("B동", "5층", "현장점검 장소", "inspection_site", "설비 현장점검 구역", "08:00", "18:00", 50, 55, 26, 22),
            ("C동", "12층", "회의실", "meeting_room", "임원 회의실", "09:00", "20:00", 50, 35, 22, 18),
            ("식당동", "1층", "F열", "cafeteria", "구내식당 F열 좌석 구역", "11:00", "14:00", 30, 55, 20, 16),
            # 카드출입/셔틀 정류장류는 "위치"일 뿐 회의 등을 잡을 장소가 아니라서 일정 등록의
            # 지도 선택기에서는 선택 불가 처리(facility_picker.js) — 대신 운영시간을 조금씩
            # 다르게 줘서 지도 안내(클릭 시 상세정보)에는 실제 운영시간이 보이게 한다.
            ("A동", "1층", "정문 셔틀장", "shuttle_stop", "A동 정문 앞 셔틀 탑승장", "06:30", "22:30", 20, 90, 6, 6),
            ("B동", "1층", "후문 셔틀장", "shuttle_stop", "B동 후문 셔틀 탑승장", "07:00", "21:30", 80, 90, 6, 6),
            ("C동", "1층", "출입카드 인증 위치", "entrance_auth", "C동 로비 출입카드 인증 게이트", "06:00", "23:00", 30, 90, 6, 6),
            ("C동", "1층", "정문 셔틀장", "shuttle_stop", "C동 정문 셔틀 탑승장", "06:45", "22:00", 70, 90, 6, 6),
            ("식당동", "1층", "셔틀 승하차장", "shuttle_stop", "식당동 앞 셔틀 승하차장", "07:15", "21:45", 50, 90, 6, 6),
            ("연구동", "1층", "셔틀 정류장", "shuttle_stop", "연구동 앞 셔틀 정류장", "07:20", "20:40", 50, 90, 6, 6),
            ("연구동", "2층", "세미나실", "meeting_room", "연구동 세미나실", "09:00", "18:30", 50, 40, 20, 18),
            ("제2연구센터", "1층", "셔틀 정류장", "shuttle_stop", "제2연구센터 앞 셔틀 정류장", "07:40", "19:50", 50, 90, 6, 6),
            ("제2연구센터", "2층", "대회의실", "meeting_room", "제2연구센터 대회의실", "08:30", "19:30", 50, 40, 22, 18),
        ]
        for building, floor, name, ftype, desc, open_h, close_h, x, y, w, h in facility_plan:
            fac_id = conn.execute(
                text(
                    "INSERT INTO facilities "
                    "(floor_id, name, facility_type, description, operating_hours_open, "
                    " operating_hours_close, pos_x, pos_y, shape_w, shape_h) "
                    "VALUES (:fl, :n, :t, :d, :oh, :ch, :x, :y, :w, :h) RETURNING id"
                ),
                {
                    "fl": floor_ids[(building, floor)],
                    "n": name,
                    "t": ftype,
                    "d": desc,
                    "oh": open_h,
                    "ch": close_h,
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                },
            ).scalar()
            facility_ids[(building, name)] = fac_id

        # Deliberately varied numbers per route (not a single repeated template) so the
        # demo timetable/route-map actually looks like a real, mixed shuttle network:
        # a fast frequent hop, a longer less-frequent one, a lunchtime-only shuttle, etc.
        route_plan = [
            {
                "name": "A동-B동 순환 셔틀", "dep": ("A동", "정문 셔틀장"), "arr": ("B동", "후문 셔틀장"),
                "travel": 5, "wait": 2, "start": "07:30", "end": "20:00", "interval": 10,
            },
            {
                "name": "B동-C동 순환 셔틀", "dep": ("B동", "후문 셔틀장"), "arr": ("C동", "정문 셔틀장"),
                "travel": 12, "wait": 4, "start": "08:00", "end": "19:00", "interval": 20,
            },
            {
                "name": "C동-식당동 순환 셔틀", "dep": ("C동", "정문 셔틀장"), "arr": ("식당동", "셔틀 승하차장"),
                "travel": 7, "wait": 3, "start": "11:00", "end": "14:30", "interval": 15,
            },
            {
                "name": "식당동-A동 순환 셔틀", "dep": ("식당동", "셔틀 승하차장"), "arr": ("A동", "정문 셔틀장"),
                "travel": 9, "wait": 5, "start": "08:00", "end": "18:30", "interval": 30,
            },
            {
                "name": "A동-C동 급행 셔틀", "dep": ("A동", "정문 셔틀장"), "arr": ("C동", "정문 셔틀장"),
                "travel": 15, "wait": 8, "start": "07:00", "end": "21:00", "interval": 40,
            },
            {
                "name": "연구동-A동 셔틀", "dep": ("연구동", "셔틀 정류장"), "arr": ("A동", "정문 셔틀장"),
                "travel": 6, "wait": 3, "start": "07:20", "end": "19:40", "interval": 25,
            },
            {
                "name": "제2연구센터-식당동 셔틀", "dep": ("제2연구센터", "셔틀 정류장"), "arr": ("식당동", "셔틀 승하차장"),
                "travel": 5, "wait": 2, "start": "07:40", "end": "19:10", "interval": 20,
            },
        ]
        route_ids = {}
        for r in route_plan:
            rid = conn.execute(
                text(
                    "INSERT INTO shuttle_routes "
                    "(worksite_id, route_name, departure_facility_id, arrival_facility_id, "
                    " travel_minutes, waiting_minutes, operation_start, operation_end, interval_minutes) "
                    "VALUES (:w, :rn, :dep, :arr, :tm, :wm, :os, :oe, :iv) RETURNING id"
                ),
                {
                    "w": worksite_id,
                    "rn": r["name"],
                    "dep": facility_ids[r["dep"]],
                    "arr": facility_ids[r["arr"]],
                    "tm": r["travel"],
                    "wm": r["wait"],
                    "os": r["start"],
                    "oe": r["end"],
                    "iv": r["interval"],
                },
            ).scalar()
            route_ids[r["name"]] = rid

        # Shuttle edges are one-way (the loop only runs in one direction). Edge minutes
        # mirror each route's own travel+wait so Phase 2's travel-time calculation uses
        # the same numbers shown on the timetable page.
        for r in route_plan:
            conn.execute(
                text(
                    "INSERT INTO move_edges "
                    "(worksite_id, from_node_type, from_node_id, to_node_type, to_node_id, "
                    " mode, minutes, bidirectional, shuttle_route_id) "
                    "VALUES (:w, 'facility', :f, 'facility', :t, 'shuttle', :min, :bd, :rid)"
                ),
                {
                    "w": worksite_id,
                    "f": facility_ids[r["dep"]],
                    "t": facility_ids[r["arr"]],
                    "min": r["travel"] + r["wait"],
                    "bd": False,
                    "rid": route_ids[r["name"]],
                },
            )

        # One elevator edge per building, 1층 <-> the spec's named floor. Bidirectional.
        for building, top_floor in [
            ("A동", "6층"), ("B동", "5층"), ("C동", "12층"),
            ("연구동", "2층"), ("제2연구센터", "2층"),
        ]:
            conn.execute(
                text(
                    "INSERT INTO move_edges "
                    "(worksite_id, from_node_type, from_node_id, to_node_type, to_node_id, "
                    " mode, minutes, bidirectional) "
                    "VALUES (:w, 'floor', :f, 'floor', :t, 'elevator', 3, :bd)"
                ),
                {
                    "w": worksite_id,
                    "f": floor_ids[(building, "1층")],
                    "t": floor_ids[(building, top_floor)],
                    "bd": True,
                },
            )

        # One walk edge example between two facilities on the same floor. Bidirectional.
        conn.execute(
            text(
                "INSERT INTO move_edges "
                "(worksite_id, from_node_type, from_node_id, to_node_type, to_node_id, "
                " mode, minutes, bidirectional) "
                "VALUES (:w, 'facility', :f, 'facility', :t, 'walk', 2, :bd)"
            ),
            {
                "w": worksite_id,
                "f": facility_ids[("C동", "출입카드 인증 위치")],
                "t": facility_ids[("C동", "정문 셔틀장")],
                "bd": True,
            },
        )

        # Additional worksites the admin can populate later (사업장 전환용, 아직 건물/시설 데이터 없음).
        for name, desc in [
            ("SK D&D (성남)", None),
            ("삼성전자 GA센터 (용인)", None),
            ("삼성전자 GA센터 (동탄)", None),
        ]:
            conn.execute(
                text("INSERT INTO worksites (name, description) VALUES (:n, :d)"),
                {"n": name, "d": desc},
            )


def fix_worksite_names(engine):
    """Idempotent rename for worksites created under an earlier, incorrect name."""
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE worksites SET name = :new WHERE name = :old"),
            {"new": "SK D&D (성남)", "old": "SK하이닉스 D&D (성남)"},
        )


def _demo_worksite_id(conn):
    return conn.execute(
        text("SELECT id FROM worksites WHERE name = :n"),
        {"n": "삼성전자 WS센터 (수원)"},
    ).scalar()


def _facility_id_by_building(conn, worksite_id, building_name, facility_name):
    return conn.execute(
        text(
            "SELECT fac.id FROM facilities fac "
            "JOIN floors fl ON fl.id = fac.floor_id "
            "JOIN buildings b ON b.id = fl.building_id "
            "WHERE b.worksite_id = :w AND b.name = :b AND fac.name = :n"
        ),
        {"w": worksite_id, "b": building_name, "n": facility_name},
    ).scalar()


def ensure_additional_demo_routes(engine):
    """Idempotent top-up for demo worksites that were already seeded before a new
    demo shuttle route was added here, so a live/already-seeded database (e.g. the
    deployed Supabase instance) picks up the new route without a full reseed."""
    with engine.begin() as conn:
        worksite_id = _demo_worksite_id(conn)
        if not worksite_id:
            return

        existing = conn.execute(
            text("SELECT id FROM shuttle_routes WHERE worksite_id = :w AND route_name = :n"),
            {"w": worksite_id, "n": "A동-C동 급행 셔틀"},
        ).scalar()
        if existing:
            return

        dep_id = _facility_id_by_building(conn, worksite_id, "A동", "정문 셔틀장") or \
            _facility_id_by_building(conn, worksite_id, "A동", "A동 정문 셔틀장")
        arr_id = _facility_id_by_building(conn, worksite_id, "C동", "정문 셔틀장") or \
            _facility_id_by_building(conn, worksite_id, "C동", "C동 정문 셔틀장")
        if not dep_id or not arr_id:
            return

        route_id = conn.execute(
            text(
                "INSERT INTO shuttle_routes "
                "(worksite_id, route_name, departure_facility_id, arrival_facility_id, "
                " travel_minutes, waiting_minutes, operation_start, operation_end, interval_minutes) "
                "VALUES (:w, :rn, :dep, :arr, :tm, :wm, :os, :oe, :iv) RETURNING id"
            ),
            {
                "w": worksite_id,
                "rn": "A동-C동 급행 셔틀",
                "dep": dep_id,
                "arr": arr_id,
                "tm": 15,
                "wm": 8,
                "os": "07:00",
                "oe": "21:00",
                "iv": 40,
            },
        ).scalar()

        conn.execute(
            text(
                "INSERT INTO move_edges "
                "(worksite_id, from_node_type, from_node_id, to_node_type, to_node_id, "
                " mode, minutes, bidirectional, shuttle_route_id) "
                "VALUES (:w, 'facility', :f, 'facility', :t, 'shuttle', :min, :bd, :rid)"
            ),
            {"w": worksite_id, "f": dep_id, "t": arr_id, "min": 15 + 8, "bd": False, "rid": route_id},
        )


# (building, old redundant name, new short name) — a facility's name used to repeat
# its own building/floor (e.g. "C동 12층 회의실" on a facility already scoped to C동
# 12층), which doubled up anywhere building+floor+name was shown together
# ("C동 12층 C동 12층 회의실"). Scoped by building since the same old name can't
# always disambiguate (e.g. plain "회의실" wasn't unique before either).
_FACILITY_RENAMES = [
    ("A동", "A동 6층 회의실", "회의실"),
    ("A동", "A동 6층 제1교육장", "제1교육장"),
    ("B동", "B동 5층 현장점검 장소", "현장점검 장소"),
    ("C동", "C동 12층 회의실", "회의실"),
    ("식당동", "식당동 F열", "F열"),
    ("A동", "A동 정문 셔틀장", "정문 셔틀장"),
    ("B동", "B동 후문 셔틀장", "후문 셔틀장"),
    ("C동", "C동 출입카드 인증 위치", "출입카드 인증 위치"),
    ("C동", "C동 정문 셔틀장", "정문 셔틀장"),
    ("식당동", "식당동 셔틀 승하차장", "셔틀 승하차장"),
]

# (building, facility name after rename, open, close) — the shuttle/entrance-auth
# facilities used to have no operating hours at all (shown as "상시"); give each a
# real, slightly different window instead.
_FACILITY_HOURS = [
    ("A동", "정문 셔틀장", "06:30", "22:30"),
    ("B동", "후문 셔틀장", "07:00", "21:30"),
    ("C동", "출입카드 인증 위치", "06:00", "23:00"),
    ("C동", "정문 셔틀장", "06:45", "22:00"),
    ("식당동", "셔틀 승하차장", "07:15", "21:45"),
]


def fix_facility_names(engine):
    """Idempotent rename+hours fix for facilities seeded before names were
    shortened to remove the doubled-up building/floor prefix (see
    _FACILITY_RENAMES above). Safe to run every startup — once a name no longer
    matches the old value, its UPDATE becomes a no-op."""
    with engine.begin() as conn:
        worksite_id = _demo_worksite_id(conn)
        if not worksite_id:
            return

        for building, old_name, new_name in _FACILITY_RENAMES:
            conn.execute(
                text(
                    "UPDATE facilities SET name = :new WHERE name = :old AND floor_id IN "
                    "(SELECT fl.id FROM floors fl JOIN buildings b ON b.id = fl.building_id "
                    " WHERE b.worksite_id = :w AND b.name = :b)"
                ),
                {"new": new_name, "old": old_name, "w": worksite_id, "b": building},
            )

        for building, name, open_h, close_h in _FACILITY_HOURS:
            conn.execute(
                text(
                    "UPDATE facilities SET operating_hours_open = :oh, operating_hours_close = :ch "
                    "WHERE name = :n AND operating_hours_open IS NULL AND floor_id IN "
                    "(SELECT fl.id FROM floors fl JOIN buildings b ON b.id = fl.building_id "
                    " WHERE b.worksite_id = :w AND b.name = :b)"
                ),
                {"oh": open_h, "ch": close_h, "n": name, "w": worksite_id, "b": building},
            )


def ensure_additional_buildings(engine):
    """Idempotent top-up: adds 연구동/제2연구센터 as real, selectable buildings
    (with floors, facilities, a shuttle connection into the existing network, and
    an elevator edge) to a worksite that was seeded before these existed."""
    with engine.begin() as conn:
        worksite_id = _demo_worksite_id(conn)
        if not worksite_id:
            return

        for building, pos_x, pos_y, floors, shuttle_route in [
            (
                "연구동", 12, 60,
                [("1층", 1, "셔틀 정류장", "shuttle_stop", "연구동 앞 셔틀 정류장", "07:20", "20:40", 50, 90, 6, 6),
                 ("2층", 2, "세미나실", "meeting_room", "연구동 세미나실", "09:00", "18:30", 50, 40, 20, 18)],
                {
                    "name": "연구동-A동 셔틀", "arr_building": "A동", "arr_name": "정문 셔틀장",
                    "travel": 6, "wait": 3, "start": "07:20", "end": "19:40", "interval": 25,
                },
            ),
            (
                "제2연구센터", 35, 88,
                [("1층", 1, "셔틀 정류장", "shuttle_stop", "제2연구센터 앞 셔틀 정류장", "07:40", "19:50", 50, 90, 6, 6),
                 ("2층", 2, "대회의실", "meeting_room", "제2연구센터 대회의실", "08:30", "19:30", 50, 40, 22, 18)],
                {
                    "name": "제2연구센터-식당동 셔틀", "arr_building": "식당동", "arr_name": "셔틀 승하차장",
                    "travel": 5, "wait": 2, "start": "07:40", "end": "19:10", "interval": 20,
                },
            ),
        ]:
            existing = conn.execute(
                text("SELECT id FROM buildings WHERE worksite_id = :w AND name = :n"),
                {"w": worksite_id, "n": building},
            ).scalar()
            if existing:
                continue

            building_id = conn.execute(
                text(
                    "INSERT INTO buildings (worksite_id, name, pos_x, pos_y) "
                    "VALUES (:w, :n, :x, :y) RETURNING id"
                ),
                {"w": worksite_id, "n": building, "x": pos_x, "y": pos_y},
            ).scalar()

            floor_id_by_label = {}
            dep_facility_id = None
            for label, order, fac_name, ftype, desc, open_h, close_h, fx, fy, fw, fh in floors:
                if label not in floor_id_by_label:
                    floor_id_by_label[label] = conn.execute(
                        text(
                            "INSERT INTO floors (building_id, floor_label, floor_order) "
                            "VALUES (:b, :l, :o) RETURNING id"
                        ),
                        {"b": building_id, "l": label, "o": order},
                    ).scalar()

                fac_id = conn.execute(
                    text(
                        "INSERT INTO facilities "
                        "(floor_id, name, facility_type, description, operating_hours_open, "
                        " operating_hours_close, pos_x, pos_y, shape_w, shape_h) "
                        "VALUES (:fl, :n, :t, :d, :oh, :ch, :x, :y, :w, :h) RETURNING id"
                    ),
                    {
                        "fl": floor_id_by_label[label],
                        "n": fac_name,
                        "t": ftype,
                        "d": desc,
                        "oh": open_h,
                        "ch": close_h,
                        "x": fx,
                        "y": fy,
                        "w": fw,
                        "h": fh,
                    },
                ).scalar()
                if ftype == "shuttle_stop":
                    dep_facility_id = fac_id

            if len(floor_id_by_label) == 2:
                labels = list(floor_id_by_label)  # insertion order == floors list order (1층, then 2층)
                conn.execute(
                    text(
                        "INSERT INTO move_edges "
                        "(worksite_id, from_node_type, from_node_id, to_node_type, to_node_id, "
                        " mode, minutes, bidirectional) "
                        "VALUES (:w, 'floor', :f, 'floor', :t, 'elevator', 3, :bd)"
                    ),
                    {
                        "w": worksite_id,
                        "f": floor_id_by_label[labels[0]],
                        "t": floor_id_by_label[labels[1]],
                        "bd": True,
                    },
                )

            arr_facility_id = _facility_id_by_building(
                conn, worksite_id, shuttle_route["arr_building"], shuttle_route["arr_name"]
            )
            if dep_facility_id and arr_facility_id:
                route_id = conn.execute(
                    text(
                        "INSERT INTO shuttle_routes "
                        "(worksite_id, route_name, departure_facility_id, arrival_facility_id, "
                        " travel_minutes, waiting_minutes, operation_start, operation_end, interval_minutes) "
                        "VALUES (:w, :rn, :dep, :arr, :tm, :wm, :os, :oe, :iv) RETURNING id"
                    ),
                    {
                        "w": worksite_id,
                        "rn": shuttle_route["name"],
                        "dep": dep_facility_id,
                        "arr": arr_facility_id,
                        "tm": shuttle_route["travel"],
                        "wm": shuttle_route["wait"],
                        "os": shuttle_route["start"],
                        "oe": shuttle_route["end"],
                        "iv": shuttle_route["interval"],
                    },
                ).scalar()
                conn.execute(
                    text(
                        "INSERT INTO move_edges "
                        "(worksite_id, from_node_type, from_node_id, to_node_type, to_node_id, "
                        " mode, minutes, bidirectional, shuttle_route_id) "
                        "VALUES (:w, 'facility', :f, 'facility', :t, 'shuttle', :min, :bd, :rid)"
                    ),
                    {
                        "w": worksite_id,
                        "f": dep_facility_id,
                        "t": arr_facility_id,
                        "min": shuttle_route["travel"] + shuttle_route["wait"],
                        "bd": False,
                        "rid": route_id,
                    },
                )

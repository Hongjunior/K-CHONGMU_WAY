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

        facility_ids = {}
        facility_plan = [
            # building, floor, name, type, desc, open, close, x, y, w, h
            ("A동", "6층", "A동 6층 회의실", "meeting_room", "본관 A동 6층 대회의실", "09:00", "19:00", 30, 40, 20, 18),
            ("A동", "6층", "A동 6층 제1교육장", "lecture_room", "사내 교육/강의용 공간", "09:00", "19:00", 70, 40, 22, 18),
            ("B동", "5층", "B동 5층 현장점검 장소", "inspection_site", "설비 현장점검 구역", "08:00", "18:00", 50, 55, 26, 22),
            ("C동", "12층", "C동 12층 회의실", "meeting_room", "임원 회의실", "09:00", "20:00", 50, 35, 22, 18),
            ("식당동", "1층", "식당동 F열", "cafeteria", "구내식당 F열 좌석 구역", "11:00", "14:00", 30, 55, 20, 16),
            ("A동", "1층", "A동 정문 셔틀장", "shuttle_stop", "A동 정문 앞 셔틀 탑승장", None, None, 20, 90, 6, 6),
            ("B동", "1층", "B동 후문 셔틀장", "shuttle_stop", "B동 후문 셔틀 탑승장", None, None, 80, 90, 6, 6),
            ("C동", "1층", "C동 출입카드 인증 위치", "entrance_auth", "C동 로비 출입카드 인증 게이트", None, None, 30, 90, 6, 6),
            ("C동", "1층", "C동 정문 셔틀장", "shuttle_stop", "C동 정문 셔틀 탑승장", None, None, 70, 90, 6, 6),
            ("식당동", "1층", "식당동 셔틀 승하차장", "shuttle_stop", "식당동 앞 셔틀 승하차장", None, None, 50, 90, 6, 6),
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
            facility_ids[name] = fac_id

        route_plan = [
            ("A동-B동 순환 셔틀", "A동 정문 셔틀장", "B동 후문 셔틀장"),
            ("B동-C동 순환 셔틀", "B동 후문 셔틀장", "C동 정문 셔틀장"),
            ("C동-식당동 순환 셔틀", "C동 정문 셔틀장", "식당동 셔틀 승하차장"),
            ("식당동-A동 순환 셔틀", "식당동 셔틀 승하차장", "A동 정문 셔틀장"),
        ]
        route_ids = {}
        for route_name, dep, arr in route_plan:
            rid = conn.execute(
                text(
                    "INSERT INTO shuttle_routes "
                    "(worksite_id, route_name, departure_facility_id, arrival_facility_id, "
                    " travel_minutes, waiting_minutes, operation_start, operation_end, interval_minutes) "
                    "VALUES (:w, :rn, :dep, :arr, 8, 3, '08:00', '19:00', 15) RETURNING id"
                ),
                {
                    "w": worksite_id,
                    "rn": route_name,
                    "dep": facility_ids[dep],
                    "arr": facility_ids[arr],
                },
            ).scalar()
            route_ids[route_name] = rid

        # Shuttle edges are one-way (the loop only runs in one direction).
        for route_name, dep, arr in route_plan:
            conn.execute(
                text(
                    "INSERT INTO move_edges "
                    "(worksite_id, from_node_type, from_node_id, to_node_type, to_node_id, "
                    " mode, minutes, bidirectional, shuttle_route_id) "
                    "VALUES (:w, 'facility', :f, 'facility', :t, 'shuttle', 11, :bd, :rid)"
                ),
                {
                    "w": worksite_id,
                    "f": facility_ids[dep],
                    "t": facility_ids[arr],
                    "bd": False,
                    "rid": route_ids[route_name],
                },
            )

        # One elevator edge per building, 1층 <-> the spec's named floor. Bidirectional.
        for building, top_floor in [("A동", "6층"), ("B동", "5층"), ("C동", "12층")]:
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
                "f": facility_ids["C동 출입카드 인증 위치"],
                "t": facility_ids["C동 정문 셔틀장"],
                "bd": True,
            },
        )

        # Additional worksites the admin can populate later (사업장 전환용, 아직 건물/시설 데이터 없음).
        for name, desc in [
            ("SK하이닉스 D&D (성남)", None),
            ("삼성전자 GA센터 (용인)", None),
            ("삼성전자 GA센터 (동탄)", None),
        ]:
            conn.execute(
                text("INSERT INTO worksites (name, description) VALUES (:n, :d)"),
                {"n": name, "d": desc},
            )

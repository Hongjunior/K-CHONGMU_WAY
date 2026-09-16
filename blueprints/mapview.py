from datetime import date as date_cls
from datetime import datetime, timedelta

from flask import Blueprint, abort, render_template, request, session
from sqlalchemy import text

from blueprints.auth import login_required, worksite_required
from blueprints.schedules import get_day_items
from constants import FACILITY_TYPE_LABELS
from db import engine
from routing import generate_timetable, next_shuttle_departure, travel_minutes_between_facilities

mapview_bp = Blueprint("mapview", __name__, url_prefix="/map")

# Landmarks that exist on the real, larger campus but are not part of the
# limited set of buildings Etners staff actually use — shown on the map for
# scale/realism only, never clickable and never tied to real building rows.
# (연구동/제2연구센터 used to be here too, but were promoted to real, selectable
# buildings in seed.py so the schedule facility picker has more choices — see
# seed.py's ensure_additional_buildings().)
DECORATIVE_LANDMARKS = [
    {"name": "본관", "pos_x": 8, "pos_y": 8},
    {"name": "복지동", "pos_x": 65, "pos_y": 88},
    {"name": "교육원", "pos_x": 50, "pos_y": 12},
    {"name": "주차타워", "pos_x": 92, "pos_y": 65},
]

# Extra polyline via-points (map display only, not travel-time data) so some
# shuttle routes visually bend through the decorative landmarks above instead
# of every route being a flat straight line.
ROUTE_VIA_POINTS = {
    "A동-C동 급행 셔틀": [(50, 14)],
}


def _shuttle_routes_by_departure_facility(conn, worksite_id):
    rows = conn.execute(
        text(
            "SELECT sr.*, fa.name AS arrival_name, fla.floor_label AS arrival_floor_label, "
            "ba.name AS arrival_building_name FROM shuttle_routes sr "
            "JOIN facilities fa ON fa.id = sr.arrival_facility_id "
            "JOIN floors fla ON fla.id = fa.floor_id "
            "JOIN buildings ba ON ba.id = fla.building_id "
            "WHERE sr.worksite_id = :w AND sr.active"
        ),
        {"w": worksite_id},
    ).mappings().all()

    by_facility = {}
    for r in rows:
        by_facility.setdefault(r["departure_facility_id"], []).append(
            {
                "route_name": r["route_name"],
                "arrival": f"{r['arrival_building_name']} {r['arrival_floor_label']} {r['arrival_name']}",
                "operation": f"{r['operation_start']}~{r['operation_end']}",
                "interval": r["interval_minutes"],
                "travel_minutes": r["travel_minutes"],
                "next_departure": next_shuttle_departure(
                    r["operation_start"], r["operation_end"], r["interval_minutes"]
                ),
            }
        )
    return by_facility


def _worksite_id():
    return session["current_worksite_id"]


@mapview_bp.route("/")
@login_required
@worksite_required
def overview():
    with engine.connect() as conn:
        worksite = conn.execute(
            text("SELECT * FROM worksites WHERE id = :id"), {"id": _worksite_id()}
        ).mappings().first()
        buildings = conn.execute(
            text("SELECT * FROM buildings WHERE worksite_id = :w ORDER BY name"),
            {"w": _worksite_id()},
        ).mappings().all()

        building_first_floor = {}
        for b in buildings:
            first_floor = conn.execute(
                text("SELECT id FROM floors WHERE building_id = :b ORDER BY floor_order LIMIT 1"),
                {"b": b["id"]},
            ).mappings().first()
            building_first_floor[b["id"]] = first_floor["id"] if first_floor else None

    return render_template(
        "map/overview.html",
        worksite=worksite,
        buildings=buildings,
        building_first_floor=building_first_floor,
        decorative_landmarks=DECORATIVE_LANDMARKS,
    )


@mapview_bp.route("/floor/<int:floor_id>")
@login_required
@worksite_required
def floor_view(floor_id):
    with engine.connect() as conn:
        floor = conn.execute(
            text(
                "SELECT fl.*, b.name AS building_name, b.id AS building_id FROM floors fl "
                "JOIN buildings b ON b.id = fl.building_id "
                "WHERE fl.id = :id AND b.worksite_id = :w"
            ),
            {"id": floor_id, "w": _worksite_id()},
        ).mappings().first()

        if not floor:
            abort(404)

        sibling_floors = conn.execute(
            text("SELECT * FROM floors WHERE building_id = :b ORDER BY floor_order"),
            {"b": floor["building_id"]},
        ).mappings().all()

        facilities = conn.execute(
            text("SELECT * FROM facilities WHERE floor_id = :f AND active ORDER BY name"),
            {"f": floor_id},
        ).mappings().all()

        shuttle_routes_by_facility = _shuttle_routes_by_departure_facility(conn, _worksite_id())

    highlight_id = request.args.get("facility", type=int)

    return render_template(
        "map/floor_view.html",
        floor=floor,
        sibling_floors=sibling_floors,
        facilities=facilities,
        highlight_id=highlight_id,
        type_labels=FACILITY_TYPE_LABELS,
        shuttle_routes_by_facility=shuttle_routes_by_facility,
    )


@mapview_bp.route("/shuttles")
@login_required
@worksite_required
def shuttles():
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT sr.*, "
                "fd.name AS departure_name, fld.floor_label AS departure_floor_label, "
                "bd.name AS departure_building_name, "
                "fa.name AS arrival_name, fla.floor_label AS arrival_floor_label, "
                "ba.name AS arrival_building_name "
                "FROM shuttle_routes sr "
                "JOIN facilities fd ON fd.id = sr.departure_facility_id "
                "JOIN floors fld ON fld.id = fd.floor_id JOIN buildings bd ON bd.id = fld.building_id "
                "JOIN facilities fa ON fa.id = sr.arrival_facility_id "
                "JOIN floors fla ON fla.id = fa.floor_id JOIN buildings ba ON ba.id = fla.building_id "
                "WHERE sr.worksite_id = :w AND sr.active ORDER BY sr.route_name"
            ),
            {"w": _worksite_id()},
        ).mappings().all()

    routes = []
    for r in rows:
        routes.append(
            {
                **dict(r),
                "departure_label": f"{r['departure_building_name']} {r['departure_floor_label']} {r['departure_name']}",
                "arrival_label": f"{r['arrival_building_name']} {r['arrival_floor_label']} {r['arrival_name']}",
                "next_departure": next_shuttle_departure(
                    r["operation_start"], r["operation_end"], r["interval_minutes"]
                ),
                "timetable": generate_timetable(
                    r["operation_start"], r["operation_end"], r["interval_minutes"]
                ),
            }
        )

    return render_template(
        "map/shuttles.html", routes=routes, now_str=datetime.now().strftime("%H:%M")
    )


@mapview_bp.route("/shuttle-map")
@login_required
@worksite_required
def shuttle_map():
    with engine.connect() as conn:
        buildings = conn.execute(
            text("SELECT * FROM buildings WHERE worksite_id = :w ORDER BY name"),
            {"w": _worksite_id()},
        ).mappings().all()

        rows = conn.execute(
            text(
                "SELECT sr.route_name, sr.travel_minutes, sr.waiting_minutes, sr.interval_minutes, "
                "sr.operation_start, sr.operation_end, "
                "bd.id AS dep_building_id, bd.name AS dep_building_name, "
                "bd.pos_x AS dep_x, bd.pos_y AS dep_y, "
                "ba.id AS arr_building_id, ba.name AS arr_building_name, "
                "ba.pos_x AS arr_x, ba.pos_y AS arr_y "
                "FROM shuttle_routes sr "
                "JOIN facilities fd ON fd.id = sr.departure_facility_id "
                "JOIN floors fld ON fld.id = fd.floor_id JOIN buildings bd ON bd.id = fld.building_id "
                "JOIN facilities fa ON fa.id = sr.arrival_facility_id "
                "JOIN floors fla ON fla.id = fa.floor_id JOIN buildings ba ON ba.id = fla.building_id "
                "WHERE sr.worksite_id = :w AND sr.active ORDER BY sr.route_name"
            ),
            {"w": _worksite_id()},
        ).mappings().all()

    palette = ["#FB8520", "#2f6feb", "#2e7d32", "#8e44ad", "#c0392b", "#00897b"]
    segments = []
    for i, r in enumerate(rows):
        via = ROUTE_VIA_POINTS.get(r["route_name"], [])
        points = [(r["dep_x"], r["dep_y"]), *via, (r["arr_x"], r["arr_y"])]
        segments.append(
            {
                "route_name": r["route_name"],
                "travel_minutes": r["travel_minutes"],
                "waiting_minutes": r["waiting_minutes"],
                "interval_minutes": r["interval_minutes"],
                "operation": f"{r['operation_start']}~{r['operation_end']}",
                "color": palette[i % len(palette)],
                "from_name": r["dep_building_name"],
                "to_name": r["arr_building_name"],
                "points": " ".join(f"{x},{y}" for x, y in points),
            }
        )

    return render_template(
        "map/shuttle_map.html",
        buildings=buildings,
        segments=segments,
        decorative_landmarks=DECORATIVE_LANDMARKS,
    )


def _facility_building(conn, facility_id):
    return conn.execute(
        text(
            "SELECT b.id, b.name, b.pos_x, b.pos_y FROM facilities fac "
            "JOIN floors fl ON fl.id = fac.floor_id "
            "JOIN buildings b ON b.id = fl.building_id "
            "WHERE fac.id = :id"
        ),
        {"id": facility_id},
    ).mappings().first()


def _shuttle_route_name_for(conn, worksite_id, dep_building_id, arr_building_id):
    return conn.execute(
        text(
            "SELECT sr.route_name FROM shuttle_routes sr "
            "JOIN facilities fd ON fd.id = sr.departure_facility_id "
            "JOIN floors fld ON fld.id = fd.floor_id "
            "JOIN facilities fa ON fa.id = sr.arrival_facility_id "
            "JOIN floors fla ON fla.id = fa.floor_id "
            "WHERE sr.worksite_id = :w AND sr.active "
            "AND fld.building_id = :dep AND fla.building_id = :arr "
            "LIMIT 1"
        ),
        {"w": worksite_id, "dep": dep_building_id, "arr": arr_building_id},
    ).scalar()


@mapview_bp.route("/day-route")
@login_required
@worksite_required
def day_route():
    try:
        cur_date = date_cls.fromisoformat(request.args.get("date") or "")
    except ValueError:
        cur_date = date_cls.today()
    date_str = cur_date.isoformat()

    with engine.connect() as conn:
        items = get_day_items(conn, session["user_id"], _worksite_id(), date_str)
        buildings = conn.execute(
            text("SELECT * FROM buildings WHERE worksite_id = :w ORDER BY name"),
            {"w": _worksite_id()},
        ).mappings().all()

        located = [it for it in items if it["schedule"]["facility_id"]]

        stops = []
        for idx, it in enumerate(located):
            b = _facility_building(conn, it["schedule"]["facility_id"])
            stops.append(
                {
                    "order": idx + 1,
                    "pos_x": b["pos_x"],
                    "pos_y": b["pos_y"],
                    "label": it["facility_label"] or b["name"],
                    "start_time": it["start_time"],
                }
            )

        palette = ["#FB8520", "#2f6feb", "#2e7d32", "#8e44ad", "#c0392b", "#00897b"]
        hops = []
        for i in range(len(located) - 1):
            a_item, b_item = located[i], located[i + 1]
            a_fac = a_item["schedule"]["facility_id"]
            b_fac = b_item["schedule"]["facility_id"]
            a_b = _facility_building(conn, a_fac)
            b_b = _facility_building(conn, b_fac)

            travel, path = travel_minutes_between_facilities(conn, _worksite_id(), a_fac, b_fac)
            is_shuttle = bool(path) and any(mode == "shuttle" for _n, mode, _m in path)
            same_building = a_b["id"] == b_b["id"]

            points = [(a_b["pos_x"], a_b["pos_y"])]
            if is_shuttle:
                route_name = _shuttle_route_name_for(conn, _worksite_id(), a_b["id"], b_b["id"])
                points.extend(ROUTE_VIA_POINTS.get(route_name, []))
            points.append((b_b["pos_x"], b_b["pos_y"]))

            hops.append(
                {
                    "order": i + 1,
                    "mode": "shuttle" if is_shuttle else ("same" if same_building else "walk"),
                    "color": palette[i % len(palette)],
                    "points": " ".join(f"{x},{y}" for x, y in points),
                    "travel_minutes": travel,
                    "from_label": a_item["facility_label"],
                    "to_label": b_item["facility_label"],
                }
            )

    return render_template(
        "map/day_route.html",
        buildings=buildings,
        decorative_landmarks=DECORATIVE_LANDMARKS,
        stops=stops,
        hops=hops,
        date_str=date_str,
        prev_date=(cur_date - timedelta(days=1)).isoformat(),
        next_date=(cur_date + timedelta(days=1)).isoformat(),
        today=date_cls.today().isoformat(),
    )


@mapview_bp.route("/search")
@login_required
@worksite_required
def search():
    q = request.args.get("q", "").strip()
    results = []
    if q:
        with engine.connect() as conn:
            results = conn.execute(
                text(
                    "SELECT fac.*, fl.floor_label, fl.id AS floor_id, b.name AS building_name FROM facilities fac "
                    "JOIN floors fl ON fl.id = fac.floor_id "
                    "JOIN buildings b ON b.id = fl.building_id "
                    "WHERE b.worksite_id = :w AND fac.active AND fac.name LIKE :q "
                    "ORDER BY b.name, fl.floor_order, fac.name"
                ),
                {"w": _worksite_id(), "q": f"%{q}%"},
            ).mappings().all()

    return render_template("map/search.html", q=q, results=results, type_labels=FACILITY_TYPE_LABELS)

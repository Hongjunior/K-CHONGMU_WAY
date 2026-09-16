from datetime import date as date_cls
from datetime import datetime, timedelta

from flask import Blueprint, abort, render_template, request, session
from sqlalchemy import text

from blueprints.auth import login_required, worksite_required
from blueprints.schedules import get_day_items
from constants import DECORATIVE_LANDMARKS, FACILITY_TYPE_LABELS
from db import engine
from routing import (
    build_day_route,
    elbow_points,
    generate_timetable,
    next_shuttle_departure,
)

mapview_bp = Blueprint("mapview", __name__, url_prefix="/map")


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
        points = elbow_points(r["dep_x"], r["dep_y"], r["arr_x"], r["arr_y"])
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
        stops, hops = build_day_route(conn, _worksite_id(), items)

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

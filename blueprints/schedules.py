from datetime import date as date_cls
from datetime import datetime, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import bindparam, text

from blueprints.auth import login_required, worksite_required
from constants import PRIORITIES, PRIORITY_LABELS, STATUS_LABELS, STATUSES
from db import IS_POSTGRES, engine
from routing import travel_minutes_between_facilities

schedules_bp = Blueprint("schedules", __name__, url_prefix="/schedules")

NOW_EXPR = "NOW()" if IS_POSTGRES else "(datetime('now', 'localtime'))"


def _worksite_id():
    return session["current_worksite_id"]


def _user_id():
    return session["user_id"]


def _facilities_for_current_worksite(conn):
    return conn.execute(
        text(
            "SELECT fac.*, fl.floor_label, b.name AS building_name FROM facilities fac "
            "JOIN floors fl ON fl.id = fac.floor_id "
            "JOIN buildings b ON b.id = fl.building_id "
            "WHERE b.worksite_id = :w AND fac.active ORDER BY b.name, fl.floor_order, fac.name"
        ),
        {"w": _worksite_id()},
    ).mappings().all()


def _worksite_map_for_picker(conn):
    """Nested building -> floor -> facilities structure (with shape data) for the
    interactive map-click location picker on the schedule form."""
    buildings = conn.execute(
        text("SELECT id, name FROM buildings WHERE worksite_id = :w ORDER BY name"),
        {"w": _worksite_id()},
    ).mappings().all()

    result = []
    for b in buildings:
        floors = conn.execute(
            text("SELECT id, floor_label FROM floors WHERE building_id = :b ORDER BY floor_order"),
            {"b": b["id"]},
        ).mappings().all()
        floor_list = []
        for f in floors:
            facs = conn.execute(
                text(
                    "SELECT id, name, facility_type, pos_x, pos_y, shape_w, shape_h "
                    "FROM facilities WHERE floor_id = :f AND active ORDER BY name"
                ),
                {"f": f["id"]},
            ).mappings().all()
            floor_list.append(
                {"id": f["id"], "label": f["floor_label"], "facilities": [dict(x) for x in facs]}
            )
        result.append({"id": b["id"], "name": b["name"], "floors": floor_list})
    return result


def _end_time_str(start_time, duration_minutes):
    if not duration_minutes:
        return None
    try:
        start_dt = datetime.strptime(start_time, "%H:%M")
    except (ValueError, TypeError):
        return None
    return (start_dt + timedelta(minutes=duration_minutes)).strftime("%H:%M")


def _safe_date(date_str):
    try:
        return date_cls.fromisoformat(date_str).isoformat()
    except (ValueError, TypeError):
        return date_cls.today().isoformat()


@schedules_bp.route("/")
@login_required
@worksite_required
def day_view():
    date_str = _safe_date(request.args.get("date") or date_cls.today().isoformat())

    with engine.connect() as conn:
        schedules = conn.execute(
            text(
                "SELECT * FROM schedules WHERE user_id = :u AND worksite_id = :w AND date = :d "
                "ORDER BY start_time"
            ),
            {"u": _user_id(), "w": _worksite_id(), "d": date_str},
        ).mappings().all()

        facility_labels = {}
        if schedules:
            fac_ids = {s["facility_id"] for s in schedules if s["facility_id"]}
            if fac_ids:
                stmt = text(
                    "SELECT fac.id, fac.name, fl.floor_label, b.name AS building_name FROM facilities fac "
                    "JOIN floors fl ON fl.id = fac.floor_id "
                    "JOIN buildings b ON b.id = fl.building_id "
                    "WHERE fac.id IN :ids"
                ).bindparams(bindparam("ids", expanding=True))
                rows = conn.execute(stmt, {"ids": list(fac_ids)}).mappings().all()
                for r in rows:
                    facility_labels[r["id"]] = f"{r['building_name']} {r['floor_label']} {r['name']}"

        items = []
        prev = None
        for sched in schedules:
            end_str = _end_time_str(sched["start_time"], sched["duration_minutes"])
            gap_minutes = None
            travel = None
            unreachable = False
            warning = False

            if prev is not None:
                prev_end = _end_time_str(prev["start_time"], prev["duration_minutes"]) or prev["start_time"]
                try:
                    prev_end_dt = datetime.strptime(prev_end, "%H:%M")
                    start_dt = datetime.strptime(sched["start_time"], "%H:%M")
                    gap_minutes = int((start_dt - prev_end_dt).total_seconds() // 60)
                except (ValueError, TypeError):
                    gap_minutes = None

                if prev["facility_id"] and sched["facility_id"]:
                    travel, _path = travel_minutes_between_facilities(
                        conn, _worksite_id(), prev["facility_id"], sched["facility_id"]
                    )
                    if travel is None:
                        unreachable = True
                    elif gap_minutes is not None and travel > gap_minutes:
                        warning = True

            items.append(
                {
                    "schedule": sched,
                    "facility_label": facility_labels.get(sched["facility_id"]),
                    "end_time": end_str,
                    "gap_minutes": gap_minutes,
                    "travel_minutes": travel,
                    "unreachable": unreachable,
                    "warning": warning,
                }
            )
            prev = sched

    cur_date = date_cls.fromisoformat(date_str)
    return render_template(
        "schedules/day_view.html",
        items=items,
        date_str=date_str,
        prev_date=(cur_date - timedelta(days=1)).isoformat(),
        next_date=(cur_date + timedelta(days=1)).isoformat(),
        status_labels=STATUS_LABELS,
        priority_labels=PRIORITY_LABELS,
        statuses=STATUSES,
        today=date_cls.today().isoformat(),
    )


@schedules_bp.route("/new", methods=["GET", "POST"])
@login_required
@worksite_required
def new_schedule():
    with engine.connect() as conn:
        facilities = _facilities_for_current_worksite(conn)
        worksite_map = _worksite_map_for_picker(conn)

    default_date = _safe_date(request.args.get("date") or date_cls.today().isoformat())

    if request.method == "POST":
        form = request.form
        title = form.get("title", "").strip()
        sched_date = form.get("date", "").strip()
        start_time = form.get("start_time", "").strip()
        duration = form.get("duration_minutes", type=int)
        facility_id = form.get("facility_id", type=int)
        work_type = form.get("work_type", "").strip() or None
        priority = form.get("priority", "normal")
        memo = form.get("memo", "").strip() or None

        valid_facility = facility_id is None or any(f["id"] == facility_id for f in facilities)
        if not title or not sched_date or not start_time or not valid_facility:
            flash("제목, 날짜, 시작시간을 올바르게 입력해주세요.", "error")
            return redirect(url_for("schedules.new_schedule", date=default_date))
        if priority not in PRIORITY_LABELS:
            priority = "normal"

        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO schedules "
                    "(user_id, worksite_id, title, date, start_time, duration_minutes, facility_id, "
                    " work_type, priority, memo) "
                    "VALUES (:u, :w, :t, :d, :st, :dur, :fac, :wt, :p, :m)"
                ),
                {
                    "u": _user_id(),
                    "w": _worksite_id(),
                    "t": title,
                    "d": sched_date,
                    "st": start_time,
                    "dur": duration,
                    "fac": facility_id,
                    "wt": work_type,
                    "p": priority,
                    "m": memo,
                },
            )
        flash("일정이 등록되었습니다.", "success")
        return redirect(url_for("schedules.day_view", date=sched_date))

    return render_template(
        "schedules/form.html",
        schedule=None,
        facilities=facilities,
        worksite_map=worksite_map,
        priorities=PRIORITIES,
        default_date=default_date,
    )


@schedules_bp.route("/<int:schedule_id>/edit", methods=["GET", "POST"])
@login_required
@worksite_required
def edit_schedule(schedule_id):
    with engine.connect() as conn:
        schedule = conn.execute(
            text("SELECT * FROM schedules WHERE id = :id AND user_id = :u AND worksite_id = :w"),
            {"id": schedule_id, "u": _user_id(), "w": _worksite_id()},
        ).mappings().first()
        facilities = _facilities_for_current_worksite(conn)
        worksite_map = _worksite_map_for_picker(conn)

    if not schedule:
        flash("일정을 찾을 수 없습니다.", "error")
        return redirect(url_for("schedules.day_view"))

    if request.method == "POST":
        form = request.form
        title = form.get("title", "").strip()
        sched_date = form.get("date", "").strip()
        start_time = form.get("start_time", "").strip()
        duration = form.get("duration_minutes", type=int)
        facility_id = form.get("facility_id", type=int)
        work_type = form.get("work_type", "").strip() or None
        priority = form.get("priority", "normal")
        memo = form.get("memo", "").strip() or None

        valid_facility = facility_id is None or any(f["id"] == facility_id for f in facilities)
        if not title or not sched_date or not start_time or not valid_facility:
            flash("제목, 날짜, 시작시간을 올바르게 입력해주세요.", "error")
            return redirect(url_for("schedules.edit_schedule", schedule_id=schedule_id))
        if priority not in PRIORITY_LABELS:
            priority = "normal"

        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE schedules SET title=:t, date=:d, start_time=:st, duration_minutes=:dur, "
                    f"facility_id=:fac, work_type=:wt, priority=:p, memo=:m, updated_at={NOW_EXPR} "
                    "WHERE id=:id AND user_id=:u"
                ),
                {
                    "t": title,
                    "d": sched_date,
                    "st": start_time,
                    "dur": duration,
                    "fac": facility_id,
                    "wt": work_type,
                    "p": priority,
                    "m": memo,
                    "id": schedule_id,
                    "u": _user_id(),
                },
            )
        flash("일정이 수정되었습니다.", "success")
        return redirect(url_for("schedules.day_view", date=sched_date))

    return render_template(
        "schedules/form.html",
        schedule=schedule,
        facilities=facilities,
        worksite_map=worksite_map,
        priorities=PRIORITIES,
        default_date=schedule["date"],
    )


@schedules_bp.route("/<int:schedule_id>/delete", methods=["POST"])
@login_required
@worksite_required
def delete_schedule(schedule_id):
    date_str = request.form.get("date") or date_cls.today().isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM schedules WHERE id = :id AND user_id = :u"),
            {"id": schedule_id, "u": _user_id()},
        )
    flash("일정이 삭제되었습니다.", "success")
    return redirect(url_for("schedules.day_view", date=date_str))


@schedules_bp.route("/<int:schedule_id>/status", methods=["POST"])
@login_required
@worksite_required
def update_status(schedule_id):
    new_status = request.form.get("status", "planned")
    date_str = request.form.get("date") or date_cls.today().isoformat()
    if new_status not in STATUS_LABELS:
        new_status = "planned"

    with engine.begin() as conn:
        conn.execute(
            text(
                f"UPDATE schedules SET status=:s, updated_at={NOW_EXPR} WHERE id=:id AND user_id=:u"
            ),
            {"s": new_status, "id": schedule_id, "u": _user_id()},
        )
    return redirect(url_for("schedules.day_view", date=date_str))


@schedules_bp.route("/api/upcoming")
@login_required
@worksite_required
def api_upcoming():
    """Today's not-done schedules for the reminder popup (static/reminder.js)."""
    today = date_cls.today().isoformat()

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT s.id, s.title, s.start_time, s.duration_minutes, "
                "fac.name AS facility_name, fl.floor_label, b.name AS building_name "
                "FROM schedules s "
                "LEFT JOIN facilities fac ON fac.id = s.facility_id "
                "LEFT JOIN floors fl ON fl.id = fac.floor_id "
                "LEFT JOIN buildings b ON b.id = fl.building_id "
                "WHERE s.user_id = :u AND s.worksite_id = :w AND s.date = :d "
                "AND s.status != 'done' AND s.status != 'on_hold' "
                "ORDER BY s.start_time"
            ),
            {"u": _user_id(), "w": _worksite_id(), "d": today},
        ).mappings().all()

    items = []
    for r in rows:
        location = None
        if r["facility_name"]:
            location = f"{r['building_name']} {r['floor_label']} {r['facility_name']}"
        items.append(
            {
                "id": r["id"],
                "title": r["title"],
                "start_time": r["start_time"],
                "duration_minutes": r["duration_minutes"],
                "location": location,
            }
        )

    return jsonify(items)

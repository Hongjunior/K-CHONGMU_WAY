from collections import Counter
from datetime import date as date_cls
from datetime import datetime, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import bindparam, text

from blueprints.auth import login_required, worksite_required
from constants import (
    DURATION_OPTIONS,
    PRIORITIES,
    PRIORITY_LABELS,
    SCHEDULE_CATEGORIES,
    SCHEDULE_CATEGORY_LABELS,
    STATUS_LABELS,
)
from db import IS_POSTGRES, engine
from routing import travel_minutes_between_facilities

schedules_bp = Blueprint("schedules", __name__, url_prefix="/schedules")

NOW_EXPR = "NOW()" if IS_POSTGRES else "(datetime('now', 'localtime'))"

# Fallback start-of-day used only to give a flexible ("시간없음") schedule item
# somewhere to land before the first fixed-time item of the day.
DAY_START = "08:00"


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


def _safe_date(date_str):
    try:
        return date_cls.fromisoformat(date_str).isoformat()
    except (ValueError, TypeError):
        return date_cls.today().isoformat()


def _parse_hhmm(value):
    try:
        return datetime.strptime(value, "%H:%M")
    except (ValueError, TypeError):
        return None


def _facility_labels_for(conn, schedules):
    facility_labels = {}
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
    return facility_labels


def _place_flexible_items(conn, worksite_id, fixed, flexible):
    """Merge fixed-time schedules with time-flexible ("시간없음") ones by
    greedily inserting each flexible item into the tightest-fitting gap of the
    day's timeline, based on travel time to/from its neighbours. Plain
    algorithm (Dijkstra + greedy best-fit) — no AI/LLM call, consistent with
    the rest of routing.py.

    Returns a start_dt-sorted list of {schedule, start_dt, end_dt, auto_placed}.
    """
    timeline = []
    for s in fixed:
        start_dt = _parse_hhmm(s["start_time"])
        if start_dt is None:
            continue
        end_dt = start_dt + timedelta(minutes=s["duration_minutes"] or 0)
        timeline.append({"schedule": s, "start_dt": start_dt, "end_dt": end_dt, "auto_placed": False})
    timeline.sort(key=lambda e: e["start_dt"])

    priority_rank = {"high": 0, "normal": 1, "low": 2}
    ordered_flexible = sorted(
        flexible, key=lambda s: (priority_rank.get(s["priority"], 1), s["id"])
    )

    day_start_dt = _parse_hhmm(DAY_START)

    for sched in ordered_flexible:
        duration = sched["duration_minutes"] or 0
        candidates = []  # (slack_minutes, insert_index, start_dt)

        for i in range(len(timeline) + 1):
            prev_entry = timeline[i - 1] if i > 0 else None
            next_entry = timeline[i] if i < len(timeline) else None

            gap_start = prev_entry["end_dt"] if prev_entry else day_start_dt
            gap_end = next_entry["start_dt"] if next_entry else None

            prev_facility = prev_entry["schedule"]["facility_id"] if prev_entry else None
            next_facility = next_entry["schedule"]["facility_id"] if next_entry else None

            travel_in = 0
            if prev_facility and sched["facility_id"]:
                travel_in, _ = travel_minutes_between_facilities(
                    conn, worksite_id, prev_facility, sched["facility_id"]
                )
            travel_out = 0
            if next_facility and sched["facility_id"]:
                travel_out, _ = travel_minutes_between_facilities(
                    conn, worksite_id, sched["facility_id"], next_facility
                )
            if travel_in is None or travel_out is None:
                continue  # no path exists between this gap's neighbours and here

            start_dt = gap_start + timedelta(minutes=travel_in)

            if gap_end is None:
                candidates.append((10**6, i, start_dt))  # open-ended fallback slot
            else:
                available = (gap_end - gap_start).total_seconds() / 60
                required = travel_in + duration + travel_out
                if required <= available:
                    candidates.append((available - required, i, start_dt))

        if candidates:
            candidates.sort(key=lambda c: c[0])
            _, insert_index, start_dt = candidates[0]
        else:
            # Every gap was unreachable — place it at the very end anyway so it
            # never silently disappears; the day view's travel warning will
            # flag it as unreachable from its neighbour.
            insert_index = len(timeline)
            start_dt = timeline[-1]["end_dt"] if timeline else day_start_dt

        end_dt = start_dt + timedelta(minutes=duration)
        timeline.insert(insert_index, {
            "schedule": sched, "start_dt": start_dt, "end_dt": end_dt, "auto_placed": True,
        })

    timeline.sort(key=lambda e: e["start_dt"])
    return timeline


def get_day_items(conn, user_id, worksite_id, date_str):
    """Ordered schedule items for one user/day, with time-flexible items
    auto-inserted into the tightest gap and per-pair travel/gap/warning info
    computed. Shared by the day view and the day-route map page."""
    schedules = conn.execute(
        text("SELECT * FROM schedules WHERE user_id = :u AND worksite_id = :w AND date = :d"),
        {"u": user_id, "w": worksite_id, "d": date_str},
    ).mappings().all()

    facility_labels = _facility_labels_for(conn, schedules)

    fixed = [s for s in schedules if s["start_time"]]
    flexible = [s for s in schedules if not s["start_time"]]
    timeline = _place_flexible_items(conn, worksite_id, fixed, flexible)

    items = []
    prev = None
    for entry in timeline:
        sched = entry["schedule"]
        gap_minutes = None
        travel = None
        unreachable = False
        warning = False

        if prev is not None:
            gap_minutes = int((entry["start_dt"] - prev["end_dt"]).total_seconds() // 60)
            if prev["schedule"]["facility_id"] and sched["facility_id"]:
                travel, _path = travel_minutes_between_facilities(
                    conn, worksite_id, prev["schedule"]["facility_id"], sched["facility_id"]
                )
                if travel is None:
                    unreachable = True
                elif travel > gap_minutes:
                    warning = True

        items.append(
            {
                "schedule": sched,
                "facility_label": facility_labels.get(sched["facility_id"]),
                "start_time": entry["start_dt"].strftime("%H:%M"),
                "end_time": entry["end_dt"].strftime("%H:%M") if sched["duration_minutes"] else None,
                "gap_minutes": gap_minutes,
                "travel_minutes": travel,
                "unreachable": unreachable,
                "warning": warning,
                "auto_placed": entry["auto_placed"],
            }
        )
        prev = entry

    return items


@schedules_bp.route("/")
@login_required
@worksite_required
def day_view():
    date_str = _safe_date(request.args.get("date") or date_cls.today().isoformat())
    category_filter = request.args.get("category")
    if category_filter not in SCHEDULE_CATEGORY_LABELS:
        category_filter = None

    with engine.connect() as conn:
        items = get_day_items(conn, _user_id(), _worksite_id(), date_str)

    category_counts = Counter((item["schedule"]["work_type"] or "etc") for item in items)

    if category_filter:
        items = [item for item in items if (item["schedule"]["work_type"] or "etc") == category_filter]

    cur_date = date_cls.fromisoformat(date_str)
    return render_template(
        "schedules/day_view.html",
        items=items,
        date_str=date_str,
        prev_date=(cur_date - timedelta(days=1)).isoformat(),
        next_date=(cur_date + timedelta(days=1)).isoformat(),
        status_labels=STATUS_LABELS,
        priority_labels=PRIORITY_LABELS,
        today=date_cls.today().isoformat(),
        categories=SCHEDULE_CATEGORIES,
        category_labels=SCHEDULE_CATEGORY_LABELS,
        category_counts=category_counts,
        category_filter=category_filter,
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
        category = form.get("category", "etc")
        if category not in SCHEDULE_CATEGORY_LABELS:
            category = "etc"
        sched_date = form.get("date", "").strip()
        no_fixed_time = bool(form.get("no_fixed_time"))
        start_time = "" if no_fixed_time else form.get("start_time", "").strip()
        duration = form.get("duration_minutes", type=int)
        facility_id = form.get("facility_id", type=int)
        priority = form.get("priority", "normal")
        memo = form.get("memo", "").strip() or None
        title = SCHEDULE_CATEGORY_LABELS[category]

        valid_facility = facility_id is None or any(f["id"] == facility_id for f in facilities)
        if not sched_date or (not no_fixed_time and not start_time) or not duration or not valid_facility:
            flash("날짜, 시작시간(또는 시간없음), 소요시간을 올바르게 입력해주세요.", "error")
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
                    "wt": category,
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
        categories=SCHEDULE_CATEGORIES,
        duration_options=DURATION_OPTIONS,
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
        category = form.get("category", "etc")
        if category not in SCHEDULE_CATEGORY_LABELS:
            category = "etc"
        sched_date = form.get("date", "").strip()
        no_fixed_time = bool(form.get("no_fixed_time"))
        start_time = "" if no_fixed_time else form.get("start_time", "").strip()
        duration = form.get("duration_minutes", type=int)
        facility_id = form.get("facility_id", type=int)
        priority = form.get("priority", "normal")
        memo = form.get("memo", "").strip() or None
        title = SCHEDULE_CATEGORY_LABELS[category]

        valid_facility = facility_id is None or any(f["id"] == facility_id for f in facilities)
        if not sched_date or (not no_fixed_time and not start_time) or not duration or not valid_facility:
            flash("날짜, 시작시간(또는 시간없음), 소요시간을 올바르게 입력해주세요.", "error")
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
                    "wt": category,
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
        categories=SCHEDULE_CATEGORIES,
        duration_options=DURATION_OPTIONS,
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


def unread_notification_count(conn, user_id):
    return conn.execute(
        text("SELECT COUNT(*) AS c FROM notifications WHERE user_id = :u AND read_at IS NULL"),
        {"u": user_id},
    ).mappings().first()["c"]


def _other_users(conn, exclude_user_id):
    return conn.execute(
        text("SELECT id, username FROM users WHERE id != :u ORDER BY username"),
        {"u": exclude_user_id},
    ).mappings().all()


@schedules_bp.route("/<int:schedule_id>/share", methods=["GET", "POST"])
@login_required
@worksite_required
def share_schedule(schedule_id):
    with engine.connect() as conn:
        schedule = conn.execute(
            text("SELECT * FROM schedules WHERE id = :id AND user_id = :u"),
            {"id": schedule_id, "u": _user_id()},
        ).mappings().first()
        if not schedule:
            flash("일정을 찾을 수 없습니다.", "error")
            return redirect(url_for("schedules.day_view"))
        users = _other_users(conn, _user_id())

    if request.method == "POST":
        to_user_id = request.form.get("to_user_id", type=int)
        if not any(u["id"] == to_user_id for u in users):
            flash("공유받을 사용자를 올바르게 선택해주세요.", "error")
            return redirect(url_for("schedules.share_schedule", schedule_id=schedule_id))

        with engine.begin() as conn:
            share_id = conn.execute(
                text(
                    "INSERT INTO schedule_shares "
                    "(schedule_id, from_user_id, to_user_id, worksite_id, status) "
                    "VALUES (:sid, :fu, :tu, :w, 'pending') RETURNING id"
                ),
                {"sid": schedule_id, "fu": _user_id(), "tu": to_user_id, "w": _worksite_id()},
            ).scalar()
            conn.execute(
                text(
                    "INSERT INTO notifications (user_id, type, message, related_share_id) "
                    "VALUES (:u, 'share', :m, :sid)"
                ),
                {
                    "u": to_user_id,
                    "m": f"{session['username']}님이 '{schedule['title']}' 일정을 공유했습니다.",
                    "sid": share_id,
                },
            )
        flash("일정을 공유했습니다.", "success")
        return redirect(url_for("schedules.day_view", date=schedule["date"]))

    return render_template("schedules/share_form.html", schedule=schedule, users=users)


@schedules_bp.route("/shares/<int:share_id>/accept", methods=["POST"])
@login_required
@worksite_required
def accept_share(share_id):
    with engine.begin() as conn:
        share = conn.execute(
            text("SELECT * FROM schedule_shares WHERE id = :id AND to_user_id = :u AND status = 'pending'"),
            {"id": share_id, "u": _user_id()},
        ).mappings().first()
        if not share:
            flash("이미 처리된 공유입니다.", "error")
            return redirect(url_for("schedules.notifications_list"))

        original = conn.execute(
            text("SELECT * FROM schedules WHERE id = :id"), {"id": share["schedule_id"]}
        ).mappings().first()
        if not original:
            conn.execute(
                text("UPDATE schedule_shares SET status='declined' WHERE id=:id"), {"id": share_id}
            )
            flash("원본 일정을 찾을 수 없습니다.", "error")
            return redirect(url_for("schedules.notifications_list"))

        duplicate = conn.execute(
            text(
                "SELECT id FROM schedules WHERE user_id = :u AND date = :d AND start_time = :st "
                "AND ((facility_id IS NULL AND :fac IS NULL) OR facility_id = :fac)"
            ),
            {
                "u": _user_id(),
                "d": original["date"],
                "st": original["start_time"],
                "fac": original["facility_id"],
            },
        ).mappings().first()

        if duplicate:
            conn.execute(
                text("UPDATE schedule_shares SET status='declined' WHERE id=:id"), {"id": share_id}
            )
            flash("이미 동일한 일정이 있습니다.", "error")
            return redirect(url_for("schedules.notifications_list"))

        conn.execute(
            text(
                "INSERT INTO schedules "
                "(user_id, worksite_id, title, date, start_time, duration_minutes, facility_id, "
                " work_type, priority, memo) "
                "VALUES (:u, :w, :t, :d, :st, :dur, :fac, :wt, :p, :m)"
            ),
            {
                "u": _user_id(),
                "w": share["worksite_id"],
                "t": original["title"],
                "d": original["date"],
                "st": original["start_time"],
                "dur": original["duration_minutes"],
                "fac": original["facility_id"],
                "wt": original["work_type"],
                "p": original["priority"],
                "m": original["memo"],
            },
        )
        conn.execute(text("UPDATE schedule_shares SET status='accepted' WHERE id=:id"), {"id": share_id})

    flash("공유받은 일정을 내 일정에 추가했습니다.", "success")
    return redirect(url_for("schedules.notifications_list"))


@schedules_bp.route("/shares/<int:share_id>/decline", methods=["POST"])
@login_required
@worksite_required
def decline_share(share_id):
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE schedule_shares SET status='declined' "
                "WHERE id=:id AND to_user_id=:u AND status='pending'"
            ),
            {"id": share_id, "u": _user_id()},
        )
    flash("공유를 삭제했습니다.", "success")
    return redirect(url_for("schedules.notifications_list"))


@schedules_bp.route("/notifications")
@login_required
def notifications_list():
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT n.*, ss.status AS share_status FROM notifications n "
                "LEFT JOIN schedule_shares ss ON ss.id = n.related_share_id "
                "WHERE n.user_id = :u ORDER BY n.created_at DESC, n.id DESC"
            ),
            {"u": _user_id()},
        ).mappings().all()

        notifications = [
            {**dict(r), "is_new": r["read_at"] is None} for r in rows
        ]

        unread_ids = [r["id"] for r in rows if r["read_at"] is None]
        if unread_ids:
            stmt = text(
                f"UPDATE notifications SET read_at={NOW_EXPR} WHERE id IN :ids"
            ).bindparams(bindparam("ids", expanding=True))
            conn.execute(stmt, {"ids": unread_ids})

    return render_template("schedules/notifications.html", notifications=notifications)


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

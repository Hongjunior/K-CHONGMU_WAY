from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from werkzeug.security import generate_password_hash

from blueprints.auth import admin_required, worksite_required
from constants import (
    EDGE_MODE_LABELS,
    EDGE_MODES,
    FACILITY_TYPE_LABELS,
    FACILITY_TYPES,
    ROLE_LABELS,
)
from db import engine

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

DELETE_BLOCKED_MSG = "연결된 하위 데이터가 있어 삭제할 수 없습니다. 하위 데이터를 먼저 삭제해주세요."


def _worksite_id():
    return session["current_worksite_id"]


def _run_delete(query, params, success_msg, redirect_endpoint, **redirect_kwargs):
    try:
        with engine.begin() as conn:
            conn.execute(text(query), params)
        flash(success_msg, "success")
    except IntegrityError:
        flash(DELETE_BLOCKED_MSG, "error")
    return redirect(url_for(redirect_endpoint, **redirect_kwargs))


@admin_bp.route("/")
@admin_required
def dashboard():
    worksite_name = None
    if session.get("current_worksite_id"):
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT name FROM worksites WHERE id = :id"),
                {"id": session["current_worksite_id"]},
            ).mappings().first()
            worksite_name = row["name"] if row else None
    return render_template("admin/dashboard.html", worksite_name=worksite_name)


# ---------- Users ----------

@admin_bp.route("/users")
@admin_required
def users_list():
    with engine.connect() as conn:
        users = conn.execute(
            text(
                "SELECT u.*, w.name AS worksite_name FROM users u "
                "LEFT JOIN worksites w ON w.id = u.current_worksite_id "
                "ORDER BY u.id"
            )
        ).mappings().all()
    return render_template("admin/users_list.html", users=users, role_labels=ROLE_LABELS)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@admin_required
def users_new():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "user")
        if role not in ROLE_LABELS:
            role = "user"

        if not username or not password:
            flash("아이디와 비밀번호를 입력해주세요.", "error")
            return redirect(url_for("admin.users_new"))

        with engine.begin() as conn:
            existing = conn.execute(
                text("SELECT id FROM users WHERE username = :u"), {"u": username}
            ).mappings().first()
            if existing:
                flash("이미 사용 중인 아이디입니다.", "error")
                return redirect(url_for("admin.users_new"))

            conn.execute(
                text("INSERT INTO users (username, password_hash, role) VALUES (:u, :p, :r)"),
                {"u": username, "p": generate_password_hash(password), "r": role},
            )

        flash("사용자가 추가되었습니다.", "success")
        return redirect(url_for("admin.users_list"))

    return render_template("admin/users_form.html", role_labels=ROLE_LABELS)


@admin_bp.route("/users/<int:user_id>/toggle-role", methods=["POST"])
@admin_required
def users_toggle_role(user_id):
    if user_id == session["user_id"]:
        flash("본인의 권한은 변경할 수 없습니다.", "error")
        return redirect(url_for("admin.users_list"))

    with engine.begin() as conn:
        user = conn.execute(
            text("SELECT role FROM users WHERE id = :id"), {"id": user_id}
        ).mappings().first()
        if not user:
            flash("사용자를 찾을 수 없습니다.", "error")
            return redirect(url_for("admin.users_list"))
        new_role = "admin" if user["role"] == "user" else "user"
        conn.execute(text("UPDATE users SET role = :r WHERE id = :id"), {"r": new_role, "id": user_id})

    flash("권한이 변경되었습니다.", "success")
    return redirect(url_for("admin.users_list"))


# ---------- Worksites (global, not scoped) ----------

@admin_bp.route("/worksites")
@admin_required
def worksites_list():
    with engine.connect() as conn:
        worksites = conn.execute(text("SELECT * FROM worksites ORDER BY id")).mappings().all()
    return render_template("admin/worksites_list.html", worksites=worksites)


@admin_bp.route("/worksites/new", methods=["GET", "POST"])
@admin_required
def worksites_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if not name:
            flash("사업장명을 입력해주세요.", "error")
            return redirect(url_for("admin.worksites_new"))
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO worksites (name, description) VALUES (:n, :d)"),
                {"n": name, "d": description},
            )
        flash("사업장이 등록되었습니다.", "success")
        return redirect(url_for("admin.worksites_list"))
    return render_template("admin/worksites_form.html", worksite=None)


@admin_bp.route("/worksites/<int:worksite_id>/edit", methods=["GET", "POST"])
@admin_required
def worksites_edit(worksite_id):
    with engine.connect() as conn:
        worksite = conn.execute(
            text("SELECT * FROM worksites WHERE id = :id"), {"id": worksite_id}
        ).mappings().first()
    if not worksite:
        flash("사업장을 찾을 수 없습니다.", "error")
        return redirect(url_for("admin.worksites_list"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        active = bool(request.form.get("active"))
        if not name:
            flash("사업장명을 입력해주세요.", "error")
            return redirect(url_for("admin.worksites_edit", worksite_id=worksite_id))
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE worksites SET name=:n, description=:d, active=:a WHERE id=:id"),
                {"n": name, "d": description, "a": active, "id": worksite_id},
            )
        flash("사업장 정보가 수정되었습니다.", "success")
        return redirect(url_for("admin.worksites_list"))

    return render_template("admin/worksites_form.html", worksite=worksite)


@admin_bp.route("/worksites/<int:worksite_id>/delete", methods=["POST"])
@admin_required
def worksites_delete(worksite_id):
    return _run_delete(
        "DELETE FROM worksites WHERE id = :id",
        {"id": worksite_id},
        "사업장이 삭제되었습니다.",
        "admin.worksites_list",
    )


# ---------- Buildings ----------

@admin_bp.route("/buildings")
@admin_required
@worksite_required
def buildings_list():
    with engine.connect() as conn:
        buildings = conn.execute(
            text("SELECT * FROM buildings WHERE worksite_id = :w ORDER BY name"),
            {"w": _worksite_id()},
        ).mappings().all()
    return render_template("admin/buildings_list.html", buildings=buildings)


@admin_bp.route("/buildings/new", methods=["GET", "POST"])
@admin_required
@worksite_required
def buildings_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        pos_x = request.form.get("pos_x", type=float)
        pos_y = request.form.get("pos_y", type=float)
        if not name:
            flash("건물명을 입력해주세요.", "error")
            return redirect(url_for("admin.buildings_new"))
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO buildings (worksite_id, name, pos_x, pos_y) VALUES (:w, :n, :x, :y)"),
                {"w": _worksite_id(), "n": name, "x": pos_x if pos_x is not None else 50, "y": pos_y if pos_y is not None else 50},
            )
        flash("건물이 등록되었습니다.", "success")
        return redirect(url_for("admin.buildings_list"))
    return render_template("admin/buildings_form.html", building=None)


@admin_bp.route("/buildings/<int:building_id>/edit", methods=["GET", "POST"])
@admin_required
@worksite_required
def buildings_edit(building_id):
    with engine.connect() as conn:
        building = conn.execute(
            text("SELECT * FROM buildings WHERE id = :id AND worksite_id = :w"),
            {"id": building_id, "w": _worksite_id()},
        ).mappings().first()
    if not building:
        flash("건물을 찾을 수 없습니다.", "error")
        return redirect(url_for("admin.buildings_list"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        pos_x = request.form.get("pos_x", type=float)
        pos_y = request.form.get("pos_y", type=float)
        if not name:
            flash("건물명을 입력해주세요.", "error")
            return redirect(url_for("admin.buildings_edit", building_id=building_id))
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE buildings SET name=:n, pos_x=:x, pos_y=:y WHERE id=:id AND worksite_id=:w"),
                {
                    "n": name,
                    "x": pos_x if pos_x is not None else 50,
                    "y": pos_y if pos_y is not None else 50,
                    "id": building_id,
                    "w": _worksite_id(),
                },
            )
        flash("건물 정보가 수정되었습니다.", "success")
        return redirect(url_for("admin.buildings_list"))

    return render_template("admin/buildings_form.html", building=building)


@admin_bp.route("/buildings/<int:building_id>/delete", methods=["POST"])
@admin_required
@worksite_required
def buildings_delete(building_id):
    return _run_delete(
        "DELETE FROM buildings WHERE id = :id AND worksite_id = :w",
        {"id": building_id, "w": _worksite_id()},
        "건물이 삭제되었습니다.",
        "admin.buildings_list",
    )


# ---------- Floors ----------

def _buildings_for_current_worksite(conn):
    return conn.execute(
        text("SELECT * FROM buildings WHERE worksite_id = :w ORDER BY name"),
        {"w": _worksite_id()},
    ).mappings().all()


@admin_bp.route("/floors")
@admin_required
@worksite_required
def floors_list():
    building_id = request.args.get("building_id", type=int)
    with engine.connect() as conn:
        buildings = _buildings_for_current_worksite(conn)

        query = (
            "SELECT f.*, b.name AS building_name FROM floors f "
            "JOIN buildings b ON b.id = f.building_id "
            "WHERE b.worksite_id = :w "
        )
        params = {"w": _worksite_id()}
        if building_id:
            query += "AND f.building_id = :b "
            params["b"] = building_id
        query += "ORDER BY b.name, f.floor_order"

        floors = conn.execute(text(query), params).mappings().all()

    return render_template(
        "admin/floors_list.html", floors=floors, buildings=buildings, selected_building_id=building_id
    )


@admin_bp.route("/floors/new", methods=["GET", "POST"])
@admin_required
@worksite_required
def floors_new():
    with engine.connect() as conn:
        buildings = _buildings_for_current_worksite(conn)

    if request.method == "POST":
        building_id = request.form.get("building_id", type=int)
        floor_label = request.form.get("floor_label", "").strip()
        floor_order = request.form.get("floor_order", type=int) or 0

        valid_building = any(b["id"] == building_id for b in buildings)
        if not floor_label or not valid_building:
            flash("건물과 층 이름을 올바르게 입력해주세요.", "error")
            return redirect(url_for("admin.floors_new"))

        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO floors (building_id, floor_label, floor_order) VALUES (:b, :l, :o)"),
                {"b": building_id, "l": floor_label, "o": floor_order},
            )
        flash("층이 등록되었습니다.", "success")
        return redirect(url_for("admin.floors_list"))

    return render_template("admin/floors_form.html", floor=None, buildings=buildings)


@admin_bp.route("/floors/<int:floor_id>/edit", methods=["GET", "POST"])
@admin_required
@worksite_required
def floors_edit(floor_id):
    with engine.connect() as conn:
        floor = conn.execute(
            text(
                "SELECT f.* FROM floors f JOIN buildings b ON b.id = f.building_id "
                "WHERE f.id = :id AND b.worksite_id = :w"
            ),
            {"id": floor_id, "w": _worksite_id()},
        ).mappings().first()
        buildings = _buildings_for_current_worksite(conn)

    if not floor:
        flash("층을 찾을 수 없습니다.", "error")
        return redirect(url_for("admin.floors_list"))

    if request.method == "POST":
        building_id = request.form.get("building_id", type=int)
        floor_label = request.form.get("floor_label", "").strip()
        floor_order = request.form.get("floor_order", type=int) or 0
        valid_building = any(b["id"] == building_id for b in buildings)
        if not floor_label or not valid_building:
            flash("건물과 층 이름을 올바르게 입력해주세요.", "error")
            return redirect(url_for("admin.floors_edit", floor_id=floor_id))

        with engine.begin() as conn:
            conn.execute(
                text("UPDATE floors SET building_id=:b, floor_label=:l, floor_order=:o WHERE id=:id"),
                {"b": building_id, "l": floor_label, "o": floor_order, "id": floor_id},
            )
        flash("층 정보가 수정되었습니다.", "success")
        return redirect(url_for("admin.floors_list"))

    return render_template("admin/floors_form.html", floor=floor, buildings=buildings)


@admin_bp.route("/floors/<int:floor_id>/delete", methods=["POST"])
@admin_required
@worksite_required
def floors_delete(floor_id):
    return _run_delete(
        "DELETE FROM floors WHERE id = :id AND building_id IN "
        "(SELECT id FROM buildings WHERE worksite_id = :w)",
        {"id": floor_id, "w": _worksite_id()},
        "층이 삭제되었습니다.",
        "admin.floors_list",
    )


# ---------- Facilities ----------

def _floors_for_current_worksite(conn):
    return conn.execute(
        text(
            "SELECT f.*, b.name AS building_name FROM floors f "
            "JOIN buildings b ON b.id = f.building_id "
            "WHERE b.worksite_id = :w ORDER BY b.name, f.floor_order"
        ),
        {"w": _worksite_id()},
    ).mappings().all()


@admin_bp.route("/facilities")
@admin_required
@worksite_required
def facilities_list():
    floor_id = request.args.get("floor_id", type=int)
    with engine.connect() as conn:
        floors = _floors_for_current_worksite(conn)

        query = (
            "SELECT fac.*, fl.floor_label, b.name AS building_name FROM facilities fac "
            "JOIN floors fl ON fl.id = fac.floor_id "
            "JOIN buildings b ON b.id = fl.building_id "
            "WHERE b.worksite_id = :w "
        )
        params = {"w": _worksite_id()}
        if floor_id:
            query += "AND fac.floor_id = :f "
            params["f"] = floor_id
        query += "ORDER BY b.name, fl.floor_order, fac.name"

        facilities = conn.execute(text(query), params).mappings().all()

    return render_template(
        "admin/facilities_list.html",
        facilities=facilities,
        floors=floors,
        selected_floor_id=floor_id,
        type_labels=FACILITY_TYPE_LABELS,
    )


@admin_bp.route("/facilities/new", methods=["GET", "POST"])
@admin_required
@worksite_required
def facilities_new():
    with engine.connect() as conn:
        floors = _floors_for_current_worksite(conn)

    if request.method == "POST":
        floor_id = request.form.get("floor_id", type=int)
        name = request.form.get("name", "").strip()
        facility_type = request.form.get("facility_type", "etc")
        description = request.form.get("description", "").strip()
        open_h = request.form.get("operating_hours_open", "").strip() or None
        close_h = request.form.get("operating_hours_close", "").strip() or None
        pos_x = request.form.get("pos_x", type=float)
        pos_y = request.form.get("pos_y", type=float)
        shape_w = request.form.get("shape_w", type=float)
        shape_h = request.form.get("shape_h", type=float)

        valid_floor = any(f["id"] == floor_id for f in floors)
        if not name or not valid_floor:
            flash("층과 시설명을 올바르게 입력해주세요.", "error")
            return redirect(url_for("admin.facilities_new"))
        if facility_type not in FACILITY_TYPE_LABELS:
            facility_type = "etc"

        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO facilities "
                    "(floor_id, name, facility_type, description, operating_hours_open, "
                    " operating_hours_close, pos_x, pos_y, shape_w, shape_h) "
                    "VALUES (:fl, :n, :t, :d, :oh, :ch, :x, :y, :sw, :sh)"
                ),
                {
                    "fl": floor_id,
                    "n": name,
                    "t": facility_type,
                    "d": description,
                    "oh": open_h,
                    "ch": close_h,
                    "x": pos_x if pos_x is not None else 50,
                    "y": pos_y if pos_y is not None else 50,
                    "sw": shape_w if shape_w is not None else 8,
                    "sh": shape_h if shape_h is not None else 6,
                },
            )
        flash("시설이 등록되었습니다.", "success")
        return redirect(url_for("admin.facilities_list"))

    return render_template(
        "admin/facilities_form.html", facility=None, floors=floors, facility_types=FACILITY_TYPES
    )


@admin_bp.route("/facilities/<int:facility_id>/edit", methods=["GET", "POST"])
@admin_required
@worksite_required
def facilities_edit(facility_id):
    with engine.connect() as conn:
        facility = conn.execute(
            text(
                "SELECT fac.* FROM facilities fac "
                "JOIN floors fl ON fl.id = fac.floor_id "
                "JOIN buildings b ON b.id = fl.building_id "
                "WHERE fac.id = :id AND b.worksite_id = :w"
            ),
            {"id": facility_id, "w": _worksite_id()},
        ).mappings().first()
        floors = _floors_for_current_worksite(conn)

    if not facility:
        flash("시설을 찾을 수 없습니다.", "error")
        return redirect(url_for("admin.facilities_list"))

    if request.method == "POST":
        floor_id = request.form.get("floor_id", type=int)
        name = request.form.get("name", "").strip()
        facility_type = request.form.get("facility_type", "etc")
        description = request.form.get("description", "").strip()
        open_h = request.form.get("operating_hours_open", "").strip() or None
        close_h = request.form.get("operating_hours_close", "").strip() or None
        pos_x = request.form.get("pos_x", type=float)
        pos_y = request.form.get("pos_y", type=float)
        shape_w = request.form.get("shape_w", type=float)
        shape_h = request.form.get("shape_h", type=float)
        active = bool(request.form.get("active"))

        valid_floor = any(f["id"] == floor_id for f in floors)
        if not name or not valid_floor:
            flash("층과 시설명을 올바르게 입력해주세요.", "error")
            return redirect(url_for("admin.facilities_edit", facility_id=facility_id))
        if facility_type not in FACILITY_TYPE_LABELS:
            facility_type = "etc"

        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE facilities SET floor_id=:fl, name=:n, facility_type=:t, description=:d, "
                    "operating_hours_open=:oh, operating_hours_close=:ch, pos_x=:x, pos_y=:y, "
                    "shape_w=:sw, shape_h=:sh, active=:a "
                    "WHERE id=:id"
                ),
                {
                    "fl": floor_id,
                    "n": name,
                    "t": facility_type,
                    "d": description,
                    "oh": open_h,
                    "ch": close_h,
                    "x": pos_x if pos_x is not None else 50,
                    "y": pos_y if pos_y is not None else 50,
                    "sw": shape_w if shape_w is not None else 8,
                    "sh": shape_h if shape_h is not None else 6,
                    "a": active,
                    "id": facility_id,
                },
            )
        flash("시설 정보가 수정되었습니다.", "success")
        return redirect(url_for("admin.facilities_list"))

    return render_template(
        "admin/facilities_form.html", facility=facility, floors=floors, facility_types=FACILITY_TYPES
    )


@admin_bp.route("/facilities/<int:facility_id>/delete", methods=["POST"])
@admin_required
@worksite_required
def facilities_delete(facility_id):
    return _run_delete(
        "DELETE FROM facilities WHERE id = :id AND floor_id IN "
        "(SELECT fl.id FROM floors fl JOIN buildings b ON b.id = fl.building_id WHERE b.worksite_id = :w)",
        {"id": facility_id, "w": _worksite_id()},
        "시설이 삭제되었습니다.",
        "admin.facilities_list",
    )


# ---------- Shuttle routes ----------

def _facilities_for_current_worksite(conn):
    return conn.execute(
        text(
            "SELECT fac.*, fl.floor_label, b.name AS building_name FROM facilities fac "
            "JOIN floors fl ON fl.id = fac.floor_id "
            "JOIN buildings b ON b.id = fl.building_id "
            "WHERE b.worksite_id = :w ORDER BY b.name, fl.floor_order, fac.name"
        ),
        {"w": _worksite_id()},
    ).mappings().all()


@admin_bp.route("/shuttle-routes")
@admin_required
@worksite_required
def shuttle_routes_list():
    with engine.connect() as conn:
        routes = conn.execute(
            text(
                "SELECT sr.*, fd.name AS departure_name, fa.name AS arrival_name FROM shuttle_routes sr "
                "JOIN facilities fd ON fd.id = sr.departure_facility_id "
                "JOIN facilities fa ON fa.id = sr.arrival_facility_id "
                "WHERE sr.worksite_id = :w ORDER BY sr.route_name"
            ),
            {"w": _worksite_id()},
        ).mappings().all()
    return render_template("admin/shuttle_routes_list.html", routes=routes)


@admin_bp.route("/shuttle-routes/new", methods=["GET", "POST"])
@admin_required
@worksite_required
def shuttle_routes_new():
    with engine.connect() as conn:
        facilities = _facilities_for_current_worksite(conn)

    if request.method == "POST":
        form = request.form
        dep_id = form.get("departure_facility_id", type=int)
        arr_id = form.get("arrival_facility_id", type=int)
        valid_ids = {f["id"] for f in facilities}

        route_name = form.get("route_name", "").strip()
        if not route_name or dep_id not in valid_ids or arr_id not in valid_ids:
            flash("노선명과 출발/도착 시설을 올바르게 입력해주세요.", "error")
            return redirect(url_for("admin.shuttle_routes_new"))

        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO shuttle_routes "
                    "(worksite_id, route_name, departure_facility_id, arrival_facility_id, "
                    " travel_minutes, waiting_minutes, operation_start, operation_end, interval_minutes) "
                    "VALUES (:w, :rn, :dep, :arr, :tm, :wm, :os, :oe, :im)"
                ),
                {
                    "w": _worksite_id(),
                    "rn": route_name,
                    "dep": dep_id,
                    "arr": arr_id,
                    "tm": form.get("travel_minutes", type=int) or 0,
                    "wm": form.get("waiting_minutes", type=int) or 0,
                    "os": form.get("operation_start") or "08:00",
                    "oe": form.get("operation_end") or "18:00",
                    "im": form.get("interval_minutes", type=int) or 15,
                },
            )
        flash("셔틀 노선이 등록되었습니다.", "success")
        return redirect(url_for("admin.shuttle_routes_list"))

    return render_template("admin/shuttle_routes_form.html", route=None, facilities=facilities)


@admin_bp.route("/shuttle-routes/<int:route_id>/edit", methods=["GET", "POST"])
@admin_required
@worksite_required
def shuttle_routes_edit(route_id):
    with engine.connect() as conn:
        route = conn.execute(
            text("SELECT * FROM shuttle_routes WHERE id = :id AND worksite_id = :w"),
            {"id": route_id, "w": _worksite_id()},
        ).mappings().first()
        facilities = _facilities_for_current_worksite(conn)

    if not route:
        flash("셔틀 노선을 찾을 수 없습니다.", "error")
        return redirect(url_for("admin.shuttle_routes_list"))

    if request.method == "POST":
        form = request.form
        dep_id = form.get("departure_facility_id", type=int)
        arr_id = form.get("arrival_facility_id", type=int)
        valid_ids = {f["id"] for f in facilities}
        route_name = form.get("route_name", "").strip()
        if not route_name or dep_id not in valid_ids or arr_id not in valid_ids:
            flash("노선명과 출발/도착 시설을 올바르게 입력해주세요.", "error")
            return redirect(url_for("admin.shuttle_routes_edit", route_id=route_id))

        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE shuttle_routes SET route_name=:rn, departure_facility_id=:dep, "
                    "arrival_facility_id=:arr, travel_minutes=:tm, waiting_minutes=:wm, "
                    "operation_start=:os, operation_end=:oe, interval_minutes=:im, active=:a "
                    "WHERE id=:id AND worksite_id=:w"
                ),
                {
                    "rn": route_name,
                    "dep": dep_id,
                    "arr": arr_id,
                    "tm": form.get("travel_minutes", type=int) or 0,
                    "wm": form.get("waiting_minutes", type=int) or 0,
                    "os": form.get("operation_start") or "08:00",
                    "oe": form.get("operation_end") or "18:00",
                    "im": form.get("interval_minutes", type=int) or 15,
                    "a": bool(form.get("active")),
                    "id": route_id,
                    "w": _worksite_id(),
                },
            )
        flash("셔틀 노선이 수정되었습니다.", "success")
        return redirect(url_for("admin.shuttle_routes_list"))

    return render_template("admin/shuttle_routes_form.html", route=route, facilities=facilities)


@admin_bp.route("/shuttle-routes/<int:route_id>/delete", methods=["POST"])
@admin_required
@worksite_required
def shuttle_routes_delete(route_id):
    return _run_delete(
        "DELETE FROM shuttle_routes WHERE id = :id AND worksite_id = :w",
        {"id": route_id, "w": _worksite_id()},
        "셔틀 노선이 삭제되었습니다.",
        "admin.shuttle_routes_list",
    )


# ---------- Move edges (polymorphic travel-time graph) ----------

def _nodes_for_current_worksite(conn):
    """All building/floor/facility nodes in the current worksite, tagged for the edge picker."""
    nodes = []
    for b in _buildings_for_current_worksite(conn):
        nodes.append({"type": "building", "id": b["id"], "label": f"[건물] {b['name']}"})
    for f in _floors_for_current_worksite(conn):
        nodes.append({"type": "floor", "id": f["id"], "label": f"[층] {f['building_name']} {f['floor_label']}"})
    for fac in _facilities_for_current_worksite(conn):
        nodes.append(
            {
                "type": "facility",
                "id": fac["id"],
                "label": f"[시설] {fac['building_name']} {fac['floor_label']} {fac['name']}",
            }
        )
    return nodes


def _node_label(conn, node_type, node_id):
    if node_type == "building":
        row = conn.execute(text("SELECT name FROM buildings WHERE id=:id"), {"id": node_id}).mappings().first()
        return f"[건물] {row['name']}" if row else "(삭제됨)"
    if node_type == "floor":
        row = conn.execute(
            text(
                "SELECT fl.floor_label, b.name AS building_name FROM floors fl "
                "JOIN buildings b ON b.id = fl.building_id WHERE fl.id = :id"
            ),
            {"id": node_id},
        ).mappings().first()
        return f"[층] {row['building_name']} {row['floor_label']}" if row else "(삭제됨)"
    if node_type == "facility":
        row = conn.execute(
            text(
                "SELECT fac.name, fl.floor_label, b.name AS building_name FROM facilities fac "
                "JOIN floors fl ON fl.id = fac.floor_id "
                "JOIN buildings b ON b.id = fl.building_id WHERE fac.id = :id"
            ),
            {"id": node_id},
        ).mappings().first()
        return f"[시설] {row['building_name']} {row['floor_label']} {row['name']}" if row else "(삭제됨)"
    return "(알수없음)"


@admin_bp.route("/move-edges")
@admin_required
@worksite_required
def move_edges_list():
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM move_edges WHERE worksite_id = :w ORDER BY id DESC"),
            {"w": _worksite_id()},
        ).mappings().all()
        edges = [
            {
                **dict(row),
                "from_label": _node_label(conn, row["from_node_type"], row["from_node_id"]),
                "to_label": _node_label(conn, row["to_node_type"], row["to_node_id"]),
            }
            for row in rows
        ]
    return render_template("admin/move_edges_list.html", edges=edges, mode_labels=EDGE_MODE_LABELS)


@admin_bp.route("/move-edges/new", methods=["GET", "POST"])
@admin_required
@worksite_required
def move_edges_new():
    with engine.connect() as conn:
        nodes = _nodes_for_current_worksite(conn)

    if request.method == "POST":
        form = request.form
        from_key = form.get("from_node", "")
        to_key = form.get("to_node", "")
        mode = form.get("mode", "walk")
        minutes = form.get("minutes", type=int)
        bidirectional = bool(form.get("bidirectional"))

        valid_keys = {f"{n['type']}:{n['id']}" for n in nodes}
        if from_key not in valid_keys or to_key not in valid_keys or mode not in EDGE_MODE_LABELS or not minutes:
            flash("출발/도착 지점, 이동수단, 소요시간을 올바르게 입력해주세요.", "error")
            return redirect(url_for("admin.move_edges_new"))

        from_type, from_id = from_key.split(":")
        to_type, to_id = to_key.split(":")

        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO move_edges "
                    "(worksite_id, from_node_type, from_node_id, to_node_type, to_node_id, mode, minutes, bidirectional) "
                    "VALUES (:w, :ft, :fi, :tt, :ti, :m, :min, :bd)"
                ),
                {
                    "w": _worksite_id(),
                    "ft": from_type,
                    "fi": int(from_id),
                    "tt": to_type,
                    "ti": int(to_id),
                    "m": mode,
                    "min": minutes,
                    "bd": bidirectional,
                },
            )
        flash("이동경로가 등록되었습니다.", "success")
        return redirect(url_for("admin.move_edges_list"))

    return render_template("admin/move_edges_form.html", edge=None, nodes=nodes, modes=EDGE_MODES)


@admin_bp.route("/move-edges/<int:edge_id>/edit", methods=["GET", "POST"])
@admin_required
@worksite_required
def move_edges_edit(edge_id):
    with engine.connect() as conn:
        edge = conn.execute(
            text("SELECT * FROM move_edges WHERE id = :id AND worksite_id = :w"),
            {"id": edge_id, "w": _worksite_id()},
        ).mappings().first()
        nodes = _nodes_for_current_worksite(conn)

    if not edge:
        flash("이동경로를 찾을 수 없습니다.", "error")
        return redirect(url_for("admin.move_edges_list"))

    if request.method == "POST":
        form = request.form
        from_key = form.get("from_node", "")
        to_key = form.get("to_node", "")
        mode = form.get("mode", "walk")
        minutes = form.get("minutes", type=int)
        bidirectional = bool(form.get("bidirectional"))
        active = bool(form.get("active"))

        valid_keys = {f"{n['type']}:{n['id']}" for n in nodes}
        if from_key not in valid_keys or to_key not in valid_keys or mode not in EDGE_MODE_LABELS or not minutes:
            flash("출발/도착 지점, 이동수단, 소요시간을 올바르게 입력해주세요.", "error")
            return redirect(url_for("admin.move_edges_edit", edge_id=edge_id))

        from_type, from_id = from_key.split(":")
        to_type, to_id = to_key.split(":")

        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE move_edges SET from_node_type=:ft, from_node_id=:fi, to_node_type=:tt, "
                    "to_node_id=:ti, mode=:m, minutes=:min, bidirectional=:bd, active=:a "
                    "WHERE id=:id AND worksite_id=:w"
                ),
                {
                    "ft": from_type,
                    "fi": int(from_id),
                    "tt": to_type,
                    "ti": int(to_id),
                    "m": mode,
                    "min": minutes,
                    "bd": bidirectional,
                    "a": active,
                    "id": edge_id,
                    "w": _worksite_id(),
                },
            )
        flash("이동경로가 수정되었습니다.", "success")
        return redirect(url_for("admin.move_edges_list"))

    current_from = f"{edge['from_node_type']}:{edge['from_node_id']}"
    current_to = f"{edge['to_node_type']}:{edge['to_node_id']}"
    return render_template(
        "admin/move_edges_form.html",
        edge=edge,
        nodes=nodes,
        modes=EDGE_MODES,
        current_from=current_from,
        current_to=current_to,
    )


@admin_bp.route("/move-edges/<int:edge_id>/delete", methods=["POST"])
@admin_required
@worksite_required
def move_edges_delete(edge_id):
    return _run_delete(
        "DELETE FROM move_edges WHERE id = :id AND worksite_id = :w",
        {"id": edge_id, "w": _worksite_id()},
        "이동경로가 삭제되었습니다.",
        "admin.move_edges_list",
    )

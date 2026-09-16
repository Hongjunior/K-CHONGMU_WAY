from collections import Counter
from datetime import date as date_cls

from flask import Flask, session
from sqlalchemy import text

from db import engine, init_db
from seed import (
    ensure_additional_buildings,
    ensure_additional_demo_routes,
    ensure_cross_building_walk_edge,
    fix_facility_names,
    fix_worksite_names,
    seed_demo_data,
)

app = Flask(__name__)
app.secret_key = "kchongmu-way-secret-key"

from blueprints.auth import auth_bp
from blueprints.worksites import worksites_bp
from blueprints.admin import admin_bp
from blueprints.mapview import mapview_bp
from blueprints.schedules import get_day_items, schedules_bp, unread_notification_count
from constants import SCHEDULE_CATEGORIES

app.register_blueprint(auth_bp)
app.register_blueprint(worksites_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(mapview_bp)
app.register_blueprint(schedules_bp)


@app.context_processor
def inject_header_status():
    if not session.get("user_id") or not session.get("current_worksite_id"):
        return {}

    today = date_cls.today().isoformat()
    with engine.connect() as conn:
        items = get_day_items(conn, session["user_id"], session["current_worksite_id"], today)
        worksite = conn.execute(
            text("SELECT name FROM worksites WHERE id = :id"),
            {"id": session["current_worksite_id"]},
        ).mappings().first()
        unread_count = unread_notification_count(conn, session["user_id"])

    category_counts = Counter((it["schedule"]["work_type"] or "etc") for it in items)
    done_count = sum(1 for it in items if it["schedule"]["status"] == "done")

    return {
        "header_today": today,
        "header_worksite_name": worksite["name"] if worksite else None,
        "header_categories": SCHEDULE_CATEGORIES,
        "header_category_counts": category_counts,
        "header_done_count": done_count,
        "header_has_schedules": bool(items),
        "header_unread_count": unread_count,
    }


@app.route("/")
def root():
    from flask import redirect, session, url_for

    if not session.get("user_id"):
        return redirect(url_for("auth.login"))
    if not session.get("current_worksite_id"):
        return redirect(url_for("worksites.select_worksite"))
    return redirect(url_for("schedules.day_view"))


init_db()
seed_demo_data(engine)
fix_facility_names(engine)
fix_worksite_names(engine)
ensure_additional_demo_routes(engine)
ensure_additional_buildings(engine)
ensure_cross_building_walk_edge(engine)

if __name__ == "__main__":
    app.run(debug=True)

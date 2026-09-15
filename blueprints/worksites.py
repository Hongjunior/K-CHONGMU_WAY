from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import text

from blueprints.auth import login_required
from db import engine

worksites_bp = Blueprint("worksites", __name__, url_prefix="/worksites")


@worksites_bp.route("/select", methods=["GET", "POST"])
@login_required
def select_worksite():
    if request.method == "POST":
        worksite_id = request.form.get("worksite_id", type=int)

        with engine.begin() as conn:
            valid = conn.execute(
                text("SELECT id, name FROM worksites WHERE id = :id AND active"),
                {"id": worksite_id},
            ).mappings().first()
            if not valid:
                flash("유효하지 않은 사업장입니다.", "error")
                return redirect(url_for("worksites.select_worksite"))

            conn.execute(
                text("UPDATE users SET current_worksite_id = :w WHERE id = :uid"),
                {"w": worksite_id, "uid": session["user_id"]},
            )

        session["current_worksite_id"] = worksite_id
        flash(f"'{valid['name']}' 사업장을 선택했습니다.", "success")
        return redirect(url_for("mapview.overview"))

    with engine.connect() as conn:
        worksites = conn.execute(
            text("SELECT * FROM worksites WHERE active ORDER BY name")
        ).mappings().all()

    return render_template(
        "worksites/select.html",
        worksites=worksites,
        current_id=session.get("current_worksite_id"),
    )

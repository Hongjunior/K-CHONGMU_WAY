from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash

from db import engine

auth_bp = Blueprint("auth", __name__)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login", next=request.path))
        if session.get("role") != "admin":
            flash("관리자만 접근할 수 있습니다.", "error")
            return redirect(url_for("mapview.overview"))
        return view(*args, **kwargs)

    return wrapped


def worksite_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("current_worksite_id"):
            return redirect(url_for("worksites.select_worksite"))
        return view(*args, **kwargs)

    return wrapped


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        department = request.form.get("department", "").strip() or None
        job_title = request.form.get("job_title", "").strip() or None
        display_name = request.form.get("display_name", "").strip() or None

        if not username or not password:
            flash("아이디와 비밀번호를 입력해주세요.", "error")
            return redirect(url_for("auth.register"))
        if password != confirm:
            flash("비밀번호가 일치하지 않습니다.", "error")
            return redirect(url_for("auth.register"))

        with engine.begin() as conn:
            existing = conn.execute(
                text("SELECT id FROM users WHERE username = :u"), {"u": username}
            ).mappings().first()
            if existing:
                flash("이미 사용 중인 아이디입니다.", "error")
                return redirect(url_for("auth.register"))

            # Self-registration always creates a regular user account.
            # Admin accounts are granted by an existing admin via /admin/users.
            conn.execute(
                text(
                    "INSERT INTO users (username, password_hash, role, department, job_title, display_name) "
                    "VALUES (:u, :p, 'user', :d, :j, :n)"
                ),
                {
                    "u": username,
                    "p": generate_password_hash(password),
                    "d": department,
                    "j": job_title,
                    "n": display_name,
                },
            )

        flash("회원가입이 완료되었습니다. 로그인해주세요.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        with engine.connect() as conn:
            user = conn.execute(
                text("SELECT * FROM users WHERE username = :u"), {"u": username}
            ).mappings().first()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("아이디 또는 비밀번호가 올바르지 않습니다.", "error")
            return redirect(url_for("auth.login"))

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        session["department"] = user["department"]
        session["job_title"] = user["job_title"]
        session["display_name"] = user["display_name"]
        session["current_worksite_id"] = user["current_worksite_id"]

        flash(f"{user['username']}님, 환영합니다.", "success")
        return redirect(request.args.get("next") or url_for("root"))

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("로그아웃되었습니다.", "success")
    return redirect(url_for("auth.login"))

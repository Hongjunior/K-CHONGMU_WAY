from flask import Flask

from db import engine, init_db
from seed import seed_demo_data

app = Flask(__name__)
app.secret_key = "kchongmu-way-secret-key"

from blueprints.auth import auth_bp
from blueprints.worksites import worksites_bp
from blueprints.admin import admin_bp
from blueprints.mapview import mapview_bp
from blueprints.schedules import schedules_bp

app.register_blueprint(auth_bp)
app.register_blueprint(worksites_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(mapview_bp)
app.register_blueprint(schedules_bp)


@app.route("/")
def root():
    from flask import redirect, session, url_for

    if not session.get("user_id"):
        return redirect(url_for("auth.login"))
    if not session.get("current_worksite_id"):
        return redirect(url_for("worksites.select_worksite"))
    return redirect(url_for("mapview.overview"))


init_db()
seed_demo_data(engine)

if __name__ == "__main__":
    app.run(debug=True)

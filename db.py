import os

from sqlalchemy import create_engine, event, text

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    db_path = "/tmp/kchongmu.db" if os.environ.get("VERCEL") else "kchongmu.db"
    engine = create_engine(f"sqlite:///{db_path}")

IS_POSTGRES = engine.url.get_backend_name() == "postgresql"

if not IS_POSTGRES:
    # SQLite does not enforce foreign keys by default; turn it on per-connection so
    # local dev behaves the same as Postgres in production (e.g. deleting a floor
    # that still has facilities raises an IntegrityError on both, instead of
    # silently orphaning rows locally).
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

PK = "id SERIAL PRIMARY KEY" if IS_POSTGRES else "id INTEGER PRIMARY KEY AUTOINCREMENT"
TS = (
    "TIMESTAMP NOT NULL DEFAULT NOW()"
    if IS_POSTGRES
    else "TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))"
)
ACTIVE_TRUE = "BOOLEAN NOT NULL DEFAULT TRUE" if IS_POSTGRES else "INTEGER NOT NULL DEFAULT 1"
BOOL_TRUE = ACTIVE_TRUE  # alias, same column definition used for any boolean-flag column
JSON_TYPE = "JSONB" if IS_POSTGRES else "TEXT"


def init_db():
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS worksites (
                {PK},
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                active {ACTIVE_TRUE},
                created_at {TS}
            )
        """))

        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS users (
                {PK},
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                current_worksite_id INTEGER REFERENCES worksites(id),
                created_at {TS}
            )
        """))

        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS buildings (
                {PK},
                worksite_id INTEGER NOT NULL REFERENCES worksites(id),
                name TEXT NOT NULL,
                pos_x REAL NOT NULL DEFAULT 50,
                pos_y REAL NOT NULL DEFAULT 50,
                created_at {TS},
                UNIQUE(worksite_id, name)
            )
        """))

        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS floors (
                {PK},
                building_id INTEGER NOT NULL REFERENCES buildings(id),
                floor_label TEXT NOT NULL,
                floor_order INTEGER NOT NULL DEFAULT 0,
                created_at {TS},
                UNIQUE(building_id, floor_label)
            )
        """))

        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS facilities (
                {PK},
                floor_id INTEGER NOT NULL REFERENCES floors(id),
                name TEXT NOT NULL,
                facility_type TEXT NOT NULL,
                description TEXT,
                operating_hours_open TEXT,
                operating_hours_close TEXT,
                pos_x REAL NOT NULL DEFAULT 50,
                pos_y REAL NOT NULL DEFAULT 50,
                shape_w REAL NOT NULL DEFAULT 8,
                shape_h REAL NOT NULL DEFAULT 6,
                active {BOOL_TRUE},
                created_at {TS},
                UNIQUE(floor_id, name)
            )
        """))

        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS shuttle_routes (
                {PK},
                worksite_id INTEGER NOT NULL REFERENCES worksites(id),
                route_name TEXT NOT NULL,
                departure_facility_id INTEGER NOT NULL REFERENCES facilities(id),
                arrival_facility_id INTEGER NOT NULL REFERENCES facilities(id),
                travel_minutes INTEGER NOT NULL,
                waiting_minutes INTEGER NOT NULL DEFAULT 0,
                operation_start TEXT NOT NULL,
                operation_end TEXT NOT NULL,
                interval_minutes INTEGER NOT NULL,
                active {BOOL_TRUE},
                created_at {TS}
            )
        """))

        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS move_edges (
                {PK},
                worksite_id INTEGER NOT NULL REFERENCES worksites(id),
                from_node_type TEXT NOT NULL,
                from_node_id INTEGER NOT NULL,
                to_node_type TEXT NOT NULL,
                to_node_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                minutes INTEGER NOT NULL,
                bidirectional {BOOL_TRUE},
                shuttle_route_id INTEGER REFERENCES shuttle_routes(id),
                active {BOOL_TRUE},
                created_at {TS}
            )
        """))

        # Phase 2
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS schedules (
                {PK},
                user_id INTEGER NOT NULL REFERENCES users(id),
                worksite_id INTEGER NOT NULL REFERENCES worksites(id),
                title TEXT NOT NULL,
                date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_minutes INTEGER,
                facility_id INTEGER REFERENCES facilities(id),
                building_id INTEGER REFERENCES buildings(id),
                floor_id INTEGER REFERENCES floors(id),
                work_type TEXT,
                priority TEXT NOT NULL DEFAULT 'normal',
                status TEXT NOT NULL DEFAULT 'planned',
                memo TEXT,
                created_at {TS},
                updated_at {TS}
            )
        """))

        # Phase 3
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS recommendation_logs (
                {PK},
                user_id INTEGER NOT NULL REFERENCES users(id),
                worksite_id INTEGER NOT NULL REFERENCES worksites(id),
                date TEXT NOT NULL,
                input_snapshot {JSON_TYPE},
                plan_a {JSON_TYPE},
                plan_b {JSON_TYPE},
                chosen_plan TEXT,
                created_at {TS}
            )
        """))

        # Phase 4
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS notices (
                {PK},
                worksite_id INTEGER NOT NULL REFERENCES worksites(id),
                title TEXT NOT NULL,
                body TEXT,
                raw_admin_text TEXT,
                ai_extracted_change {JSON_TYPE},
                affected_building_id INTEGER REFERENCES buildings(id),
                affected_floor_id INTEGER REFERENCES floors(id),
                affected_facility_id INTEGER REFERENCES facilities(id),
                affected_route_id INTEGER REFERENCES shuttle_routes(id),
                effective_start TEXT,
                effective_end TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                created_by INTEGER REFERENCES users(id),
                created_at {TS}
            )
        """))

        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS notice_impacts (
                {PK},
                notice_id INTEGER NOT NULL REFERENCES notices(id),
                schedule_id INTEGER NOT NULL REFERENCES schedules(id),
                impact_description TEXT,
                delay_minutes_estimate INTEGER,
                created_at {TS}
            )
        """))

        for stmt in [
            "CREATE INDEX IF NOT EXISTS idx_buildings_worksite ON buildings(worksite_id)",
            "CREATE INDEX IF NOT EXISTS idx_floors_building ON floors(building_id)",
            "CREATE INDEX IF NOT EXISTS idx_facilities_floor ON facilities(floor_id)",
            "CREATE INDEX IF NOT EXISTS idx_move_edges_worksite ON move_edges(worksite_id)",
            "CREATE INDEX IF NOT EXISTS idx_shuttle_routes_worksite ON shuttle_routes(worksite_id)",
            "CREATE INDEX IF NOT EXISTS idx_schedules_user_date ON schedules(user_id, date)",
            "CREATE INDEX IF NOT EXISTS idx_notices_worksite ON notices(worksite_id)",
        ]:
            conn.execute(text(stmt))

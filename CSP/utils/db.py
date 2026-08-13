"""
Database Utility Module
=======================
Handles database initialization, connection, and schema creation
for the Smart Career Navigator application (PostgreSQL).
"""

import os
import time
import threading
import psycopg2
import psycopg2.extras
import psycopg2.pool
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

_CONNECT_KWARGS = dict(
    # Neon (and most managed Postgres providers) will silently drop idle
    # connections after a period of inactivity, especially on serverless
    # / free tiers. These keepalive settings make the OS notice a dead
    # socket quickly instead of a query hanging or failing confusingly.
    keepalives=1,
    keepalives_idle=30,
    keepalives_interval=10,
    keepalives_count=3,
)


class _RealDictConnection(psycopg2.extensions.connection):
    """Connection subclass that returns RealDictCursor by default."""
    def cursor(self, *args, **kwargs):
        kwargs.setdefault('cursor_factory', psycopg2.extras.RealDictCursor)
        return super().cursor(*args, **kwargs)


# ── Connection pooling ──────────────────────────────────────────
# Opening a brand-new TCP/TLS connection to a remote Postgres instance
# (e.g. Neon) on every get_db() call is expensive and was the main
# cause of slow page loads, since a single request can call get_db()
# many times (auth check, rate limiting, the view itself, notification
# lookups, etc). A pool keeps a small set of real connections open and
# hands them out on demand, which is dramatically faster.
_pool = None

# How long we trust a pooled connection without re-verifying it with a
# round trip. Testing every single connection on every single get_db()
# call (several per request) was correct but made every page noticeably
# slower, since each test is an extra network round trip to Neon. Instead,
# we remember when each connection was last confirmed alive and only pay
# for a fresh check once that memory goes stale -- keeping the common case
# fast while still catching connections Neon has dropped in the meantime.
_HEALTH_CHECK_INTERVAL_SECONDS = 20
_last_verified = {}
_last_verified_lock = threading.Lock()


def _get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            dsn=DATABASE_URL,
            connection_factory=_RealDictConnection,
            **_CONNECT_KWARGS,
        )
    return _pool


def _is_connection_alive(conn):
    """Run a trivial query to verify a pooled connection is still usable."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        # SELECT 1 leaves an open transaction behind (new connections
        # default to autocommit=False) -- clear it so callers are free to
        # flip .autocommit afterward without psycopg2 rejecting the change.
        conn.rollback()
        return True
    except Exception:
        return False


def _recently_verified(conn):
    with _last_verified_lock:
        ts = _last_verified.get(id(conn))
    return ts is not None and (time.time() - ts) < _HEALTH_CHECK_INTERVAL_SECONDS


def _mark_verified(conn):
    with _last_verified_lock:
        _last_verified[id(conn)] = time.time()


def _forget_verified(conn):
    with _last_verified_lock:
        _last_verified.pop(id(conn), None)


class _RetryingCursor:
    """
    Thin wrapper around a real psycopg2 cursor that transparently
    reconnects and retries once if the underlying connection turns out to
    be dead (e.g. "SSL connection has been closed unexpectedly"). This
    protects against the rare case where a connection dies *during* a
    request rather than while it was sitting idle in the pool, without
    every route having to add its own retry logic.
    """

    def __init__(self, pooled_conn):
        self._pooled_conn = pooled_conn
        self._cursor = pooled_conn._conn.cursor()

    def execute(self, query, vars=None):
        try:
            return self._cursor.execute(query, vars)
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            self._pooled_conn._reconnect()
            self._cursor = self._pooled_conn._conn.cursor()
            return self._cursor.execute(query, vars)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        try:
            self._cursor.close()
        except Exception:
            pass
        return False

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _PooledConnection:
    """
    Thin wrapper around a pooled psycopg2 connection.

    Existing code throughout the app calls conn.close() when it's done.
    Here, close() returns the connection to the pool instead of actually
    closing the underlying socket, so no other file needs to change.
    """

    def __init__(self, pool):
        self._pool = pool
        self._closed = False
        self._conn = None
        self._from_pool = False
        self._acquire()

    def _acquire(self):
        """Get a real connection, trusting recently-verified ones as-is."""
        pool = self._pool
        conn = None
        for _ in range(pool.maxconn):
            try:
                candidate = pool.getconn()
            except psycopg2.pool.PoolError:
                # Pool is fully checked out (e.g. leaked connections from
                # earlier crashed requests piled up). Stop trying the pool
                # and fall through to the direct-connection fallback below
                # instead of raising and failing the whole request.
                break
            try:
                candidate.rollback()  # clear any leftover transaction state
            except Exception:
                pass

            if _recently_verified(candidate):
                conn = candidate
                break

            if _is_connection_alive(candidate):
                _mark_verified(candidate)
                conn = candidate
                break

            _forget_verified(candidate)
            try:
                pool.putconn(candidate, close=True)
            except Exception:
                pass

        self._from_pool = conn is not None
        if conn is None:
            # Every pooled connection was stale (or the pool is misbehaving)
            # -- open a brand-new direct connection as a last resort so the
            # request can still succeed instead of hard-failing. This one
            # isn't tracked by the pool, so it must be closed directly
            # rather than returned via putconn() (see close() below).
            conn = psycopg2.connect(
                DATABASE_URL,
                connection_factory=_RealDictConnection,
                **_CONNECT_KWARGS,
            )

        self._conn = conn

    def _reconnect(self):
        """
        Called by _RetryingCursor when a query fails mid-request because
        the connection died. Discards the dead connection and acquires a
        fresh one, preserving the same autocommit setting the caller
        already had.
        """
        autocommit = False
        try:
            autocommit = self._conn.autocommit
        except Exception:
            pass

        old_conn, old_from_pool = self._conn, self._from_pool
        _forget_verified(old_conn)
        try:
            if old_from_pool:
                self._pool.putconn(old_conn, close=True)
            else:
                old_conn.close()
        except Exception:
            pass

        self._acquire()
        try:
            self._conn.autocommit = autocommit
        except Exception:
            pass

    def cursor(self, *args, **kwargs):
        return _RetryingCursor(self)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        """Return the connection to the pool instead of closing it."""
        if self._closed:
            return
        self._closed = True

        if not self._from_pool:
            # This connection was opened directly (fallback path, not
            # tracked by the pool) -- close it for real instead of trying
            # to hand it back to a pool that never dispensed it.
            try:
                self._conn.close()
            except Exception:
                pass
            return

        try:
            # Discard any uncommitted work before the connection is reused.
            # This is a no-op if everything was already committed.
            self._conn.rollback()
        except Exception:
            # If the underlying connection is broken, drop it from the
            # pool entirely rather than returning a bad connection.
            _forget_verified(self._conn)
            try:
                self._pool.putconn(self._conn, close=True)
            except Exception:
                pass
            return
        self._pool.putconn(self._conn)

    def __getattr__(self, name):
        # Delegate anything else (e.g. .autocommit) to the real connection.
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        if name in ('_pool', '_conn', '_closed', '_from_pool'):
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)

    def __del__(self):
        # Safety net: if a route crashes between get_db() and conn.close()
        # (e.g. an unhandled exception from a bad query), close() never
        # runs and the checked-out connection is leaked from the pool's
        # point of view forever. Enough of these over a long session
        # exhausts the pool (maxconn=20), after which *every* get_db()
        # call starts failing -- including ones before any AI code runs,
        # which is why such failures never showed up in the AI activity
        # log. Once nothing else references this object (e.g. Flask has
        # finished handling the exception and dropped the traceback),
        # CPython's refcounting GC calls this and we return the
        # connection to the pool here instead of leaking it permanently.
        try:
            self.close()
        except Exception:
            pass


def get_db():
    """Get a pooled database connection with dict-like row access."""
    pool = _get_pool()
    conn = _PooledConnection(pool)
    conn.autocommit = False
    return conn



def get_cursor(conn):
    """Get a cursor that returns rows as dicts."""
    return conn.cursor()


def init_db():
    """Initialize the database and create all required tables."""
    conn = get_db()
    cur = get_cursor(conn)

    # Fast path: check once whether the schema already exists. Each CREATE
    # TABLE IF NOT EXISTS below is its own round trip to the database --
    # running all ~15 of them on every single startup (including every
    # auto-reload while the Flask dev server runs with debug=True) was
    # adding real, noticeable time to every 'python app.py' launch, even
    # though after the first run none of them actually create anything.
    # The column-migration checks further down still run every time
    # (they're cheap and are how new columns get added to an existing
    # database later), only the raw table creation is skipped here.
    cur.execute("SELECT to_regclass('public.course_progress') AS exists_flag")
    tables_exist = cur.fetchone()['exists_flag'] is not None

    if not tables_exist:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role VARCHAR(50) DEFAULT 'student',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS career_roles (
                id SERIAL PRIMARY KEY,
                role_name VARCHAR(255) UNIQUE NOT NULL,
                required_technical_skills TEXT,
                required_soft_skills TEXT,
                preferred_domains TEXT,
                description TEXT,
                min_skill_match INTEGER DEFAULT 60
            );
        ''')

    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'career_roles'")
    career_cols = [row['column_name'] for row in cur.fetchall()]

    role_migrations = [
        ("avg_salary_min", "INTEGER"),
        ("avg_salary_max", "INTEGER"),
        ("demand_level", "VARCHAR(50) DEFAULT 'Medium'"),
        ("growth_rate", "VARCHAR(255)"),
        ("related_roles", "TEXT"),
    ]
    for col_name, col_type in role_migrations:
        if col_name not in career_cols:
            try:
                cur.execute(f"ALTER TABLE career_roles ADD COLUMN {col_name} {col_type}")
            except Exception as e:
                print(f"Migration warning: Could not add column {col_name}: {e}")

    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
    existing_columns = [row['column_name'] for row in cur.fetchall()]

    new_columns = [
        ("is_verified", "INTEGER DEFAULT 0"),
        ("otp", "VARCHAR(10)"),
        ("otp_expiry", "TIMESTAMP"),
        ("is_blocked", "INTEGER DEFAULT 0"),
        ("google_id", "VARCHAR(255)"),
        ("github_id", "VARCHAR(255)"),
        ("token_limit", "INTEGER DEFAULT 100000")
    ]

    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            try:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            except Exception as e:
                print(f"Migration warning: Could not add column {col_name}: {e}")

    if not tables_exist:
        cur.execute('''
                CREATE TABLE IF NOT EXISTS student_profiles (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
                    name VARCHAR(255),
                    branch VARCHAR(255) DEFAULT '',
                    year_of_study VARCHAR(50),
                    technical_skills TEXT,
                    soft_skills TEXT,
                    interests TEXT,
                    preferred_domains TEXT,
                    academic_performance TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS resumes (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    filename VARCHAR(255) NOT NULL,
                    filepath TEXT NOT NULL,
                    extracted_skills TEXT,
                    education TEXT,
                    experience TEXT,
                    projects TEXT,
                    certifications TEXT,
                    resume_score DOUBLE PRECISION DEFAULT 0,
                    analysis_result TEXT,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS recommendations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    career_role VARCHAR(255) NOT NULL,
                    match_score DOUBLE PRECISION DEFAULT 0,
                    matched_skills TEXT,
                    missing_skills TEXT,
                    recommended_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS courses (
                    id SERIAL PRIMARY KEY,
                    skill VARCHAR(255) NOT NULL,
                    course_name VARCHAR(255) NOT NULL,
                    platform VARCHAR(255),
                    free_paid VARCHAR(50) DEFAULT 'Free',
                    difficulty VARCHAR(50) DEFAULT 'Beginner',
                    link TEXT,
                    career_roles TEXT,
                    UNIQUE(skill, course_name)
                );

                CREATE TABLE IF NOT EXISTS ai_requests (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    feature VARCHAR(255) NOT NULL,
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'success',
                    error_message TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    token VARCHAR(255) UNIQUE NOT NULL,
                    expiry TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS rate_limits (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(255) NOT NULL,
                    timestamp DOUBLE PRECISION NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    message TEXT NOT NULL,
                    type VARCHAR(50) DEFAULT 'info',
                    is_read INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS mock_interviews (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    career_role VARCHAR(255) NOT NULL,
                    status VARCHAR(50) DEFAULT 'in_progress',
                    score INTEGER,
                    strengths TEXT,
                    weaknesses TEXT,
                    question_count INTEGER DEFAULT 0,
                    current_question INTEGER DEFAULT 0,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS interview_qa (
                    id SERIAL PRIMARY KEY,
                    interview_id INTEGER NOT NULL REFERENCES mock_interviews(id),
                    question TEXT NOT NULL,
                    answer TEXT,
                    feedback TEXT,
                    score INTEGER,
                    question_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS skill_assessments (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    career_role VARCHAR(255) NOT NULL,
                    skill VARCHAR(255) NOT NULL,
                    score INTEGER DEFAULT 0,
                    total_questions INTEGER DEFAULT 0,
                    correct_answers INTEGER DEFAULT 0,
                    confidence VARCHAR(50) DEFAULT 'beginner',
                    taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS course_progress (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    career_role VARCHAR(255) NOT NULL,
                    skill VARCHAR(255) NOT NULL,
                    course_name VARCHAR(255) NOT NULL,
                    UNIQUE(user_id, course_name),
                    status VARCHAR(50) DEFAULT 'not_started',
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    rating INTEGER,
                    notes TEXT
                );
        ''')

    try:
        cur.execute("SELECT id FROM users WHERE username = %s", ('admin',))
        admin_user = cur.fetchone()
        if not admin_user:
            cur.execute(
                "INSERT INTO users (username, email, password_hash, role, is_verified) VALUES (%s, %s, %s, %s, %s)",
                ('admin', 'admin@scn.com', generate_password_hash('admin123'), 'admin', 1)
            )
    except Exception as e:
        print(f"Error creating default admin: {e}")

    conn.commit()
    cur.close()
    conn.close()


def load_csv_data():
    """Load career roles and courses from CSV files into the database."""
    import pandas as pd

    datasets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'datasets')
    conn = get_db()
    cur = get_cursor(conn)

    roles_csv = os.path.join(datasets_dir, 'career_roles.csv')
    if os.path.exists(roles_csv):
        df = pd.read_csv(roles_csv)
        for _, row in df.iterrows():
            try:
                avg_salary_min = int(row['avg_salary_min']) if 'avg_salary_min' in row and pd.notna(row.get('avg_salary_min')) else None
                avg_salary_max = int(row['avg_salary_max']) if 'avg_salary_max' in row and pd.notna(row.get('avg_salary_max')) else None
                demand_level = str(row['demand_level']) if 'demand_level' in row and pd.notna(row.get('demand_level')) else 'Medium'
                growth_rate = str(row['growth_rate']) if 'growth_rate' in row and pd.notna(row.get('growth_rate')) else None
                related_roles = str(row['related_roles']) if 'related_roles' in row and pd.notna(row.get('related_roles')) else None

                cur.execute("SELECT id FROM career_roles WHERE role_name = %s", (row['Role'],))
                existing = cur.fetchone()
                if existing:
                    cur.execute('''
                        UPDATE career_roles SET
                            required_technical_skills=%s, required_soft_skills=%s,
                            preferred_domains=%s, description=%s, min_skill_match=%s,
                            avg_salary_min=%s, avg_salary_max=%s, demand_level=%s, growth_rate=%s, related_roles=%s
                        WHERE id=%s
                    ''', (
                        row['Required_Technical_Skills'],
                        row['Required_Soft_Skills'],
                        row['Preferred_Domains'],
                        row['Description'],
                        int(row['Min_Skill_Match']),
                        avg_salary_min,
                        avg_salary_max,
                        demand_level,
                        growth_rate,
                        related_roles,
                        existing['id']
                    ))
                else:
                    cur.execute('''
                        INSERT INTO career_roles
                        (role_name, required_technical_skills, required_soft_skills, preferred_domains, description, min_skill_match,
                         avg_salary_min, avg_salary_max, demand_level, growth_rate, related_roles)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        row['Role'],
                        row['Required_Technical_Skills'],
                        row['Required_Soft_Skills'],
                        row['Preferred_Domains'],
                        row['Description'],
                        int(row['Min_Skill_Match']),
                        avg_salary_min,
                        avg_salary_max,
                        demand_level,
                        growth_rate,
                        related_roles
                    ))
            except Exception:
                continue

    courses_csv = os.path.join(datasets_dir, 'courses.csv')
    if os.path.exists(courses_csv):
        df = pd.read_csv(courses_csv)
        for _, row in df.iterrows():
            try:
                cur.execute("SELECT id FROM courses WHERE course_name = %s", (row['Course_Name'],))
                existing = cur.fetchone()
                if existing:
                    cur.execute('''
                        UPDATE courses SET
                            skill=%s, platform=%s, free_paid=%s, difficulty=%s, link=%s, career_roles=%s
                        WHERE id=%s
                    ''', (
                        row['Skill'], row['Platform'], row['Free_Paid'],
                        row['Difficulty'], row['Link'], row['Career_Roles'],
                        existing['id']
                    ))
                else:
                    cur.execute('''
                        INSERT INTO courses
                        (skill, course_name, platform, free_paid, difficulty, link, career_roles)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        row['Skill'], row['Course_Name'], row['Platform'],
                        row['Free_Paid'], row['Difficulty'], row['Link'], row['Career_Roles']
                    ))
            except Exception:
                continue

    conn.commit()
    cur.close()
    conn.close()
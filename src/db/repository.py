"""Data access layer for TalentBeacon MySQL database."""
import json

from src.db.connection import execute_query, get_db_connection

_ENTERPRISE_SCHEMA_READY = False


def get_all_employees():
    return execute_query(
        """
        SELECT e.*, GROUP_CONCAT(DISTINCT s.name SEPARATOR ';') AS skills,
               GROUP_CONCAT(DISTINCT c.name SEPARATOR ', ') AS certifications
        FROM employees e
        LEFT JOIN employee_skills es ON e.id = es.employee_id
        LEFT JOIN skills s ON es.skill_id = s.id
        LEFT JOIN employee_certifications ec ON e.id = ec.employee_id
        LEFT JOIN certifications c ON ec.certification_id = c.id
        GROUP BY e.id
        ORDER BY e.id
        """
    )


def get_active_dataset_employees(uploaded_by=None):
    """Return employees that belong to the active uploaded dataset."""
    active = get_active_dataset_upload(uploaded_by=uploaded_by)
    if not active:
        return []
    return execute_query(
        """
        SELECT e.id, e.employee_code, e.name, e.email, e.department, e.designation,
               e.years_of_experience, e.education_level, e.performance_score,
               e.projects_handled, e.satisfaction_score, e.dataset_upload_id,
               du.filename AS dataset_filename,
               GROUP_CONCAT(DISTINCT s.name ORDER BY s.name SEPARATOR ';') AS skills,
               GROUP_CONCAT(DISTINCT c.name ORDER BY c.name SEPARATOR ';') AS certifications
        FROM employees e
        JOIN dataset_uploads du ON e.dataset_upload_id = du.id
        LEFT JOIN employee_skills es ON e.id = es.employee_id
        LEFT JOIN skills s ON es.skill_id = s.id
        LEFT JOIN employee_certifications ec ON e.id = ec.employee_id
        LEFT JOIN certifications c ON ec.certification_id = c.id
        WHERE e.dataset_upload_id = %s
        GROUP BY e.id, du.filename
        ORDER BY e.id
        """,
        (active["id"],),
    )


def get_employee_by_id(employee_id):
    return execute_query(
        """
        SELECT e.*, GROUP_CONCAT(DISTINCT s.name SEPARATOR ';') AS skills,
               GROUP_CONCAT(DISTINCT c.name SEPARATOR ', ') AS certifications
        FROM employees e
        LEFT JOIN employee_skills es ON e.id = es.employee_id
        LEFT JOIN skills s ON es.skill_id = s.id
        LEFT JOIN employee_certifications ec ON e.id = ec.employee_id
        LEFT JOIN certifications c ON ec.certification_id = c.id
        WHERE e.id = %s
        GROUP BY e.id
        """,
        (employee_id,),
        fetch_one=True,
    )


def get_all_skills():
    return execute_query("SELECT * FROM skills ORDER BY category, name")


def get_all_roles():
    return execute_query("SELECT * FROM roles ORDER BY name")


def get_role_with_skills(role_id):
    role = execute_query("SELECT * FROM roles WHERE id = %s", (role_id,), fetch_one=True)
    if not role:
        return None
    skills = execute_query(
        """
        SELECT s.name, rs.is_required, rs.min_level, s.category
        FROM role_skills rs
        JOIN skills s ON rs.skill_id = s.id
        WHERE rs.role_id = %s
        """,
        (role_id,),
    )
    role["skills"] = skills
    return role


def get_role_by_name(role_name):
    return execute_query(
        "SELECT * FROM roles WHERE LOWER(name) = LOWER(%s)",
        (role_name,),
        fetch_one=True,
    )


def get_learning_for_skill(skill_name):
    return execute_query(
        """
        SELECT lr.* FROM learning_resources lr
        JOIN skills s ON lr.skill_id = s.id
        WHERE LOWER(s.name) = LOWER(%s)
        """,
        (skill_name,),
    )


def get_user_by_username(username):
    ensure_enterprise_user_schema()
    return execute_query(
        """
        SELECT * FROM users
        WHERE is_active = TRUE
          AND (LOWER(username) = LOWER(%s)
               OR LOWER(email) = LOWER(%s)
               OR LOWER(COALESCE(company_email, '')) = LOWER(%s)
               OR LOWER(COALESCE(employee_login_id, '')) = LOWER(%s))
        ORDER BY
            CASE
                WHEN LOWER(username) = LOWER(%s) THEN 0
                WHEN LOWER(email) = LOWER(%s) THEN 1
                WHEN LOWER(COALESCE(company_email, '')) = LOWER(%s) THEN 2
                WHEN LOWER(COALESCE(employee_login_id, '')) = LOWER(%s) THEN 3
                ELSE 4
            END,
            CASE role
                WHEN 'admin' THEN 0
                WHEN 'hr' THEN 1
                WHEN 'manager' THEN 2
                ELSE 3
            END,
            created_from_upload DESC,
            COALESCE(temp_password_expires_at, '') DESC,
            id DESC
        """,
        (username, username, username, username, username, username, username, username),
        fetch_one=True,
    )


def get_user_account_by_id(user_id):
    ensure_enterprise_user_schema()
    return execute_query(
        "SELECT * FROM users WHERE id = %s AND is_active = TRUE",
        (user_id,),
        fetch_one=True,
    )


def get_user_accounts():
    ensure_enterprise_user_schema()
    return execute_query(
        "SELECT * FROM users WHERE is_active = TRUE ORDER BY id",
    )


def write_audit_log(action, actor_id=None, target_id=None, status="ok", details=None):
    ensure_enterprise_user_schema()
    return execute_query(
        """
        INSERT INTO audit_logs (action, actor_id, target_id, status, details_json)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (action, actor_id, target_id, status, json.dumps(details or {})),
    )


def get_analytics_summary():
    return execute_query(
        """
        SELECT
            (SELECT COUNT(*) FROM employees) AS total_employees,
            (SELECT COUNT(*) FROM skills) AS total_skills,
            (SELECT COUNT(*) FROM roles) AS total_roles,
            (SELECT COUNT(*) FROM learning_resources) AS total_courses,
            (SELECT COUNT(*) FROM certifications) AS total_certifications,
            (SELECT AVG(performance_score) FROM employees) AS avg_performance,
            (SELECT AVG(years_of_experience) FROM employees) AS avg_experience
        """,
        fetch_one=True,
    )


def get_skill_distribution():
    return execute_query(
        """
        SELECT s.name, s.category, COUNT(es.employee_id) AS employee_count
        FROM skills s
        LEFT JOIN employee_skills es ON s.id = es.skill_id
        GROUP BY s.id, s.name, s.category
        ORDER BY employee_count DESC
        LIMIT 30
        """
    )


def get_department_stats():
    return execute_query(
        """
        SELECT department, COUNT(*) AS count,
               AVG(performance_score) AS avg_performance,
               AVG(years_of_experience) AS avg_experience
        FROM employees
        GROUP BY department
        ORDER BY count DESC
        """
    )


def log_ml_training(model_name, algorithm, accuracy, f1_score, rmse, metrics_json):
    execute_query(
        """
        INSERT INTO ml_training_logs (model_name, algorithm, accuracy, f1_score, rmse, metrics_json)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (model_name, algorithm, accuracy, f1_score, rmse, json.dumps(metrics_json)),
    )


def ensure_upload_schema():
    """Create upload and JD matching tables without resetting existing data."""
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SHOW COLUMNS FROM employees LIKE 'email'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE employees ADD COLUMN email VARCHAR(255) NULL")

            cursor.execute("SHOW COLUMNS FROM employees LIKE 'dataset_upload_id'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE employees ADD COLUMN dataset_upload_id INT NULL")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS dataset_uploads (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    stored_filename VARCHAR(255) NULL,
                    file_path VARCHAR(500) NULL,
                    file_type ENUM('csv', 'excel') NOT NULL,
                    row_count INT DEFAULT 0,
                    is_active BOOLEAN DEFAULT FALSE,
                    uploaded_by INT NULL,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            for column_sql in (
                "ALTER TABLE dataset_uploads ADD COLUMN stored_filename VARCHAR(255) NULL",
                "ALTER TABLE dataset_uploads ADD COLUMN file_path VARCHAR(500) NULL",
                "ALTER TABLE dataset_uploads ADD COLUMN is_active BOOLEAN DEFAULT FALSE",
            ):
                try:
                    cursor.execute(column_sql)
                except Exception:
                    pass
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS jd_uploads (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    extracted_text MEDIUMTEXT,
                    requirements_json JSON,
                    uploaded_by INT NULL,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS jd_candidate_matches (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    jd_upload_id INT NOT NULL,
                    employee_id INT NOT NULL,
                    match_score DECIMAL(5,2) NOT NULL,
                    score_breakdown JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (jd_upload_id) REFERENCES jd_uploads(id) ON DELETE CASCADE,
                    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
                    UNIQUE KEY uq_jd_employee_match (jd_upload_id, employee_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS project_candidate_matches (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    project_id INT NOT NULL,
                    employee_id INT NOT NULL,
                    match_score DECIMAL(5,2) NOT NULL,
                    score_breakdown JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
                    UNIQUE KEY uq_project_employee_match (project_id, employee_id)
                )
                """
            )
            for stmt in (
                "CREATE INDEX idx_emp_email ON employees(email)",
                "CREATE INDEX idx_emp_dataset_upload ON employees(dataset_upload_id)",
                "CREATE INDEX idx_jd_match_score ON jd_candidate_matches(jd_upload_id, match_score)",
                "CREATE INDEX idx_project_match_score ON project_candidate_matches(project_id, match_score)",
            ):
                try:
                    cursor.execute(stmt)
                except Exception:
                    pass


def ensure_enterprise_user_schema():
    """Add enterprise onboarding fields to the existing users table."""
    global _ENTERPRISE_SCHEMA_READY
    if _ENTERPRISE_SCHEMA_READY:
        return
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("ALTER TABLE users MODIFY role VARCHAR(30) NOT NULL DEFAULT 'employee'")
            except Exception:
                pass
            for column_sql in (
                "ALTER TABLE users ADD COLUMN company_email VARCHAR(255) NULL",
                "ALTER TABLE users ADD COLUMN employee_login_id VARCHAR(50) NULL",
                "ALTER TABLE users ADD COLUMN first_login BOOLEAN DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN temp_password_expires_at VARCHAR(40) NULL",
                "ALTER TABLE users ADD COLUMN source_dataset_id VARCHAR(100) NULL",
                "ALTER TABLE users ADD COLUMN source_employee_code VARCHAR(255) NULL",
                "ALTER TABLE users ADD COLUMN source_employee_key VARCHAR(255) NULL",
                "ALTER TABLE users ADD COLUMN source_file_hash VARCHAR(255) NULL",
                "ALTER TABLE users ADD COLUMN source_email VARCHAR(255) NULL",
                "ALTER TABLE users ADD COLUMN created_by INT NULL",
                "ALTER TABLE users ADD COLUMN created_from_upload BOOLEAN DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN created_from_demo BOOLEAN DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN account_created BOOLEAN DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN account_status VARCHAR(40) NULL",
                "ALTER TABLE users ADD COLUMN temp_password_used BOOLEAN DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN failed_attempts INT DEFAULT 0",
                "ALTER TABLE users ADD COLUMN locked_until VARCHAR(40) NULL",
                "ALTER TABLE users ADD COLUMN otp_hash VARCHAR(255) NULL",
                "ALTER TABLE users ADD COLUMN otp_expires_at VARCHAR(40) NULL",
                "ALTER TABLE users ADD COLUMN otp_used BOOLEAN DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN otp_purpose VARCHAR(40) NULL",
                "ALTER TABLE users ADD COLUMN name_from_file BOOLEAN DEFAULT FALSE",
            ):
                try:
                    cursor.execute(column_sql)
                except Exception:
                    pass
            for stmt in (
                "CREATE INDEX idx_users_company_email ON users(company_email)",
                "CREATE INDEX idx_users_source_dataset ON users(source_dataset_id)",
                "CREATE INDEX idx_users_created_by ON users(created_by)",
                "CREATE INDEX idx_users_employee_login_id ON users(employee_login_id)",
                "CREATE INDEX idx_users_source_employee_key ON users(source_employee_key)",
            ):
                try:
                    cursor.execute(stmt)
                except Exception:
                    pass
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    action VARCHAR(120) NOT NULL,
                    actor_id INT NULL,
                    target_id INT NULL,
                    status VARCHAR(40) DEFAULT 'ok',
                    details_json JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_audit_action (action),
                    INDEX idx_audit_actor (actor_id),
                    INDEX idx_audit_target (target_id)
                )
                """
            )
    _ENTERPRISE_SCHEMA_READY = True


def upsert_user_account(user):
    """Persist a generated app user to MySQL without exposing temporary passwords."""
    ensure_enterprise_user_schema()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            _reuse_upload_user_id(cursor, user)
            cursor.execute(_USER_ACCOUNT_UPSERT_SQL, _user_account_params(user))
            return user.get("id")


def _reuse_upload_user_id(cursor, user):
    if not user.get("created_from_upload"):
        return
    identifiers = [
        str(user.get("company_email") or "").strip().lower(),
        str(user.get("email") or "").strip().lower(),
        str(user.get("employee_id") or "").strip().lower(),
    ]
    identifiers = [value for value in identifiers if value]
    if not identifiers:
        return
    placeholders = ",".join(["%s"] * len(identifiers))
    cursor.execute(
        f"""
        SELECT id FROM users
        WHERE is_active = TRUE
          AND created_from_upload = TRUE
          AND role = 'employee'
          AND (
              LOWER(COALESCE(company_email, '')) IN ({placeholders})
              OR LOWER(COALESCE(email, '')) IN ({placeholders})
              OR LOWER(COALESCE(employee_login_id, '')) IN ({placeholders})
          )
        ORDER BY id DESC
        LIMIT 1
        """,
        tuple(identifiers + identifiers + identifiers),
    )
    existing = cursor.fetchone()
    if existing:
        user["id"] = existing["id"]


_USER_ACCOUNT_UPSERT_SQL = """
    INSERT INTO users (
        id, username, email, password_hash, role, employee_id, company_email,
        employee_login_id, first_login, temp_password_expires_at,
        source_dataset_id, source_employee_code, source_employee_key,
        source_file_hash, source_email, created_by, created_from_upload,
        created_from_demo, account_created, account_status,
        temp_password_used, failed_attempts, locked_until, otp_hash,
        otp_expires_at, otp_used, otp_purpose, name_from_file, is_active
    ) VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
    ON DUPLICATE KEY UPDATE
        username = VALUES(username),
        password_hash = VALUES(password_hash),
        role = VALUES(role),
        company_email = VALUES(company_email),
        employee_login_id = VALUES(employee_login_id),
        first_login = VALUES(first_login),
        temp_password_expires_at = VALUES(temp_password_expires_at),
        source_dataset_id = VALUES(source_dataset_id),
        source_employee_code = VALUES(source_employee_code),
        source_employee_key = VALUES(source_employee_key),
        source_file_hash = VALUES(source_file_hash),
        source_email = VALUES(source_email),
        created_by = VALUES(created_by),
        created_from_upload = VALUES(created_from_upload),
        created_from_demo = VALUES(created_from_demo),
        account_created = VALUES(account_created),
        account_status = VALUES(account_status),
        temp_password_used = VALUES(temp_password_used),
        failed_attempts = VALUES(failed_attempts),
        locked_until = VALUES(locked_until),
        otp_hash = VALUES(otp_hash),
        otp_expires_at = VALUES(otp_expires_at),
        otp_used = VALUES(otp_used),
        otp_purpose = VALUES(otp_purpose),
        name_from_file = VALUES(name_from_file),
        is_active = TRUE
"""


def _user_account_params(user):
    return (
        user.get("id"),
        user.get("username"),
        user.get("email") or user.get("company_email"),
        user.get("password_hash"),
        user.get("role", "employee"),
        user.get("company_email") or user.get("email"),
        user.get("employee_id"),
        bool(user.get("first_login")),
        user.get("temp_password_expires_at"),
        user.get("source_dataset_id"),
        user.get("source_employee_code"),
        user.get("source_employee_key"),
        user.get("source_file_hash"),
        user.get("source_email"),
        user.get("created_by"),
        bool(user.get("created_from_upload")),
        bool(user.get("created_from_demo")),
        bool(user.get("account_created")),
        user.get("account_status") or ("created" if user.get("account_created") else "pending_setup"),
        bool(user.get("temp_password_used")),
        int(user.get("failed_attempts") or 0),
        user.get("locked_until"),
        user.get("otp_hash"),
        user.get("otp_expires_at"),
        bool(user.get("otp_used")),
        user.get("otp_purpose"),
        bool(user.get("name_from_file")),
    )


def upsert_user_accounts(users):
    """Bulk-persist generated app users to MySQL."""
    if not users:
        return 0
    ensure_enterprise_user_schema()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            for user in users:
                _reuse_upload_user_id(cursor, user)
                cursor.execute(_USER_ACCOUNT_UPSERT_SQL, _user_account_params(user))
            return len(users)


def create_dataset_upload(filename, file_type, row_count, uploaded_by=None, stored_filename=None, file_path=None):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            if uploaded_by is None:
                cursor.execute("UPDATE dataset_uploads SET is_active = FALSE WHERE uploaded_by IS NULL")
            else:
                cursor.execute("UPDATE dataset_uploads SET is_active = FALSE WHERE uploaded_by = %s", (uploaded_by,))
            cursor.execute(
                """
                INSERT INTO dataset_uploads (
                    filename, stored_filename, file_path, file_type, row_count, is_active, uploaded_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (filename, stored_filename, file_path, file_type, row_count, True, uploaded_by),
            )
            return cursor.lastrowid


def create_jd_upload(filename, extracted_text, requirements, uploaded_by=None):
    return execute_query(
        """
        INSERT INTO jd_uploads (filename, extracted_text, requirements_json, uploaded_by)
        VALUES (%s, %s, %s, %s)
        """,
        (filename, extracted_text, json.dumps(requirements), uploaded_by),
    )


def get_upload_summary():
    return execute_query(
        """
        SELECT
            (SELECT COUNT(*) FROM employees) AS total_candidates,
            (SELECT COUNT(*) FROM dataset_uploads) AS uploaded_datasets,
            (SELECT COUNT(*) FROM jd_uploads) AS uploaded_jds,
            (
                SELECT COALESCE(MAX(pcm.match_score), 0)
                FROM project_candidate_matches pcm
                JOIN employees e ON pcm.employee_id = e.id
                JOIN dataset_uploads du ON e.dataset_upload_id = du.id AND du.is_active = TRUE
            ) AS best_match_score
        """,
        fetch_one=True,
    )


def get_dataset_uploads(limit=10):
    return execute_query(
        """
        SELECT * FROM dataset_uploads
        ORDER BY uploaded_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_dataset_upload(upload_id):
    return execute_query(
        "SELECT * FROM dataset_uploads WHERE id = %s",
        (upload_id,),
        fetch_one=True,
    )


def get_active_dataset_upload(uploaded_by=None):
    def find_one(owner_filter="", params=()):
        return execute_query(
            f"""
            SELECT * FROM dataset_uploads
            WHERE is_active = TRUE
            {owner_filter}
            ORDER BY uploaded_at DESC
            LIMIT 1
            """,
            tuple(params),
            fetch_one=True,
        )

    if uploaded_by is None:
        active = find_one("AND uploaded_by IS NULL")
    else:
        active = find_one("AND uploaded_by = %s", (uploaded_by,))
        if not active:
            active = find_one("AND uploaded_by IS NULL")
    if active:
        return active
    active = find_one()
    if active:
        return active
    return execute_query(
        """
        SELECT * FROM dataset_uploads
        ORDER BY uploaded_at DESC
        LIMIT 1
        """,
        fetch_one=True,
    )


def activate_dataset_upload(upload_id, uploaded_by=None):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM dataset_uploads WHERE id = %s", (upload_id,))
            if not cursor.fetchone():
                raise ValueError("Uploaded file not found.")
            if uploaded_by is None:
                cursor.execute("UPDATE dataset_uploads SET is_active = FALSE WHERE uploaded_by IS NULL")
            else:
                cursor.execute("UPDATE dataset_uploads SET is_active = FALSE WHERE uploaded_by = %s", (uploaded_by,))
            cursor.execute("UPDATE dataset_uploads SET is_active = TRUE WHERE id = %s", (upload_id,))
            return upload_id


def clear_dataset_employees(upload_id):
    return execute_query("DELETE FROM employees WHERE dataset_upload_id = %s", (upload_id,))


def update_dataset_row_count(upload_id, row_count):
    return execute_query(
        "UPDATE dataset_uploads SET row_count = %s WHERE id = %s",
        (row_count, upload_id),
    )


def delete_dataset_upload(upload_id):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM dataset_uploads WHERE id = %s", (upload_id,))
            upload = cursor.fetchone()
            if not upload:
                raise ValueError("Uploaded file not found.")
            was_active = bool(upload.get("is_active"))
            cursor.execute("DELETE FROM employees WHERE dataset_upload_id = %s", (upload_id,))
            cursor.execute("DELETE FROM dataset_uploads WHERE id = %s", (upload_id,))
            if was_active:
                cursor.execute(
                    """
                    SELECT id FROM dataset_uploads
                    ORDER BY uploaded_at DESC
                    LIMIT 1
                    """
                )
                replacement = cursor.fetchone()
                if replacement:
                    cursor.execute(
                        "UPDATE dataset_uploads SET is_active = TRUE WHERE id = %s",
                        (replacement["id"],),
                    )
            return upload


def get_jd_uploads(limit=10):
    return execute_query(
        """
        SELECT * FROM jd_uploads
        ORDER BY uploaded_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def upsert_employee_from_upload(candidate, dataset_upload_id):
    """Insert or update a candidate and replace their skills/certifications."""
    employee_code = candidate["employee_code"]
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO employees (
                    employee_code, name, email, department, designation,
                    years_of_experience, education_level, performance_score,
                    projects_handled, satisfaction_score, dataset_upload_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    email = VALUES(email),
                    department = VALUES(department),
                    designation = VALUES(designation),
                    years_of_experience = VALUES(years_of_experience),
                    education_level = VALUES(education_level),
                    performance_score = VALUES(performance_score),
                    projects_handled = VALUES(projects_handled),
                    satisfaction_score = VALUES(satisfaction_score),
                    dataset_upload_id = VALUES(dataset_upload_id)
                """,
                (
                    employee_code,
                    candidate.get("name"),
                    candidate.get("email"),
                    candidate.get("department", "Uploaded"),
                    candidate.get("designation", "Candidate"),
                    candidate.get("years_of_experience", 0),
                    candidate.get("education_level", "Unknown"),
                    candidate.get("performance_score", 3),
                    candidate.get("projects_handled", 0),
                    candidate.get("satisfaction_score", 3.0),
                    dataset_upload_id,
                ),
            )
            cursor.execute("SELECT id FROM employees WHERE employee_code = %s", (employee_code,))
            employee_id = cursor.fetchone()["id"]

            cursor.execute("DELETE FROM employee_skills WHERE employee_id = %s", (employee_id,))
            for skill in candidate.get("skills", []):
                cursor.execute("SELECT id FROM skills WHERE LOWER(name) = LOWER(%s)", (skill,))
                row = cursor.fetchone()
                if row:
                    skill_id = row["id"]
                else:
                    cursor.execute("INSERT INTO skills (name, category) VALUES (%s, 'technical')", (skill,))
                    skill_id = cursor.lastrowid
                cursor.execute(
                    """
                    INSERT IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level)
                    VALUES (%s, %s, 'intermediate')
                    """,
                    (employee_id, skill_id),
                )

            cursor.execute("DELETE FROM employee_certifications WHERE employee_id = %s", (employee_id,))
            for cert in candidate.get("certifications", []):
                cursor.execute("SELECT id FROM certifications WHERE name = %s", (cert,))
                row = cursor.fetchone()
                if row:
                    cert_id = row["id"]
                else:
                    cursor.execute("INSERT INTO certifications (name) VALUES (%s)", (cert,))
                    cert_id = cursor.lastrowid
                cursor.execute(
                    """
                    INSERT IGNORE INTO employee_certifications (employee_id, certification_id)
                    VALUES (%s, %s)
                    """,
                    (employee_id, cert_id),
                )
            return employee_id


def upsert_employees_from_upload(candidates, dataset_upload_id):
    """Insert/update uploaded employees in one transaction for much faster uploads."""
    def chunks(values, size=500):
        values = list(values)
        for index in range(0, len(values), size):
            yield values[index:index + size]

    def normalized_key(value):
        return str(value or "").strip().lower()

    if not candidates:
        return 0
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            employee_rows = [
                (
                    candidate["employee_code"],
                    candidate.get("name"),
                    candidate.get("email"),
                    candidate.get("department", "Uploaded"),
                    candidate.get("designation", "Employee"),
                    candidate.get("years_of_experience", 0),
                    candidate.get("education_level", "Unknown"),
                    candidate.get("performance_score", 3),
                    candidate.get("projects_handled", 0),
                    candidate.get("satisfaction_score", 3.0),
                    dataset_upload_id,
                )
                for candidate in candidates
            ]
            cursor.executemany(
                """
                INSERT INTO employees (
                    employee_code, name, email, department, designation,
                    years_of_experience, education_level, performance_score,
                    projects_handled, satisfaction_score, dataset_upload_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    email = VALUES(email),
                    department = VALUES(department),
                    designation = VALUES(designation),
                    years_of_experience = VALUES(years_of_experience),
                    education_level = VALUES(education_level),
                    performance_score = VALUES(performance_score),
                    projects_handled = VALUES(projects_handled),
                    satisfaction_score = VALUES(satisfaction_score),
                    dataset_upload_id = VALUES(dataset_upload_id)
                """,
                employee_rows,
            )

            employee_codes = [candidate["employee_code"] for candidate in candidates]
            employee_id_by_code = {}
            for code_chunk in chunks(employee_codes):
                placeholders = ",".join(["%s"] * len(code_chunk))
                cursor.execute(
                    f"SELECT id, employee_code FROM employees WHERE employee_code IN ({placeholders})",
                    tuple(code_chunk),
                )
                for row in cursor.fetchall():
                    employee_id_by_code[row["employee_code"]] = row["id"]

            skill_names = sorted({
                str(skill or "").strip()
                for candidate in candidates
                for skill in candidate.get("skills", [])
                if str(skill or "").strip()
            }, key=str.lower)
            cert_names = sorted({
                str(cert or "").strip()
                for candidate in candidates
                for cert in candidate.get("certifications", [])
                if str(cert or "").strip()
            }, key=str.lower)

            skill_id_by_key = {}
            if skill_names:
                for name_chunk in chunks(skill_names):
                    placeholders = ",".join(["%s"] * len(name_chunk))
                    cursor.execute(
                        f"SELECT id, name FROM skills WHERE LOWER(name) IN ({placeholders})",
                        tuple(normalized_key(name) for name in name_chunk),
                    )
                    for row in cursor.fetchall():
                        skill_id_by_key[normalized_key(row["name"])] = row["id"]
                missing_skills = [
                    (name, "technical")
                    for name in skill_names
                    if normalized_key(name) not in skill_id_by_key
                ]
                if missing_skills:
                    cursor.executemany(
                        "INSERT IGNORE INTO skills (name, category) VALUES (%s, %s)",
                        missing_skills,
                    )
                    for name_chunk in chunks(skill_names):
                        placeholders = ",".join(["%s"] * len(name_chunk))
                        cursor.execute(
                            f"SELECT id, name FROM skills WHERE LOWER(name) IN ({placeholders})",
                            tuple(normalized_key(name) for name in name_chunk),
                        )
                        for row in cursor.fetchall():
                            skill_id_by_key[normalized_key(row["name"])] = row["id"]

            cert_id_by_key = {}
            if cert_names:
                for name_chunk in chunks(cert_names):
                    placeholders = ",".join(["%s"] * len(name_chunk))
                    cursor.execute(
                        f"SELECT id, name FROM certifications WHERE LOWER(name) IN ({placeholders})",
                        tuple(normalized_key(name) for name in name_chunk),
                    )
                    for row in cursor.fetchall():
                        cert_id_by_key[normalized_key(row["name"])] = row["id"]
                missing_certs = [
                    (name,)
                    for name in cert_names
                    if normalized_key(name) not in cert_id_by_key
                ]
                if missing_certs:
                    cursor.executemany(
                        "INSERT IGNORE INTO certifications (name) VALUES (%s)",
                        missing_certs,
                    )
                    for name_chunk in chunks(cert_names):
                        placeholders = ",".join(["%s"] * len(name_chunk))
                        cursor.execute(
                            f"SELECT id, name FROM certifications WHERE LOWER(name) IN ({placeholders})",
                            tuple(normalized_key(name) for name in name_chunk),
                        )
                        for row in cursor.fetchall():
                            cert_id_by_key[normalized_key(row["name"])] = row["id"]

            employee_ids = list(employee_id_by_code.values())
            for id_chunk in chunks(employee_ids):
                placeholders = ",".join(["%s"] * len(id_chunk))
                cursor.execute(f"DELETE FROM employee_skills WHERE employee_id IN ({placeholders})", tuple(id_chunk))
                cursor.execute(f"DELETE FROM employee_certifications WHERE employee_id IN ({placeholders})", tuple(id_chunk))

            skill_links = []
            cert_links = []
            seen_skill_links = set()
            seen_cert_links = set()
            for candidate in candidates:
                employee_id = employee_id_by_code.get(candidate["employee_code"])
                if not employee_id:
                    continue
                for skill in candidate.get("skills", []):
                    skill_id = skill_id_by_key.get(normalized_key(skill))
                    key = (employee_id, skill_id)
                    if skill_id and key not in seen_skill_links:
                        seen_skill_links.add(key)
                        skill_links.append((employee_id, skill_id, "intermediate"))
                for cert in candidate.get("certifications", []):
                    cert_id = cert_id_by_key.get(normalized_key(cert))
                    key = (employee_id, cert_id)
                    if cert_id and key not in seen_cert_links:
                        seen_cert_links.add(key)
                        cert_links.append((employee_id, cert_id))
            if skill_links:
                cursor.executemany(
                    """
                    INSERT IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level)
                    VALUES (%s, %s, %s)
                    """,
                    skill_links,
                )
            if cert_links:
                cursor.executemany(
                    """
                    INSERT IGNORE INTO employee_certifications (employee_id, certification_id)
                    VALUES (%s, %s)
                    """,
                    cert_links,
                )
            return len(candidates)


def get_candidate_records(uploaded_only=False, dataset_upload_id=None, active_only=False):
    params = []
    where_parts = []
    if uploaded_only:
        where_parts.append("e.dataset_upload_id IS NOT NULL")
    if dataset_upload_id:
        where_parts.append("e.dataset_upload_id = %s")
        params.append(dataset_upload_id)
    if active_only:
        active = get_active_dataset_upload()
        if not active:
            return []
        where_parts.append("e.dataset_upload_id = %s")
        params.append(active["id"])
    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    return execute_query(
        f"""
        SELECT e.id, e.employee_code, e.name, e.email, e.department, e.designation,
               e.years_of_experience, e.education_level, e.performance_score,
               GROUP_CONCAT(DISTINCT s.name SEPARATOR ';') AS skills,
               GROUP_CONCAT(DISTINCT c.name SEPARATOR ', ') AS certifications
        FROM employees e
        LEFT JOIN employee_skills es ON e.id = es.employee_id
        LEFT JOIN skills s ON es.skill_id = s.id
        LEFT JOIN employee_certifications ec ON e.id = ec.employee_id
        LEFT JOIN certifications c ON ec.certification_id = c.id
        {where_clause}
        GROUP BY e.id
        ORDER BY e.id
        """,
        tuple(params),
    )


def get_uploaded_candidate_count():
    return execute_query(
        "SELECT COUNT(*) AS cnt FROM employees WHERE dataset_upload_id IS NOT NULL",
        fetch_one=True,
    )


def create_project(name, description, required_skills, min_experience, created_by=None):
    return execute_query(
        """
        INSERT INTO projects (name, description, required_skills, min_experience, created_by)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (name, description, required_skills, min_experience, created_by),
    )


def update_project(project_id, name, description, required_skills, min_experience):
    return execute_query(
        """
        UPDATE projects
        SET name = %s, description = %s, required_skills = %s, min_experience = %s
        WHERE id = %s
        """,
        (name, description, required_skills, min_experience, project_id),
    )


def delete_project(project_id):
    return execute_query("DELETE FROM projects WHERE id = %s", (project_id,))


def get_project(project_id):
    return execute_query("SELECT * FROM projects WHERE id = %s", (project_id,), fetch_one=True)


def get_projects(limit=100):
    return execute_query(
        """
        SELECT p.*,
               (
                   SELECT COUNT(*)
                   FROM project_candidate_matches pcm
                   JOIN employees e ON pcm.employee_id = e.id
                   JOIN dataset_uploads du ON e.dataset_upload_id = du.id AND du.is_active = TRUE
                   WHERE pcm.project_id = p.id
               ) AS match_count,
               (
                   SELECT COALESCE(MAX(pcm.match_score), 0)
                   FROM project_candidate_matches pcm
                   JOIN employees e ON pcm.employee_id = e.id
                   JOIN dataset_uploads du ON e.dataset_upload_id = du.id AND du.is_active = TRUE
                   WHERE pcm.project_id = p.id
               ) AS top_match
        FROM projects p
        ORDER BY p.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def save_project_match(project_id, employee_id, match_score, breakdown):
    return execute_query(
        """
        INSERT INTO project_candidate_matches (project_id, employee_id, match_score, score_breakdown)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            match_score = VALUES(match_score),
            score_breakdown = VALUES(score_breakdown),
            created_at = CURRENT_TIMESTAMP
        """,
        (project_id, employee_id, match_score, json.dumps(breakdown)),
    )


def clear_project_matches(project_id):
    return execute_query("DELETE FROM project_candidate_matches WHERE project_id = %s", (project_id,))


def get_matches_for_project(project_id):
    active = get_active_dataset_upload()
    if not active:
        return []
    rows = execute_query(
        """
        SELECT m.match_score, m.score_breakdown, e.id AS employee_id, e.employee_code,
               e.name, e.email, e.department, e.designation, e.years_of_experience,
               e.education_level,
               GROUP_CONCAT(DISTINCT s.name SEPARATOR ';') AS skills
        FROM project_candidate_matches m
        JOIN employees e ON m.employee_id = e.id
        LEFT JOIN employee_skills es ON e.id = es.employee_id
        LEFT JOIN skills s ON es.skill_id = s.id
        WHERE m.project_id = %s AND e.dataset_upload_id = %s
        GROUP BY m.id, e.id
        ORDER BY m.match_score DESC
        """,
        (project_id, active["id"]),
    )
    for row in rows:
        if isinstance(row.get("score_breakdown"), str):
            row["score_breakdown"] = json.loads(row["score_breakdown"])
    return rows


def save_jd_match(jd_upload_id, employee_id, match_score, breakdown):
    return execute_query(
        """
        INSERT INTO jd_candidate_matches (jd_upload_id, employee_id, match_score, score_breakdown)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            match_score = VALUES(match_score),
            score_breakdown = VALUES(score_breakdown),
            created_at = CURRENT_TIMESTAMP
        """,
        (jd_upload_id, employee_id, match_score, json.dumps(breakdown)),
    )


def get_matches_for_jd(jd_upload_id):
    rows = execute_query(
        """
        SELECT m.match_score, m.score_breakdown, e.id AS employee_id, e.employee_code,
               e.name, e.email, e.department, e.designation, e.years_of_experience,
               e.education_level,
               GROUP_CONCAT(DISTINCT s.name SEPARATOR ';') AS skills
        FROM jd_candidate_matches m
        JOIN employees e ON m.employee_id = e.id
        LEFT JOIN employee_skills es ON e.id = es.employee_id
        LEFT JOIN skills s ON es.skill_id = s.id
        WHERE m.jd_upload_id = %s
        GROUP BY m.id, e.id
        ORDER BY m.match_score DESC
        """,
        (jd_upload_id,),
    )
    for row in rows:
        if isinstance(row.get("score_breakdown"), str):
            row["score_breakdown"] = json.loads(row["score_breakdown"])
    return rows

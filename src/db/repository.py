"""Data access layer for TalentBeacon MySQL database."""
import json

from src.db.connection import execute_query, get_db_connection


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
    params = []
    owner_filter = ""
    if uploaded_by is None:
        owner_filter = "AND du.uploaded_by IS NULL"
    else:
        owner_filter = "AND du.uploaded_by = %s"
        params.append(uploaded_by)
    return execute_query(
        f"""
        SELECT e.id, e.employee_code, e.name, e.email, e.department, e.designation,
               e.years_of_experience, e.education_level, e.performance_score,
               e.projects_handled, e.satisfaction_score, e.dataset_upload_id,
               du.filename AS dataset_filename,
               GROUP_CONCAT(DISTINCT s.name ORDER BY s.name SEPARATOR ';') AS skills,
               GROUP_CONCAT(DISTINCT c.name ORDER BY c.name SEPARATOR ';') AS certifications
        FROM employees e
        JOIN dataset_uploads du ON e.dataset_upload_id = du.id AND du.is_active = TRUE
        {owner_filter}
        LEFT JOIN employee_skills es ON e.id = es.employee_id
        LEFT JOIN skills s ON es.skill_id = s.id
        LEFT JOIN employee_certifications ec ON e.id = ec.employee_id
        LEFT JOIN certifications c ON ec.certification_id = c.id
        GROUP BY e.id, du.filename
        ORDER BY e.id
        """,
        tuple(params),
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
    return execute_query(
        "SELECT * FROM users WHERE username = %s AND is_active = TRUE",
        (username,),
        fetch_one=True,
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
                "ALTER TABLE users ADD COLUMN created_by INT NULL",
                "ALTER TABLE users ADD COLUMN created_from_upload BOOLEAN DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN account_created BOOLEAN DEFAULT FALSE",
            ):
                try:
                    cursor.execute(column_sql)
                except Exception:
                    pass
            for stmt in (
                "CREATE INDEX idx_users_company_email ON users(company_email)",
                "CREATE INDEX idx_users_source_dataset ON users(source_dataset_id)",
                "CREATE INDEX idx_users_created_by ON users(created_by)",
            ):
                try:
                    cursor.execute(stmt)
                except Exception:
                    pass


def upsert_user_account(user):
    """Persist a generated app user to MySQL without exposing temporary passwords."""
    ensure_enterprise_user_schema()
    return execute_query(
        """
        INSERT INTO users (
            username, email, password_hash, role, employee_id, company_email,
            employee_login_id, first_login, temp_password_expires_at,
            source_dataset_id, source_employee_code, created_by,
            created_from_upload, account_created, is_active
        ) VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
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
            created_by = VALUES(created_by),
            created_from_upload = VALUES(created_from_upload),
            account_created = VALUES(account_created),
            is_active = TRUE
        """,
        (
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
            user.get("created_by"),
            bool(user.get("created_from_upload")),
            bool(user.get("account_created")),
        ),
    )


def upsert_user_accounts(users):
    """Bulk-persist generated app users to MySQL."""
    if not users:
        return 0
    ensure_enterprise_user_schema()
    sql = """
        INSERT INTO users (
            username, email, password_hash, role, employee_id, company_email,
            employee_login_id, first_login, temp_password_expires_at,
            source_dataset_id, source_employee_code, created_by,
            created_from_upload, account_created, is_active
        ) VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
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
            created_by = VALUES(created_by),
            created_from_upload = VALUES(created_from_upload),
            account_created = VALUES(account_created),
            is_active = TRUE
    """
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            for user in users:
                cursor.execute(
                    sql,
                    (
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
                        user.get("created_by"),
                        bool(user.get("created_from_upload")),
                        bool(user.get("account_created")),
                    ),
                )
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
    params = []
    owner_filter = ""
    if uploaded_by is None:
        owner_filter = "AND uploaded_by IS NULL"
    else:
        owner_filter = "AND uploaded_by = %s"
        params.append(uploaded_by)
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
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            for candidate in candidates:
                employee_code = candidate["employee_code"]
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
                        candidate.get("designation", "Employee"),
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

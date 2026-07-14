"""
Seed TalentBeacon MySQL database from employee CSV and initialize roles/skills/courses.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql
import config
from werkzeug.security import generate_password_hash
from src.preprocessing import preprocess_data
from src.db.connection import get_db_connection


ROLE_DEFINITIONS = {
    "Data Analyst": {
        "required": ["SQL", "Excel", "Power BI", "Statistics", "Python"],
        "desired": ["Machine Learning", "Tableau", "Data Visualization"],
    },
    "Data Scientist": {
        "required": ["Python", "Statistics", "Machine Learning", "SQL", "Pandas"],
        "desired": ["Deep Learning", "TensorFlow", "PyTorch", "NLP"],
    },
    "Full Stack Developer": {
        "required": ["JavaScript", "HTML", "CSS", "React", "Node.js", "SQL"],
        "desired": ["TypeScript", "Docker", "AWS"],
    },
    "Cloud Engineer": {
        "required": ["AWS", "Docker", "Linux", "Terraform", "Python"],
        "desired": ["Kubernetes", "Azure", "GCP"],
    },
    "Machine Learning Engineer": {
        "required": ["Python", "Machine Learning", "TensorFlow", "SQL", "Docker"],
        "desired": ["PyTorch", "AWS", "Spark"],
    },
    "Cybersecurity Analyst": {
        "required": ["Linux", "Python", "Networking", "Security"],
        "desired": ["CISSP", "Cloud Security"],
    },
}

SKILL_CATEGORIES = {
    "Python": "technical", "Java": "technical", "React": "technical", "AWS": "technical",
    "Docker": "technical", "SQL": "technical", "JavaScript": "technical", "HTML": "technical",
    "CSS": "technical", "Node.js": "technical", "TypeScript": "technical", "Git": "technical",
    "PostgreSQL": "technical", "MySQL": "technical", "MongoDB": "technical", "Kubernetes": "technical",
    "Terraform": "technical", "Linux": "technical", "C++": "technical", "C": "technical",
    "Machine Learning": "technical", "Deep Learning": "technical", "NLP": "technical",
    "TensorFlow": "technical", "PyTorch": "technical", "Scikit-Learn": "technical",
    "Power BI": "analytics", "Tableau": "analytics", "Statistics": "analytics",
    "Excel": "analytics", "Pandas": "analytics", "NumPy": "analytics", "Data Science": "analytics",
    "Communication": "soft", "Leadership": "soft", "Presentation": "soft",
    "React.js": "technical", "Vue.js": "technical", "Express": "technical",
    "Ruby": "technical", "Ruby on Rails": "technical", "PHP": "technical", "Laravel": "technical",
    "Angular": "technical", "Flutter": "technical", "Spark": "technical", "Hadoop": "technical",
    "Azure": "technical", "GCP": "technical", "Google Cloud": "technical", "Bash/Shell": "technical",
    "HTML/CSS": "technical", "jQuery": "technical", "Networking": "technical", "Security": "technical",
    "Data Visualization": "analytics", "React Native": "technical", "Spring": "technical",
}


def init_schema():
    from database.init_db import init_schema as _init
    _init()


def get_or_create_skill(cursor, skill_name):
    cursor.execute("SELECT id FROM skills WHERE LOWER(name) = LOWER(%s)", (skill_name,))
    row = cursor.fetchone()
    if row:
        return row["id"] if isinstance(row, dict) else row[0]
    category = SKILL_CATEGORIES.get(skill_name, "other")
    cursor.execute(
        "INSERT INTO skills (name, category) VALUES (%s, %s)",
        (skill_name, category),
    )
    return cursor.lastrowid


def get_or_create_cert(cursor, cert_name):
    cursor.execute("SELECT id FROM certifications WHERE name = %s", (cert_name,))
    row = cursor.fetchone()
    if row:
        return row["id"] if isinstance(row, dict) else row[0]
    cursor.execute("INSERT INTO certifications (name) VALUES (%s)", (cert_name,))
    return cursor.lastrowid


def seed_roles_and_courses(cursor):
    for role_name, spec in ROLE_DEFINITIONS.items():
        cursor.execute("SELECT id FROM roles WHERE name = %s", (role_name,))
        row = cursor.fetchone()
        if row:
            role_id = row["id"] if isinstance(row, dict) else row[0]
        else:
            cursor.execute(
                "INSERT INTO roles (name, description) VALUES (%s, %s)",
                (role_name, f"Target role profile for {role_name}"),
            )
            role_id = cursor.lastrowid

        for skill in spec["required"]:
            sid = get_or_create_skill(cursor, skill)
            cursor.execute(
                """
                INSERT IGNORE INTO role_skills (role_id, skill_id, is_required, min_level)
                VALUES (%s, %s, TRUE, 'intermediate')
                """,
                (role_id, sid),
            )
            cursor.execute(
                """
                INSERT IGNORE INTO learning_resources (title, skill_id, source, url, duration_hours)
                VALUES (%s, %s, 'internal_lms', %s, %s)
                """,
                (
                    f"{skill} Fundamentals",
                    sid,
                    f"https://learn.example.com/{skill.lower().replace(' ', '-')}",
                    8.0,
                ),
            )
        for skill in spec["desired"]:
            sid = get_or_create_skill(cursor, skill)
            cursor.execute(
                """
                INSERT IGNORE INTO role_skills (role_id, skill_id, is_required, min_level)
                VALUES (%s, %s, FALSE, 'beginner')
                """,
                (role_id, sid),
            )


def seed_employees_from_csv():
    csv_path = config.DEFAULT_CSV_PATH
    if not csv_path.exists():
        print(f"No default employee CSV found at {csv_path}. Skipping employee seed.")
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                seed_roles_and_courses(cursor)
        return

    df = preprocess_data(str(csv_path))
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS cnt FROM employees")
            count = cursor.fetchone()
            cnt = count["cnt"] if isinstance(count, dict) else count[0]
            if cnt > 0:
                print(f"Database already has {cnt} employees. Skipping employee seed.")
                seed_roles_and_courses(cursor)
                return

            for _, row in df.iterrows():
                emp_code = str(row["Employee_ID"])
                cursor.execute(
                    """
                    INSERT INTO employees (
                        employee_code, department, designation, years_of_experience,
                        education_level, performance_score, projects_handled,
                        satisfaction_score, hire_date
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        emp_code,
                        row["Department"],
                        row["Job_Title"],
                        int(row["Years_of_Experience"]),
                        row["Education_Level"],
                        int(row["Performance_Score"]),
                        int(row["Projects_Handled"]),
                        float(row["Employee_Satisfaction_Score"]),
                        row["Hire_Date"].date() if hasattr(row["Hire_Date"], "date") else row["Hire_Date"],
                    ),
                )
                emp_id = cursor.lastrowid

                for skill in row["Parsed_Skills"]:
                    sid = get_or_create_skill(cursor, skill)
                    cursor.execute(
                        """
                        INSERT IGNORE INTO employee_skills (employee_id, skill_id, proficiency_level)
                        VALUES (%s, %s, 'intermediate')
                        """,
                        (emp_id, sid),
                    )

                for cert in row["Parsed_Certifications"]:
                    cid = get_or_create_cert(cursor, cert)
                    cursor.execute(
                        """
                        INSERT IGNORE INTO employee_certifications (employee_id, certification_id)
                        VALUES (%s, %s)
                        """,
                        (emp_id, cid),
                    )

            seed_roles_and_courses(cursor)
            print(f"Seeded {len(df)} employees.")


def seed_users():
    default_users = [
        ("admin", "admin@talentbeacon.com", "admin123", "admin", None),
        ("manager", "manager@talentbeacon.com", "manager123", "manager", None),
        ("employee", "employee@talentbeacon.com", "employee123", "employee", 1),
    ]
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            for username, email, password, role, emp_id in default_users:
                cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
                if cursor.fetchone():
                    continue
                cursor.execute(
                    """
                    INSERT INTO users (username, email, password_hash, role, employee_id)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (username, email, generate_password_hash(password), role, emp_id),
                )
    print("Default users seeded: admin/admin123, manager/manager123, employee/employee123")


if __name__ == "__main__":
    print("Initializing TalentBeacon database...")
    init_schema()
    seed_employees_from_csv()
    seed_users()
    print("Database seed complete. Upload employee data from the Employee Files page.")

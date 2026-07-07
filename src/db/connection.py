import pymysql
from pymysql.cursors import DictCursor
from contextlib import contextmanager
import config


def get_connection():
    return pymysql.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


@contextmanager
def get_db_connection():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_query(sql, params=None, fetch_one=False, fetch_all=True):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or ())
            if sql.strip().upper().startswith(("SELECT", "SHOW", "DESCRIBE")):
                if fetch_one:
                    return cursor.fetchone()
                if fetch_all:
                    return cursor.fetchall()
            return cursor.lastrowid


def execute_many(sql, params_list):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(sql, params_list)
            return cursor.rowcount

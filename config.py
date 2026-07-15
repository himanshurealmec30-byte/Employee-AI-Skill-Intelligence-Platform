import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
APP_ENV = os.getenv("APP_ENV", os.getenv("NODE_ENV", "development")).lower()
IS_PRODUCTION = APP_ENV in {"production", "prod"}

# MySQL Configuration
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost").strip()
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "root").strip()
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "himanshu12345")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "talentbeacon").strip()

_MYSQL_PLACEHOLDERS = {
    "",
    "your-mysql-host",
    "your_mysql_host",
    "your-db-host",
    "your-railway-host",
}
_MYSQL_PASSWORD_PLACEHOLDERS = {
    "",
    "your-mysql-password",
    "your_mysql_password",
    "paste_your_real_railway_password_here",
}
MYSQL_CONFIG_VALID = (
    MYSQL_HOST.lower() not in _MYSQL_PLACEHOLDERS
    and MYSQL_USER.lower() not in {"", "your-mysql-user", "your_mysql_user"}
    and MYSQL_PASSWORD.lower() not in _MYSQL_PASSWORD_PLACEHOLDERS
    and MYSQL_DATABASE.lower() not in {"", "your-mysql-database", "your_mysql_database"}
)
MYSQL_READS_REQUESTED = os.getenv("MYSQL_READS_ENABLED", "1").lower() not in {"0", "false", "no"}
MYSQL_READS_ENABLED = MYSQL_READS_REQUESTED and MYSQL_CONFIG_VALID

SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
)

SECRET_KEY = os.getenv("SECRET_KEY", "talentbeacon-dev-secret-change-in-production")
if IS_PRODUCTION and SECRET_KEY == "talentbeacon-dev-secret-change-in-production":
    raise RuntimeError("Set a strong SECRET_KEY before running TalentBeacon in production.")
DEFAULT_CSV_PATH = Path(os.getenv("DEFAULT_CSV_PATH", BASE_DIR / "sample_employee_dataset.csv"))
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", BASE_DIR / "uploads"))
DATASET_UPLOAD_DIR = UPLOADS_DIR / "datasets"
DATASET_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
CSRF_ENABLED = os.getenv("CSRF_ENABLED", "1" if IS_PRODUCTION else "0").lower() not in {"0", "false", "no"}
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "1").lower() not in {"0", "false", "no"}

# ML model paths
READINESS_MODEL_PATH = MODELS_DIR / "readiness_xgb.pkl"
READINESS_RF_PATH = MODELS_DIR / "readiness_rf.pkl"
READINESS_LR_PATH = MODELS_DIR / "readiness_lr.pkl"
TFIDF_SKILL_MODEL_PATH = MODELS_DIR / "skill_tfidf.pkl"
SKILL_VOCAB_PATH = MODELS_DIR / "skill_vocab.json"
TRAINING_METRICS_PATH = MODELS_DIR / "training_metrics.json"
MODEL_REGISTRY_PATH = MODELS_DIR / "model_registry.json"

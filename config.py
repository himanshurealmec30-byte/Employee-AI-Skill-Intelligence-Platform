import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# MySQL Configuration
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "9552087105")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "talentbeacon")
MYSQL_READS_ENABLED = os.getenv("MYSQL_READS_ENABLED", "1").lower() not in {"0", "false", "no"}

SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
)

SECRET_KEY = os.getenv("SECRET_KEY", "talentbeacon-dev-secret-change-in-production")
DEFAULT_CSV_PATH = BASE_DIR / "employee management system cleaned data output2.csv"
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = BASE_DIR / "uploads"
DATASET_UPLOAD_DIR = UPLOADS_DIR / "datasets"
DATASET_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ML model paths
READINESS_MODEL_PATH = MODELS_DIR / "readiness_xgb.pkl"
READINESS_RF_PATH = MODELS_DIR / "readiness_rf.pkl"
READINESS_LR_PATH = MODELS_DIR / "readiness_lr.pkl"
TFIDF_SKILL_MODEL_PATH = MODELS_DIR / "skill_tfidf.pkl"
SKILL_VOCAB_PATH = MODELS_DIR / "skill_vocab.json"
TRAINING_METRICS_PATH = MODELS_DIR / "training_metrics.json"
MODEL_REGISTRY_PATH = MODELS_DIR / "model_registry.json"

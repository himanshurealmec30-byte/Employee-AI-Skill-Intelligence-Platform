"""
TalentBeacon ML & NLP Training Pipeline
Trains readiness prediction models (XGBoost, Random Forest, Logistic Regression)
and NLP skill embedding (TF-IDF) models.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config
from src.preprocessing import preprocess_data
from src.nlp.skill_embedder import train_nlp_models
from src.ml.readiness_trainer import train_readiness_models
from src.db.repository import log_ml_training


def _append_model_registry(record):
    registry_path = config.MODEL_REGISTRY_PATH
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else []
        if not isinstance(registry, list):
            registry = []
    except Exception:
        registry = []
    registry.insert(0, record)
    registry_path.write_text(json.dumps(registry[:25], indent=2), encoding="utf-8")


def main():
    print("=" * 60)
    print("TalentBeacon ML & NLP Training Pipeline")
    print("=" * 60)

    csv_path = config.DEFAULT_CSV_PATH
    if not csv_path.exists():
        print(f"ERROR: Dataset not found at {csv_path}")
        sys.exit(1)

    print("\n[1/3] Loading and preprocessing employee data...")
    df = preprocess_data(str(csv_path))
    print(f"      Loaded {len(df)} employees, {df['Parsed_Skills'].apply(len).sum()} skill records")

    print("\n[2/3] Training NLP Skill Embedding (TF-IDF)...")
    embedder, nlp_metrics = train_nlp_models(df=df)
    print(f"      Vocabulary: {nlp_metrics['vocabulary_size']} skills")
    print(f"      TF-IDF features: {nlp_metrics['tfidf_features']}")
    print(f"      Sample similarity: {nlp_metrics['sample_top_similarity']:.3f}")

    print("\n[3/3] Training Readiness Prediction Models...")
    trainer, ml_metrics = train_readiness_models(df=df)
    for model_name, metrics in ml_metrics.items():
        if isinstance(metrics, dict):
            print(f"      {model_name}: {metrics}")

    trained_at = datetime.now(timezone.utc).isoformat()
    version = datetime.now(timezone.utc).strftime("v%Y%m%d%H%M%S")
    all_metrics = {
        "version": version,
        "trained_at": trained_at,
        "dataset": str(csv_path),
        "nlp": nlp_metrics,
        "ml": ml_metrics,
    }
    config.TRAINING_METRICS_PATH.write_text(json.dumps(all_metrics, indent=2), encoding="utf-8")
    _append_model_registry({
        "version": version,
        "trained_at": trained_at,
        "dataset": str(csv_path),
        "models": list(ml_metrics.keys()),
        "nlp_vocabulary_size": nlp_metrics.get("vocabulary_size"),
        "best_accuracy": ml_metrics.get("xgboost_classifier", {}).get("accuracy", 0),
        "best_f1": ml_metrics.get("xgboost_classifier", {}).get("f1", 0),
        "best_rmse": ml_metrics.get("xgboost_regressor", {}).get("rmse", 0),
    })

    try:
        best_acc = ml_metrics.get("xgboost_classifier", {}).get("accuracy", 0)
        best_f1 = ml_metrics.get("xgboost_classifier", {}).get("f1", 0)
        best_rmse = ml_metrics.get("xgboost_regressor", {}).get("rmse", 0)
        log_ml_training(f"readiness_xgb_{version}", "XGBoost", best_acc, best_f1, best_rmse, all_metrics)
    except Exception as e:
        print(f"      (DB log skipped: {e})")

    print("\n" + "=" * 60)
    print("Training complete! Models saved to:", config.MODELS_DIR)
    print("=" * 60)


if __name__ == "__main__":
    main()

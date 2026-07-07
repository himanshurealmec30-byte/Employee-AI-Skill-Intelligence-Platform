"""
ML Readiness Prediction Model Training
Trains Random Forest, XGBoost, and Logistic Regression for role readiness.
"""
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, MultiLabelBinarizer, StandardScaler
from xgboost import XGBClassifier, XGBRegressor

import config
from src.utils.skills import normalize_skill_key


LEVEL_MAP = {"beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}


class ReadinessModelTrainer:
    """Trains ML models to predict employee readiness for target roles."""

    def __init__(self):
        self.mlb = MultiLabelBinarizer()
        self.role_encoder = LabelEncoder()
        self.feature_cols = []
        self.models = {}
        self.role_names = []

    def _build_training_data(self, df, role_definitions):
        """
        Build supervised training dataset.
        Label (readiness) = weighted combination of skill overlap, experience, performance.
        """
        records = []
        all_skills = sorted(set(s for skills in df["Parsed_Skills"] for s in skills))
        self.mlb.fit([all_skills])
        self.role_names = sorted(role_definitions.keys())

        for role_name, spec in role_definitions.items():
            required = {normalize_skill_key(s) for s in spec["required"]}
            desired = {normalize_skill_key(s) for s in spec.get("desired", [])}
            all_role_skills = required | desired

            for _, row in df.iterrows():
                emp_skills = {normalize_skill_key(s) for s in row["Parsed_Skills"]}
                matched_req = len(emp_skills & required)
                matched_des = len(emp_skills & desired)
                req_ratio = matched_req / max(len(required), 1)
                des_ratio = matched_des / max(len(desired), 1) if desired else 0.5

                exp_score = min(1.0, row["Years_of_Experience"] / 8.0)
                perf_score = row["Performance_Score"] / 5.0
                proj_score = min(1.0, row["Projects_Handled"] / 40.0)
                cert_bonus = min(0.15, len(row["Parsed_Certifications"]) * 0.03)

                readiness = (
                    0.45 * req_ratio + 0.15 * des_ratio +
                    0.20 * exp_score + 0.15 * perf_score +
                    0.05 * proj_score + cert_bonus
                )
                readiness = min(1.0, readiness)

                skill_vec = self.mlb.transform([row["Parsed_Skills"]])[0]
                records.append({
                    "role": role_name,
                    "employee_id": row["Employee_ID"],
                    "years_of_experience": row["Years_of_Experience"],
                    "performance_score": row["Performance_Score"],
                    "projects_handled": row["Projects_Handled"],
                    "satisfaction_score": row["Employee_Satisfaction_Score"],
                    "num_certifications": len(row["Parsed_Certifications"]),
                    "num_skills": len(row["Parsed_Skills"]),
                    "req_match_ratio": req_ratio,
                    "des_match_ratio": des_ratio,
                    "readiness_score": readiness,
                    "ready_label": 1 if readiness >= 0.70 else 0,
                    **{f"role_{r}": 1 if r == role_name else 0 for r in self.role_names},
                    **{f"skill_{i}": skill_vec[i] for i in range(len(skill_vec))},
                })

        train_df = pd.DataFrame(records)
        self.feature_cols = [
            c for c in train_df.columns
            if c not in ("role", "employee_id", "readiness_score", "ready_label")
        ]
        return train_df

    def train(self, df, role_definitions):
        train_df = self._build_training_data(df, role_definitions)
        X = train_df[self.feature_cols].values
        y_reg = train_df["readiness_score"].values
        y_cls = train_df["ready_label"].values
        stratify = y_cls if len(np.unique(y_cls)) > 1 else None

        X_train, X_test, y_train_reg, y_test_reg, y_train_cls, y_test_cls = train_test_split(
            X, y_reg, y_cls, test_size=0.2, random_state=42, stratify=stratify
        )

        metrics = {}

        # XGBoost Regressor for readiness percentage
        xgb_reg = XGBRegressor(
            n_estimators=350, max_depth=5, learning_rate=0.05,
            subsample=0.85, colsample_bytree=0.85, random_state=42,
            objective="reg:squarederror",
        )
        xgb_reg.fit(X_train, y_train_reg)
        xgb_pred = xgb_reg.predict(X_test)
        metrics["xgboost_regressor"] = {
            "mae": float(mean_absolute_error(y_test_reg, xgb_pred)),
            "rmse": float(np.sqrt(mean_squared_error(y_test_reg, xgb_pred))),
            "r2": float(r2_score(y_test_reg, xgb_pred)),
        }
        reg_cv = cross_validate(
            xgb_reg, X, y_reg, cv=5,
            scoring=("neg_mean_absolute_error", "neg_root_mean_squared_error", "r2"),
            n_jobs=None,
        )
        metrics["xgboost_regressor_cv"] = {
            "mae_mean": float(-reg_cv["test_neg_mean_absolute_error"].mean()),
            "rmse_mean": float(-reg_cv["test_neg_root_mean_squared_error"].mean()),
            "r2_mean": float(reg_cv["test_r2"].mean()),
        }
        self.models["xgb_regressor"] = xgb_reg

        # Random Forest Classifier for ready/not-ready
        rf_cls = RandomForestClassifier(
            n_estimators=300,
            max_depth=14,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        rf_cls.fit(X_train, y_train_cls)
        rf_pred = rf_cls.predict(X_test)
        metrics["random_forest_classifier"] = {
            "accuracy": float(accuracy_score(y_test_cls, rf_pred)),
            "f1": float(f1_score(y_test_cls, rf_pred, zero_division=0)),
        }
        rf_cv = cross_validate(rf_cls, X, y_cls, cv=5, scoring=("accuracy", "f1"), n_jobs=None)
        metrics["random_forest_classifier_cv"] = {
            "accuracy_mean": float(rf_cv["test_accuracy"].mean()),
            "f1_mean": float(rf_cv["test_f1"].mean()),
        }
        self.models["rf_classifier"] = rf_cls

        # Logistic Regression baseline
        lr_cls = Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(
                max_iter=2000,
                class_weight="balanced",
                random_state=42,
            )),
        ])
        lr_cls.fit(X_train, y_train_cls)
        lr_pred = lr_cls.predict(X_test)
        metrics["logistic_regression"] = {
            "accuracy": float(accuracy_score(y_test_cls, lr_pred)),
            "f1": float(f1_score(y_test_cls, lr_pred, zero_division=0)),
        }
        self.models["lr_classifier"] = lr_cls

        # XGBoost Classifier
        positives = max(1, int(y_train_cls.sum()))
        negatives = max(1, int(len(y_train_cls) - y_train_cls.sum()))
        xgb_cls = XGBClassifier(
            n_estimators=250,
            max_depth=4,
            learning_rate=0.06,
            subsample=0.85,
            colsample_bytree=0.85,
            random_state=42,
            eval_metric="logloss",
            scale_pos_weight=negatives / positives,
        )
        xgb_cls.fit(X_train, y_train_cls)
        xgb_cls_pred = xgb_cls.predict(X_test)
        metrics["xgboost_classifier"] = {
            "accuracy": float(accuracy_score(y_test_cls, xgb_cls_pred)),
            "f1": float(f1_score(y_test_cls, xgb_cls_pred, zero_division=0)),
        }
        xgb_cls_cv = cross_validate(xgb_cls, X, y_cls, cv=5, scoring=("accuracy", "f1"), n_jobs=None)
        metrics["xgboost_classifier_cv"] = {
            "accuracy_mean": float(xgb_cls_cv["test_accuracy"].mean()),
            "f1_mean": float(xgb_cls_cv["test_f1"].mean()),
        }
        self.models["xgb_classifier"] = xgb_cls

        metrics["training_samples"] = len(train_df)
        metrics["feature_count"] = len(self.feature_cols)
        importances = getattr(xgb_reg, "feature_importances_", None)
        if importances is not None:
            top_idx = np.argsort(importances)[::-1][:12]
            metrics["top_regression_features"] = [
                {
                    "feature": self._display_feature_name(self.feature_cols[i]),
                    "importance": float(importances[i]),
                }
                for i in top_idx
            ]
        return metrics

    def _display_feature_name(self, feature_name):
        if feature_name.startswith("skill_"):
            try:
                skill_idx = int(feature_name.split("_", 1)[1])
                return f"skill:{self.mlb.classes_[skill_idx]}"
            except (ValueError, IndexError):
                return feature_name
        if feature_name.startswith("role_"):
            return "role:" + feature_name.replace("role_", "", 1)
        return feature_name

    def save(self):
        Path(config.MODELS_DIR).mkdir(parents=True, exist_ok=True)
        bundle = {
            "models": self.models,
            "mlb": self.mlb,
            "feature_cols": self.feature_cols,
            "role_names": self.role_names,
        }
        with open(config.READINESS_MODEL_PATH, "wb") as f:
            pickle.dump(bundle, f)
        with open(config.READINESS_RF_PATH, "wb") as f:
            pickle.dump(self.models["rf_classifier"], f)
        with open(config.READINESS_LR_PATH, "wb") as f:
            pickle.dump(self.models["lr_classifier"], f)

    @classmethod
    def load(cls):
        with open(config.READINESS_MODEL_PATH, "rb") as f:
            bundle = pickle.load(f)
        trainer = cls()
        trainer.models = bundle["models"]
        trainer.mlb = bundle["mlb"]
        trainer.feature_cols = bundle["feature_cols"]
        trainer.role_names = bundle.get("role_names", [])
        return trainer

    def predict_readiness(self, employee_features: dict):
        """Predict readiness score (0-100%) for an employee."""
        xgb_reg = self.models.get("xgb_regressor")
        if xgb_reg is None:
            return employee_features.get("req_match_ratio", 0) * 100

        role_name = employee_features.get("role_name")
        if role_name:
            for r in self.role_names:
                employee_features.setdefault(f"role_{r}", 1 if r == role_name else 0)

        row = [employee_features.get(c, 0) for c in self.feature_cols]
        score = float(xgb_reg.predict([row])[0])
        return round(min(100, max(0, score * 100)), 1)


def train_readiness_models(df=None, role_definitions=None):
    from database.seed import ROLE_DEFINITIONS
    if df is None:
        from src.preprocessing import preprocess_data
        df = preprocess_data(str(config.DEFAULT_CSV_PATH))
    if role_definitions is None:
        role_definitions = ROLE_DEFINITIONS

    trainer = ReadinessModelTrainer()
    metrics = trainer.train(df, role_definitions)
    trainer.save()
    return trainer, metrics

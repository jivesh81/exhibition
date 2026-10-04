"""
SafeSight AI — ML Training Pipeline
===================================
Complete training pipeline for the hybrid risk model.

Datasets supported:
- SHWD (Safety Helmet Wearing Dataset)
- Hard Hat Workers Dataset
- PPE Detection Datasets (helmet, vest, person)
- Custom workplace safety datasets

Usage:
    python -m ml.train --dataset shwd --model lightgbm
    python -m ml.evaluate --model artifacts/hybrid_risk_model.pkl
"""

import os
import json
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

try:
    import lightgbm as lgb
    _LGB_AVAILABLE = True
except ImportError:
    _LGB_AVAILABLE = False

try:
    import xgboost as xgb
    _XGB_AVAILABLE = True
except ImportError:
    _XGB_AVAILABLE = False

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report
)
from sklearn.utils.class_weight import compute_class_weight
import joblib

from .features import FeatureExtractor, WorkerFeatures, WORKER_FEATURES, FEATURE_METADATA
from .model import HybridRiskModel, ModelMetadata, MODEL_PATH, SCALER_PATH, METADATA_PATH


# Dataset configurations
DATASET_CONFIGS = {
    "shwd": {
        "name": "SHWD - Safety Helmet Wearing Dataset",
        "source": "https://github.com/njvisionpower/Safety-Helmet-Wearing-Dataset",
        "license": "CC BY 4.0",
        "description": "Images of workers with/without safety helmets. ~5000 images.",
        "classes": ["helmet", "no-helmet", "person"],
        "splits": {"train": 0.7, "val": 0.15, "test": 0.15},
    },
    "hardhat": {
        "name": "Hard Hat Workers Dataset",
        "source": "https://www.kaggle.com/datasets/andrewmvd/hard-hat-workers",
        "license": "CC0: Public Domain",
        "description": "Hard hat detection in construction sites. ~3000 images.",
        "classes": ["hardhat", "person", "head"],
        "splits": {"train": 0.7, "val": 0.15, "test": 0.15},
    },
    "ppe_voc": {
        "name": "PPE Detection VOC Dataset",
        "source": "https://github.com/ultralytics/ultralytics/tree/main/datasets/ppe",
        "license": "AGPL-3.0",
        "description": "PPE detection (helmet, vest, gloves, boots). VOC format.",
        "classes": ["helmet", "vest", "gloves", "boots", "person"],
        "splits": {"train": 0.8, "val": 0.1, "test": 0.1},
    },
    "synthetic": {
        "name": "Synthetic Workplace Safety Dataset",
        "source": "Generated from simulation",
        "license": "Internal",
        "description": "Synthetic data from SafeSight demo engine for baseline training.",
        "classes": ["helmet", "vest", "gloves", "person"],
        "splits": {"train": 0.8, "val": 0.1, "test": 0.1},
    },
}


@dataclass
class TrainingConfig:
    """Training configuration."""
    model_type: str = "lightgbm"  # lightgbm, xgboost, random_forest, gradient_boosting, logistic
    dataset: str = "synthetic"
    data_path: Optional[str] = None
    test_size: float = 0.2
    val_size: float = 0.1
    random_seed: int = 42
    n_estimators: int = 200
    max_depth: int = 8
    learning_rate: float = 0.05
    class_weight: str = "balanced"
    cv_folds: int = 5
    early_stopping_rounds: int = 20
    output_dir: str = "artifacts"


class DatasetLoader:
    """Load and prepare datasets for training."""

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.feature_extractor = FeatureExtractor()

    def load_synthetic(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate synthetic training data from the demo engine scenarios.
        This creates realistic feature vectors with known risk labels.
        """
        np.random.seed(self.config.random_seed)
        n_samples = 10000

        X = []
        y = []  # 0 = safe, 1 = unsafe (HIGH/CRITICAL)

        for _ in range(n_samples):
            # Random worker state
            helmet = np.random.choice([0, 1], p=[0.1, 0.9])
            vest = np.random.choice([0, 1], p=[0.05, 0.95])
            gloves = np.random.choice([0, 1], p=[0.2, 0.8])

            posture = np.random.choice([0, 1, 2], p=[0.7, 0.2, 0.1])
            in_zone = np.random.choice([0, 1], p=[0.6, 0.4])

            if in_zone:
                zone_sev = np.random.choice([0, 1, 2, 3], p=[0.1, 0.2, 0.4, 0.3])
                distance = np.random.uniform(0.5, 10.0)
            else:
                zone_sev = 0
                distance = np.random.uniform(10.0, 50.0)

            closing_speed = np.random.exponential(0.5) if in_zone else np.random.exponential(0.1)
            facing_hazard = np.random.choice([0, 1], p=[0.7, 0.3])
            exposure = np.random.exponential(5.0) if in_zone else 0
            movement_speed = np.random.exponential(0.5)
            ppe_conf = np.random.beta(8, 2)
            posture_conf = np.random.beta(8, 2)
            hazard_conf = np.random.beta(7, 3)
            hist_risk = np.random.uniform(0, 30)
            recent_inc = np.random.poisson(0.5)

            # Create feature vector
            features = WorkerFeatures(
                worker_id=f"W-{np.random.randint(1, 100):03d}",
                worker_id_hash=np.random.randint(0, 999999),
                helmet_present=helmet,
                vest_present=vest,
                gloves_present=gloves,
                ppe_confidence=ppe_conf,
                posture_encoded=posture,
                posture_confidence=posture_conf,
                distance_to_hazard=distance,
                closing_speed=min(closing_speed, 5.0),
                inside_hazard_zone=in_zone,
                zone_severity_encoded=zone_sev,
                facing_hazard=facing_hazard,
                exposure_duration=min(exposure, 60.0),
                movement_speed=min(movement_speed, 5.0),
                hazard_confidence=hazard_conf,
                historical_risk=hist_risk,
                recent_incident_count=min(recent_inc, 10),
            )

            # Compute rule-based risk for labeling
            from risk_engine import assess_risk
            rule_result = assess_risk({
                "ppe": {"helmet": bool(helmet), "vest": bool(vest), "gloves": bool(gloves)},
                "distance": distance if in_zone else None,
                "in_zone": bool(in_zone),
                "zone_severity": ["safe", "warning", "danger", "critical"][zone_sev],
                "facing_hazard": bool(facing_hazard),
                "facing_away": False,
                "closing_speed": closing_speed,
                "posture": ["Normal", "Unsafe", "Severe"][posture],
            })

            # Label: unsafe if rule says HIGH or CRITICAL
            is_unsafe = 1 if rule_result["severity"] in ("HIGH", "CRITICAL") else 0

            X.append(features.to_array())
            y.append(is_unsafe)

        return np.array(X), np.array(y)

    def load_from_csv(self, path: str) -> Tuple[np.ndarray, np.ndarray]:
        """Load features from CSV file."""
        df = pd.read_csv(path)
        # Expect columns matching WORKER_FEATURES + 'label'
        feature_cols = [c for c in WORKER_FEATURES if c in df.columns]
        X = df[feature_cols].values
        y = df['label'].values if 'label' in df.columns else df['risk_level'].values
        return X, y

    def load_dataset(self) -> Tuple[np.ndarray, np.ndarray]:
        """Load dataset based on config."""
        if self.config.dataset == "synthetic":
            return self.load_synthetic()
        elif self.config.data_path and os.path.exists(self.config.data_path):
            return self.load_from_csv(self.config.data_path)
        else:
            # Try to find dataset in standard locations
            for base in ["data", "datasets", "../data", "../datasets"]:
                path = Path(base) / self.config.dataset / "features.csv"
                if path.exists():
                    return self.load_from_csv(str(path))
            raise FileNotFoundError(f"Dataset {self.config.dataset} not found. Use --data-path or run synthetic.")


class ModelTrainer:
    """Train the hybrid risk model."""

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.model = None
        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()
        self.metrics = {}

    def create_model(self):
        """Create model instance based on config."""
        if self.config.model_type == "lightgbm":
            if not _LGB_AVAILABLE:
                raise ImportError("lightgbm not installed. pip install lightgbm")
            return lgb.LGBMClassifier(
                n_estimators=self.config.n_estimators,
                max_depth=self.config.max_depth,
                learning_rate=self.config.learning_rate,
                class_weight=self.config.class_weight,
                random_state=self.config.random_seed,
                verbose=-1,
            )
        elif self.config.model_type == "xgboost":
            if not _XGB_AVAILABLE:
                raise ImportError("xgboost not installed. pip install xgboost")
            return xgb.XGBClassifier(
                n_estimators=self.config.n_estimators,
                max_depth=self.config.max_depth,
                learning_rate=self.config.learning_rate,
                random_state=self.config.random_seed,
                eval_metric="logloss",
                verbosity=0,
            )
        elif self.config.model_type == "random_forest":
            return RandomForestClassifier(
                n_estimators=self.config.n_estimators,
                max_depth=self.config.max_depth,
                class_weight=self.config.class_weight,
                random_state=self.config.random_seed,
                n_jobs=-1,
            )
        elif self.config.model_type == "gradient_boosting":
            return GradientBoostingClassifier(
                n_estimators=self.config.n_estimators,
                max_depth=self.config.max_depth,
                learning_rate=self.config.learning_rate,
                random_state=self.config.random_seed,
            )
        elif self.config.model_type == "logistic":
            return LogisticRegression(
                class_weight=self.config.class_weight,
                random_state=self.config.random_seed,
                max_iter=1000,
            )
        else:
            raise ValueError(f"Unknown model type: {self.config.model_type}")

    def train(self, X: np.ndarray, y: np.ndarray) -> Dict:
        """Train the model with validation."""
        print(f"[Training] Dataset shape: {X.shape}, Labels: {np.bincount(y)}")

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=self.config.test_size, random_state=self.config.random_seed, stratify=y
        )
        X_train, X_val, y_train, y_val = train_test_split(
            X_train, y_train, test_size=self.config.val_size/(1-self.config.test_size),
            random_state=self.config.random_seed, stratify=y_train
        )

        print(f"[Training] Train: {X_train.shape}, Val: {X_val.shape}, Test: {X_test.shape}")

        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_val_scaled = self.scaler.transform(X_val)
        X_test_scaled = self.scaler.transform(X_test)

        # Create and train model
        self.model = self.create_model()

        if self.config.model_type == "lightgbm":
            # Use early stopping with callbacks (new API)
            try:
                self.model.fit(
                    X_train_scaled, y_train,
                    eval_set=[(X_val_scaled, y_val)],
                    callbacks=[lgb.early_stopping(self.config.early_stopping_rounds), lgb.log_evaluation(0)],
                )
            except TypeError:
                # Fallback for older API
                self.model.fit(
                    X_train_scaled, y_train,
                    eval_set=[(X_val_scaled, y_val)],
                    early_stopping_rounds=self.config.early_stopping_rounds,
                    verbose=False,
                )
        elif self.config.model_type == "xgboost":
            self.model.fit(
                X_train_scaled, y_train,
                eval_set=[(X_val_scaled, y_val)],
                early_stopping_rounds=self.config.early_stopping_rounds,
                verbose=False,
            )
        else:
            self.model.fit(X_train_scaled, y_train)

        # Evaluate
        self.metrics = self.evaluate(X_test_scaled, y_test, "test")
        val_metrics = self.evaluate(X_val_scaled, y_val, "val")

        print(f"[Training] Test Accuracy: {self.metrics['accuracy']:.4f}")
        print(f"[Training] Test F1: {self.metrics['f1']:.4f}")
        print(f"[Training] Test ROC-AUC: {self.metrics['roc_auc']:.4f}")
        print(f"[Training] Test Precision: {self.metrics['precision']:.4f}")
        print(f"[Training] Test Recall: {self.metrics['recall']:.4f}")

        # Cross-validation
        cv_scores = cross_val_score(
            self.create_model(), self.scaler.transform(X), y,
            cv=StratifiedKFold(n_splits=self.config.cv_folds, shuffle=True, random_state=self.config.random_seed),
            scoring='f1'
        )
        print(f"[Training] CV F1: {cv_scores.mean():.4f} (+/- {cv_scores.std()*2:.4f})")
        self.metrics["cv_f1_mean"] = cv_scores.mean()
        self.metrics["cv_f1_std"] = cv_scores.std()

        return self.metrics

    def evaluate(self, X: np.ndarray, y: np.ndarray, split: str) -> Dict:
        """Evaluate model on data."""
        y_pred = self.model.predict(X)
        y_proba = self.model.predict_proba(X)[:, 1] if hasattr(self.model, "predict_proba") else y_pred

        metrics = {
            "split": split,
            "accuracy": accuracy_score(y, y_pred),
            "precision": precision_score(y, y_pred, zero_division=0),
            "recall": recall_score(y, y_pred, zero_division=0),
            "f1": f1_score(y, y_pred, zero_division=0),
            "roc_auc": roc_auc_score(y, y_proba) if len(np.unique(y)) > 1 else 0.5,
        }

        cm = confusion_matrix(y, y_pred)
        metrics["confusion_matrix"] = cm.tolist()
        metrics["classification_report"] = classification_report(y, y_pred, output_dict=True, zero_division=0)

        print(f"\n[{split.upper()} Confusion Matrix]")
        print(cm)
        print(f"\n[{split.upper()} Classification Report]")
        print(classification_report(y, y_pred, zero_division=0))

        return metrics

    def save(self, output_dir: str, metadata: ModelMetadata):
        """Save model, scaler, and metadata."""
        os.makedirs(output_dir, exist_ok=True)
        model_path = os.path.join(output_dir, "hybrid_risk_model.pkl")
        scaler_path = os.path.join(output_dir, "feature_scaler.pkl")
        meta_path = os.path.join(output_dir, "model_metadata.json")

        joblib.dump(self.model, model_path)
        joblib.dump(self.scaler, scaler_path)
        with open(meta_path, "w") as f:
            json.dump(asdict(metadata), f, indent=2)

        print(f"[Training] Model saved to {model_path}")
        print(f"[Training] Scaler saved to {scaler_path}")
        print(f"[Training] Metadata saved to {meta_path}")


def train_model(config: TrainingConfig):
    """Main training entry point."""
    print(f"=== SafeSight AI ML Training ===")
    print(f"Model: {config.model_type}")
    print(f"Dataset: {config.dataset}")
    print(f"Output: {config.output_dir}")

    # Load data
    loader = DatasetLoader(config)
    X, y = loader.load_dataset()

    # Train
    trainer = ModelTrainer(config)
    metrics = trainer.train(X, y)

    # Create metadata
    metadata = ModelMetadata(
        model_type=config.model_type,
        version="1.0",
        feature_version="1",
        training_dataset=config.dataset,
        training_date=datetime.now().isoformat(),
        n_features=len(WORKER_FEATURES),
        feature_names=WORKER_FEATURES,
        metrics=metrics,
        thresholds={"safe": 25, "warning": 50, "high": 75, "critical": 100},
    )

    # Save
    trainer.save(config.output_dir, metadata)

    return metrics


def main():
    parser = argparse.ArgumentParser(description="SafeSight AI ML Training")
    parser.add_argument("--model", default="lightgbm", choices=["lightgbm", "xgboost", "random_forest", "gradient_boosting", "logistic"])
    parser.add_argument("--dataset", default="synthetic", choices=list(DATASET_CONFIGS.keys()))
    parser.add_argument("--data-path", type=str, help="Path to custom dataset CSV")
    parser.add_argument("--output-dir", default="artifacts")
    parser.add_argument("--n-estimators", type=int, default=200)
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    config = TrainingConfig(
        model_type=args.model,
        dataset=args.dataset,
        data_path=args.data_path,
        output_dir=args.output_dir,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
        random_seed=args.seed,
    )

    train_model(config)


if __name__ == "__main__":
    main()
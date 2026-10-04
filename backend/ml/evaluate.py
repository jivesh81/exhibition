"""
SafeSight AI — ML Evaluation
============================
Evaluate trained hybrid risk model on test data.
"""

import os
import json
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple
import joblib

from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report,
    precision_recall_curve, roc_curve, auc
)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from .features import WORKER_FEATURES
from .model import ModelMetadata, HybridRiskModel
from .train import DatasetLoader, TrainingConfig, DATASET_CONFIGS


def load_model_artifacts(model_dir: str) -> Tuple[object, object, ModelMetadata]:
    """Load model, scaler, and metadata."""
    model_path = os.path.join(model_dir, "hybrid_risk_model.pkl")
    scaler_path = os.path.join(model_dir, "feature_scaler.pkl")
    meta_path = os.path.join(model_dir, "model_metadata.json")

    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)
    with open(meta_path) as f:
        metadata = ModelMetadata(**json.load(f))

    return model, scaler, metadata


def evaluate_model(model_dir: str, data_path: str = None, dataset: str = "synthetic",
                   output_dir: str = None, plots: bool = True):
    """Evaluate model on test data."""
    print(f"=== SafeSight AI Model Evaluation ===")
    print(f"Model dir: {model_dir}")

    # Load artifacts
    model, scaler, metadata = load_model_artifacts(model_dir)
    print(f"Model: {metadata.model_type} v{metadata.version}")
    print(f"Dataset: {metadata.training_dataset}")
    print(f"Features: {metadata.n_features}")

    # Load test data
    config = TrainingConfig(dataset=dataset, data_path=data_path, random_seed=42)
    loader = DatasetLoader(config)
    X, y = loader.load_dataset()

    # Use same split as training (seed=42)
    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    X_test_scaled = scaler.transform(X_test)

    print(f"\nTest set: {X_test.shape[0]} samples")
    print(f"Class distribution: {np.bincount(y_test)}")

    # Predict
    y_pred = model.predict(X_test_scaled)
    y_proba = model.predict_proba(X_test_scaled)[:, 1] if hasattr(model, "predict_proba") else y_pred

    # Metrics
    metrics = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1": f1_score(y_test, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_test, y_proba) if len(np.unique(y_test)) > 1 else 0.5,
    }

    print(f"\n=== Test Metrics ===")
    for k, v in metrics.items():
        print(f"  {k}: {v:.4f}")

    print(f"\n=== Confusion Matrix ===")
    cm = confusion_matrix(y_test, y_pred)
    print(cm)

    print(f"\n=== Classification Report ===")
    print(classification_report(y_test, y_pred, zero_division=0, target_names=["SAFE", "UNSAFE"]))

    # Per-class metrics
    tn, fp, fn, tp = cm.ravel()
    print(f"\n=== Safety-Critical Metrics ===")
    print(f"  False Negatives (missed unsafe): {fn}")
    print(f"  False Positives (false alarms): {fp}")
    print(f"  True Positives (caught unsafe): {tp}")
    print(f"  True Negatives (correct safe): {tn}")
    print(f"  Sensitivity (Recall): {tp/(tp+fn):.4f}")
    print(f"  Specificity: {tn/(tn+fp):.4f}")
    print(f"  Precision: {tp/(tp+fp):.4f}")
    print(f"  F1 Score: {2*tp/(2*tp+fp+fn):.4f}")

    # Feature importance
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        idx = np.argsort(importances)[::-1]
        print(f"\n=== Feature Importance (Top 10) ===")
        for i in idx[:10]:
            print(f"  {WORKER_FEATURES[i]:30s} {importances[i]:.4f}")

    # Plots
    if plots and output_dir:
        os.makedirs(output_dir, exist_ok=True)
        plot_evaluation(y_test, y_proba, y_pred, output_dir, metadata.model_type)

    return metrics


def plot_evaluation(y_true: np.ndarray, y_proba: np.ndarray, y_pred: np.ndarray,
                    output_dir: str, model_name: str):
    """Generate evaluation plots."""
    # ROC Curve
    fpr, tpr, _ = roc_curve(y_true, y_proba)
    roc_auc = auc(fpr, tpr)

    plt.figure(figsize=(12, 4))

    plt.subplot(1, 3, 1)
    plt.plot(fpr, tpr, label=f'ROC (AUC = {roc_auc:.3f})')
    plt.plot([0, 1], [0, 1], 'k--')
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title('ROC Curve')
    plt.legend()
    plt.grid(True, alpha=0.3)

    # Precision-Recall Curve
    precision, recall, _ = precision_recall_curve(y_true, y_proba)
    pr_auc = auc(recall, precision)

    plt.subplot(1, 3, 2)
    plt.plot(recall, precision, label=f'PR (AUC = {pr_auc:.3f})')
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.title('Precision-Recall Curve')
    plt.legend()
    plt.grid(True, alpha=0.3)

    # Confusion Matrix
    plt.subplot(1, 3, 3)
    cm = confusion_matrix(y_true, y_pred)
    plt.imshow(cm, interpolation='nearest', cmap=plt.cm.Blues)
    plt.title('Confusion Matrix')
    plt.colorbar()
    classes = ['SAFE', 'UNSAFE']
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes)
    plt.yticks(tick_marks, classes)
    thresh = cm.max() / 2.
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            plt.text(j, i, format(cm[i, j], 'd'),
                    ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black")
    plt.ylabel('True Label')
    plt.xlabel('Predicted Label')

    plt.tight_layout()
    plot_path = os.path.join(output_dir, f"evaluation_{model_name}.png")
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"\nPlots saved to {plot_path}")


def evaluate_hybrid_pipeline(model_dir: str, scenarios: List[Dict] = None):
    """
    Evaluate the full hybrid pipeline (ML + rules) on synthetic scenarios.
    """
    print(f"\n=== Hybrid Pipeline Evaluation ===")

    # Load model
    model, scaler, metadata = load_model_artifacts(model_dir)
    risk_model = HybridRiskModel()
    risk_model.model = model
    risk_model.scaler = scaler
    risk_model.metadata = metadata

    # Test scenarios
    if scenarios is None:
        scenarios = [
            {
                "name": "Safe worker",
                "worker": {"id": "W-001", "ppe": {"helmet": True, "vest": True, "gloves": True}, "posture": "Normal", "x": 0.2, "y": 0.2},
                "proximity": {"distance": 15.0, "in_zone": False, "zone_severity": "safe", "facing_hazard": False, "closing_speed": 0.0},
                "expected": "SAFE",
            },
            {
                "name": "Worker without helmet in danger zone",
                "worker": {"id": "W-002", "ppe": {"helmet": False, "vest": True, "gloves": True}, "posture": "Normal", "x": 0.7, "y": 0.3},
                "proximity": {"distance": 3.0, "in_zone": True, "zone_severity": "danger", "facing_hazard": True, "closing_speed": 0.5},
                "expected": "HIGH",
            },
            {
                "name": "Worker approaching critical zone fast",
                "worker": {"id": "W-003", "ppe": {"helmet": True, "vest": True, "gloves": True}, "posture": "Normal", "x": 0.8, "y": 0.5},
                "proximity": {"distance": 1.5, "in_zone": True, "zone_severity": "critical", "facing_hazard": True, "closing_speed": 2.5},
                "expected": "CRITICAL",
            },
            {
                "name": "Multiple violations",
                "worker": {"id": "W-004", "ppe": {"helmet": False, "vest": False, "gloves": False}, "posture": "Unsafe", "x": 0.75, "y": 0.4},
                "proximity": {"distance": 2.0, "in_zone": True, "zone_severity": "danger", "facing_hazard": True, "closing_speed": 1.0},
                "expected": "CRITICAL",
            },
        ]

    correct = 0
    for sc in scenarios:
        assessment = risk_model.assess(sc["worker"], sc["proximity"], [], time.time())
        match = "✓" if assessment.severity == sc["expected"] else "✗"
        if assessment.severity == sc["expected"]:
            correct += 1
        print(f"  {match} {sc['name']}: Expected {sc['expected']}, Got {assessment.severity} (score: {assessment.final_risk_score:.1f})")
        if assessment.overrides:
            print(f"      Overrides: {assessment.overrides}")

    print(f"\nScenario accuracy: {correct}/{len(scenarios)} = {correct/len(scenarios)*100:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="SafeSight AI Model Evaluation")
    parser.add_argument("--model-dir", default="artifacts", help="Directory with model artifacts")
    parser.add_argument("--data-path", type=str, help="Path to test dataset CSV")
    parser.add_argument("--dataset", default="synthetic", choices=list(DATASET_CONFIGS.keys()))
    parser.add_argument("--output-dir", default="eval_output", help="Directory for plots")
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--test-hybrid", action="store_true", help="Test hybrid pipeline scenarios")
    args = parser.parse_args()

    evaluate_model(
        args.model_dir,
        data_path=args.data_path,
        dataset=args.dataset,
        output_dir=args.output_dir,
        plots=not args.no_plots,
    )

    if args.test_hybrid:
        evaluate_hybrid_pipeline(args.model_dir)


if __name__ == "__main__":
    main()
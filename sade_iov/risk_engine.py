"""Layer 2 - Machine-Learning Risk Engine (Section 4.5.1 / 5.5).

A supervised XGBoost ensemble maps the physical-telemetry feature vector
``F_t = {R_RSSI, V_var, alpha_freq}`` to:

  * a discrete misbehaviour class (genuine / jamming / injection / spoofing),
    used for the detection metrics in Chapter 6, and
  * a continuous situational risk score ``S_risk in [0, 100]`` (via a companion
    gradient-boosted regressor) that feeds the deterministic fusion / decision
    logic of Layer 2.

The model is constrained for edge execution (Table 7): max tree depth 5,
~100 estimators, standardised features, stratified 80:20 split, recall-first
tuning objective.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier, XGBRegressor

from . import config


@dataclass
class RiskEngine:
    """Trained risk engine: classifier (detection) + regressor (S_risk)."""

    classifier: XGBClassifier
    regressor: XGBRegressor
    scaler: StandardScaler

    # -- inference -----------------------------------------------------------
    def _scale(self, features) -> np.ndarray:
        arr = np.asarray(features, dtype=float).reshape(-1, len(config.FEATURES))
        return self.scaler.transform(arr)

    def predict_risk(self, features) -> np.ndarray:
        """Return S_risk in [0, 100] for one or many feature vectors."""
        x = self._scale(features)
        risk = self.regressor.predict(x)
        return np.clip(risk, 0.0, 100.0)

    def predict_class(self, features) -> np.ndarray:
        """Return the predicted misbehaviour-class label(s)."""
        return self.classifier.predict(self._scale(features))

    def predict_proba(self, features) -> np.ndarray:
        return self.classifier.predict_proba(self._scale(features))

    def score_epoch(self, r_rssi: float, v_var: float, alpha_freq: float) -> float:
        """Convenience: single-epoch S_risk as a Python float."""
        return float(self.predict_risk([[r_rssi, v_var, alpha_freq]])[0])

    # -- persistence ---------------------------------------------------------
    def save(self) -> None:
        os.makedirs(config.ARTIFACT_DIR, exist_ok=True)
        self.classifier.save_model(config.MODEL_PATH)
        self.regressor.save_model(config.REGRESSOR_PATH)
        joblib.dump(self.scaler, config.SCALER_PATH)

    @classmethod
    def load(cls) -> "RiskEngine":
        clf = XGBClassifier()
        clf.load_model(config.MODEL_PATH)
        reg = XGBRegressor()
        reg.load_model(config.REGRESSOR_PATH)
        scaler = joblib.load(config.SCALER_PATH)
        return cls(classifier=clf, regressor=reg, scaler=scaler)


def train_risk_engine(
    df: pd.DataFrame,
    seed: int = config.DEFAULT_SEED,
) -> tuple[RiskEngine, dict]:
    """Train the risk engine on a generated dataset.

    The split is performed by :func:`split_dataset` (stratified 80:20). Returns
    the fitted :class:`RiskEngine` plus a dict of train/test partitions for the
    evaluation module.
    """
    from sklearn.model_selection import train_test_split

    X = df[config.FEATURES].to_numpy(dtype=float)
    y_cls = df["label"].to_numpy()
    y_risk = df["risk_true"].to_numpy(dtype=float)

    idx = np.arange(len(df))
    (X_tr, X_te, ycls_tr, ycls_te, yrisk_tr, yrisk_te, idx_tr, idx_te) = train_test_split(
        X, y_cls, y_risk, idx,
        test_size=config.TEST_SIZE,
        random_state=seed,
        stratify=y_cls,  # stratified 80:20
    )

    # Standardise telemetry features (Table 7).
    scaler = StandardScaler().fit(X_tr)
    X_tr_s = scaler.transform(X_tr)
    X_te_s = scaler.transform(X_te)

    clf = XGBClassifier(
        num_class=len(config.PROFILES),
        random_state=seed,
        eval_metric="mlogloss",
        **config.XGB_PARAMS,
    )
    clf.fit(X_tr_s, ycls_tr)

    reg = XGBRegressor(
        max_depth=config.XGB_PARAMS["max_depth"],
        n_estimators=config.XGB_PARAMS["n_estimators"],
        learning_rate=config.XGB_PARAMS["learning_rate"],
        subsample=config.XGB_PARAMS["subsample"],
        colsample_bytree=config.XGB_PARAMS["colsample_bytree"],
        objective="reg:squarederror",
        random_state=seed,
        n_jobs=0,
    )
    reg.fit(X_tr_s, yrisk_tr)

    engine = RiskEngine(classifier=clf, regressor=reg, scaler=scaler)

    partitions = {
        "X_test": X_te,
        "y_cls_test": ycls_te,
        "y_risk_test": yrisk_te,
        "X_train": X_tr,
        "y_cls_train": ycls_tr,
        "idx_test": idx_te,
        "df": df,
    }
    return engine, partitions


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    from .data_generator import generate_dataset

    data = generate_dataset()
    eng, parts = train_risk_engine(data)
    preds = eng.predict_class(parts["X_test"])
    acc = float((preds == parts["y_cls_test"]).mean())
    print(f"test accuracy: {acc:.3f}")
    print("sample S_risk:", eng.predict_risk(parts["X_test"][:5]).round(1))

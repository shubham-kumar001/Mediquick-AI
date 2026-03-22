# ============================================
# ML ENGINE - 6 TRAINED MODELS
# ============================================

import os
import sys
from difflib import get_close_matches

import joblib
import numpy as np
import pandas as pd
from joblib import parallel_backend


class WeightedEnsemble:
    def __init__(self, models, weights):
        self.models = models
        self.weights = weights / np.sum(weights)
        self.classes_ = models[0].classes_

    def predict_proba(self, X):
        all_probs = []
        for model in self.models:
            probs = model.predict_proba(X)
            all_probs.append(probs)

        weighted_probs = np.zeros_like(all_probs[0])
        for index, probs in enumerate(all_probs):
            weighted_probs += self.weights[index] * probs
        return weighted_probs

    def predict(self, X):
        probs = self.predict_proba(X)
        return self.classes_[np.argmax(probs, axis=1)]


class TemperatureScaledModel:
    def __init__(self, base_model, temperature):
        self.base_model = base_model
        self.temperature = temperature
        self.classes_ = base_model.classes_

    def predict_proba(self, X):
        probs = self.base_model.predict_proba(X)
        logits = np.log(np.clip(probs, 1e-12, 1.0))
        scaled_logits = logits / max(float(self.temperature), 1e-6)
        exps = np.exp(scaled_logits - np.max(scaled_logits, axis=1, keepdims=True))
        return exps / np.sum(exps, axis=1, keepdims=True)

    def predict(self, X):
        probs = self.predict_proba(X)
        return self.classes_[np.argmax(probs, axis=1)]


class MultiLabelEnsemble:
    def __init__(self, models):
        self.models = models
        self.classes_ = None

    def predict(self, X):
        predictions = []
        for model in self.models:
            pred = model.predict(X)
            predictions.append(pred)
        return np.mean(predictions, axis=0) > 0.5

    def predict_proba(self, X):
        probas = []
        for model in self.models:
            if hasattr(model, "predict_proba"):
                probas.append(model.predict_proba(X))
        return np.mean(probas, axis=0)


_main_module = sys.modules.get("__main__")
if _main_module is not None:
    setattr(_main_module, "WeightedEnsemble", WeightedEnsemble)
    setattr(_main_module, "TemperatureScaledModel", TemperatureScaledModel)
    setattr(_main_module, "MultiLabelEnsemble", MultiLabelEnsemble)


class MediMindML:
    def __init__(self, models_dir):
        self.models_dir = models_dir
        self.models = {}
        self.load_all_models()

    def _model_path(self, *parts):
        return os.path.join(self.models_dir, *parts)

    def _safe_print(self, message):
        print(message.encode("ascii", errors="replace").decode("ascii"))

    def _load_first_existing(self, *relative_paths):
        last_error = None

        for relative_path in relative_paths:
            path = self._model_path(*relative_path.split("/"))
            if os.path.exists(path):
                return joblib.load(path)
            last_error = FileNotFoundError(f"Missing file: {path}")

        raise last_error or FileNotFoundError("No matching model artifact found")

    def _build_supportive_lookup(self, care_frame):
        lookup = {}

        for _, row in care_frame.fillna("").iterrows():
            entry = {
                "supportive": row.get("supportive_care", ""),
                "symptomatic_management": row.get("symptomatic_management", ""),
                "non_pharmacological": row.get("non_pharmacological", ""),
                "disease": row.get("disease", ""),
                "symptom": row.get("symptom", ""),
            }

            for key in (row.get("input_text", ""), row.get("disease", ""), row.get("symptom", "")):
                normalized = str(key).strip().lower()
                if normalized:
                    lookup[normalized] = entry

        return lookup

    def _force_serial_execution(self, obj, visited=None):
        if visited is None:
            visited = set()

        obj_id = id(obj)
        if obj is None or obj_id in visited:
            return
        visited.add(obj_id)

        if hasattr(obj, "n_jobs"):
            try:
                obj.n_jobs = 1
            except Exception:
                pass

        if isinstance(obj, dict):
            for value in obj.values():
                self._force_serial_execution(value, visited)
            return

        if isinstance(obj, (list, tuple, set)):
            for value in obj:
                self._force_serial_execution(value, visited)
            return

        for attr in ("estimators_", "estimators", "calibrated_classifiers_", "models", "base_model"):
            if hasattr(obj, attr):
                try:
                    self._force_serial_execution(getattr(obj, attr), visited)
                except Exception:
                    pass

    def load_all_models(self):
        """Load all 6 trained models."""
        self._safe_print("Loading ML Models...")

        # Model 1: Disease Prediction
        try:
            self.disease_model = self._load_first_existing(
                "disease_model/lr.pkl",
                "disease_model/nb.pkl",
                "disease_model/rf.pkl",
                "disease_model/calibrated_ensemble.pkl",
                "disease_model/ensemble.pkl",
            )
            self.disease_vectorizer = self._load_first_existing(
                "disease_model/vectorizer.pkl",
                "disease_model/calibrated_vectorizer.pkl",
                "disease_model/tfidf_vectorizer.pkl",
            )
            self.disease_labels = self._load_first_existing(
                "disease_model/label_encoder.pkl",
                "disease_model/class_names.pkl",
                "disease_model/disease_names.pkl",
                "disease_model/calibrated_disease_names.pkl",
            )
            self._force_serial_execution(self.disease_model)
            self._safe_print("[OK] Disease Model loaded")
        except Exception as e:
            self._safe_print(f"[ERROR] Disease Model error: {e}")
            self.disease_model = None
            self.disease_vectorizer = None
            self.disease_labels = None

        # Model 2: Ayurvedic
        try:
            self.ayurvedic_model = self._load_first_existing(
                "ayurvedic_model/lr_model.pkl",
                "ayurvedic_model/nb_model.pkl",
                "ayurvedic_model/rf_model.pkl",
                "ayurvedic_model/ensemble.pkl",
            )
            self.ayurvedic_vectorizer = self._load_first_existing("ayurvedic_model/vectorizer.pkl")
            self._force_serial_execution(self.ayurvedic_model)
            self._safe_print("[OK] Ayurvedic Model loaded")
        except Exception as e:
            self._safe_print(f"[ERROR] Ayurvedic Model error: {e}")
            self.ayurvedic_model = None
            self.ayurvedic_vectorizer = None

        # Model 3: Supportive Care
        try:
            self.supportive_model = self._load_first_existing(
                "supportive_model/lr_model.pkl",
                "supportive_model/nb_model.pkl",
                "supportive_model/rf_model.pkl",
                "supportive_model/ensemble.pkl",
            )
            self.supportive_vectorizer = self._load_first_existing("supportive_model/vectorizer.pkl")
            self._force_serial_execution(self.supportive_model)

            care_csv_path = self._model_path("supportive_model", "care_database.csv")
            if os.path.exists(care_csv_path):
                care_frame = pd.read_csv(care_csv_path)
                self.care_database = self._build_supportive_lookup(care_frame)
            else:
                self.care_database = self._load_first_existing("supportive_model/care_database.pkl")

            self._safe_print("[OK] Supportive Model loaded")
        except Exception as e:
            self._safe_print(f"[ERROR] Supportive Model error: {e}")
            self.supportive_model = None
            self.supportive_vectorizer = None
            self.care_database = {}

        # Model 4: Unified
        try:
            self.unified_model = self._load_first_existing(
                "unified_model/lr_model.pkl",
                "unified_model/nb_model.pkl",
                "unified_model/rf_model.pkl",
                "unified_model/calibrated_ensemble.pkl",
                "unified_model/ensemble.pkl",
            )
            self.unified_vectorizer = self._load_first_existing("unified_model/vectorizer.pkl")
            self._force_serial_execution(self.unified_model)
            self._safe_print("[OK] Unified Model loaded")
        except Exception as e:
            self._safe_print(f"[ERROR] Unified Model error: {e}")
            self.unified_model = None
            self.unified_vectorizer = None

        # Model 5: Diet
        try:
            self.diet_model = self._load_first_existing(
                "diet_model/lr_model.pkl",
                "diet_model/nb_model.pkl",
                "diet_model/rf_model.pkl",
                "diet_model/temperature_scaled_model.pkl",
                "diet_model/calibrated_ensemble.pkl",
                "diet_model/ensemble.pkl",
            )
            self.diet_vectorizer = self._load_first_existing("diet_model/vectorizer.pkl")
            self.diet_database = self._load_first_existing("diet_model/diet_database.pkl")
            self._force_serial_execution(self.diet_model)
            self._safe_print("[OK] Diet Model loaded")
        except Exception as e:
            self._safe_print(f"[ERROR] Diet Model error: {e}")
            self.diet_model = None
            self.diet_vectorizer = None
            self.diet_database = {}

        # Model 6: Lab Tests
        try:
            self.lab_model = self._load_first_existing(
                "lab_tests_model/lr_model.pkl",
                "lab_tests_model/nb_model.pkl",
                "lab_tests_model/rf_model.pkl",
                "lab_tests_model/calibrated_ensemble.pkl",
                "lab_tests_model/ensemble.pkl",
            )
            self.lab_vectorizer = self._load_first_existing("lab_tests_model/vectorizer.pkl")
            self.lab_database = self._load_first_existing(
                "lab_tests_model/lab_tests_database.pkl",
                "lab_tests_model/lab_test_database.pkl",
            )
            self._force_serial_execution(self.lab_model)
            self._safe_print("[OK] Lab Tests Model loaded")
        except Exception as e:
            self._safe_print(f"[ERROR] Lab Tests Model error: {e}")
            self.lab_model = None
            self.lab_vectorizer = None
            self.lab_database = {}

    def _get_disease_label(self, top_idx):
        if hasattr(self.disease_labels, "classes_"):
            return self.disease_labels.classes_[top_idx]

        if isinstance(self.disease_labels, (list, tuple, np.ndarray, pd.Series)):
            return self.disease_labels[top_idx]

        if hasattr(self.disease_model, "classes_"):
            return self.disease_model.classes_[top_idx]

        return None

    def predict_disease(self, symptoms_text):
        """Predict disease from symptoms."""
        if self.disease_model is None or self.disease_vectorizer is None:
            return None, 0

        vec = self.disease_vectorizer.transform([symptoms_text])
        with parallel_backend("threading", n_jobs=1):
            probs = self.disease_model.predict_proba(vec)[0]
        top_idx = np.argmax(probs)

        disease = self._get_disease_label(top_idx)
        confidence = probs[top_idx] * 100

        return disease, confidence

    def get_ayurvedic(self, symptoms_text):
        """Get Ayurvedic medicine recommendations."""
        if self.ayurvedic_model is None or self.ayurvedic_vectorizer is None:
            return []

        vec = self.ayurvedic_vectorizer.transform([symptoms_text.lower()])
        with parallel_backend("threading", n_jobs=1):
            probs = self.ayurvedic_model.predict_proba(vec)[0]
        top3_idx = np.argsort(probs)[-3:][::-1]

        results = []
        for idx in top3_idx:
            if probs[idx] > 0.1:
                results.append(
                    {
                        "medicine": self.ayurvedic_model.classes_[idx],
                        "confidence": probs[idx] * 100,
                    }
                )
        return results

    def get_supportive_care(self, symptoms_text):
        """Get supportive care recommendations."""
        if self.supportive_model is None or self.supportive_vectorizer is None:
            return {}

        vec = self.supportive_vectorizer.transform([symptoms_text.lower()])
        with parallel_backend("threading", n_jobs=1):
            probs = self.supportive_model.predict_proba(vec)[0]
        top_idx = np.argmax(probs)

        predicted_key = str(self.supportive_model.classes_[top_idx]).strip().lower()
        symptom_key = symptoms_text.strip().lower()

        if symptom_key in self.care_database:
            return self.care_database[symptom_key]

        if predicted_key in self.care_database:
            return self.care_database[predicted_key]

        close_matches = get_close_matches(symptom_key, list(self.care_database.keys()), n=1, cutoff=0.3)
        if close_matches:
            return self.care_database[close_matches[0]]

        return {}

    def get_diet_plan(self, disease_name):
        """Get diet recommendations."""
        if self.diet_model is None:
            return {}

        disease_key = disease_name.lower()
        return self.diet_database.get(disease_key, {})

    def get_lab_tests(self, disease_name):
        """Get lab test recommendations."""
        if self.lab_model is None:
            return []

        disease_key = disease_name.lower()
        lab_info = self.lab_database.get(disease_key, {})
        return lab_info.get("lab_tests", [])

    def get_full_analysis(self, symptoms_text):
        """Get complete analysis from all 6 models."""
        result = {
            "symptoms": symptoms_text,
            "disease": None,
            "disease_confidence": 0,
            "ayurvedic": [],
            "supportive_care": {},
            "diet_plan": {},
            "lab_tests": [],
        }

        disease, conf = self.predict_disease(symptoms_text)
        if disease:
            result["disease"] = disease
            result["disease_confidence"] = conf
            result["diet_plan"] = self.get_diet_plan(disease)
            result["lab_tests"] = self.get_lab_tests(disease)

        result["ayurvedic"] = self.get_ayurvedic(symptoms_text)
        result["supportive_care"] = self.get_supportive_care(symptoms_text)

        return result

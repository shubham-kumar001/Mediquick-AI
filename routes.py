# ============================================
# BACKEND/ROUTES.PY - COMPLETE API ENDPOINTS
# ============================================

from __future__ import annotations

import json
import os
import uuid
from difflib import get_close_matches
from functools import lru_cache

import pandas as pd
from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.utils import secure_filename

from auth import admin_required, doctor_required, login_required
from config import DATA_DIR
from database import Appointment, ChatLog, Doctor, Feedback, Prescription, User, db

api_bp = Blueprint("api", __name__, url_prefix="/api")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDICINE_GUIDE_PATH = os.path.join(BASE_DIR, "medicine_guides", "ayurvedic_guide.json")

GREETING_WORDS = {
    "hi", "hello", "hey", "good morning", "good afternoon", "good evening", "namaste"
}
AFFIRMATION_WORDS = {"yes", "yeah", "yep", "ok", "okay", "sure", "haan", "han"}
TEXT_ALIASES = [
    ("loose motions", "diarrhea"),
    ("lose motions", "diarrhea"),
    ("loose motion", "diarrhea"),
    ("lose motion", "diarrhea"),
    ("feaver", "fever"),
    ("aurvedic", "ayurvedic"),
]
EMERGENCY_KEYWORDS = [
    "chest pain", "difficulty breathing", "shortness of breath", "trouble breathing",
    "seizure", "stroke", "heart attack", "fainting", "unconscious", "heavy bleeding",
    "blood vomiting", "vomiting blood", "suicidal", "severe allergic reaction"
]
FOLLOW_UP_PHRASES = [
    "what should i do", "what next", "is it serious", "explain more", "tell me more",
    "should i book", "do i need doctor", "what medicine", "what can i eat"
]
HOME_CARE_HINTS = ["home care", "what should i do", "what to do", "care at home", "self care"]
SYMPTOM_HINTS = [
    "i have", "i am having", "i'm having", "feeling", "suffering from", "pain",
    "fever", "cough", "cold", "headache", "vomiting", "nausea", "rash", "weakness",
    "constipation", "diarrhea", "diarrhoea", "loose motion", "lose motion", "loose stool",
    "stomach pain", "body pain", "sneezing", "sneeze", "runny nose", "sore throat", "itching", "itchy"
]
DIET_HINTS = ["diet", "food", "eat", "meal", "nutrition", "avoid", "hydration"]
LAB_TEST_HINTS = ["lab test", "blood test", "test", "scan", "x-ray", "mri", "cbc", "thyroid"]
MEDICINE_HINTS = ["medicine", "tablet", "capsule", "syrup", "dose", "dosage", "ayurvedic"]
DISEASE_HINTS = ["disease", "condition", "what is", "tell me about", "about "]
FOLLOW_UP_REFERENCE_HINTS = [
    "for it", "for that", "for this", "what about", "and for", "any solution",
    "ayurvedic solution", "any ayurvedic solution", "any ayurvedic care", "ayurvedic care",
    "home care", "diet for it", "tests for it", "for fever", "for cough", "for headache"
]
GENERIC_CONTEXT_REQUESTS = {
    "medicine": ["ayurvedic", "medicine", "remedy", "remedies", "solution", "care"],
    "diet": ["diet", "food", "eat", "meal", "nutrition"],
    "lab_test": ["test", "tests", "blood test", "scan", "x-ray", "mri"],
    "home_care": ["home care", "care at home", "what should i do", "what to do", "self care"],
}
MENU_INTENT_OVERRIDES = {
    "disease prediction from symptoms": "help",
    "disease prediction": "help",
    "ayurvedic remedies": "medicine",
    "ayurvedic remedy": "medicine",
    "home care advice": "home_care",
    "diet recommendations": "diet",
    "diet recommendation": "diet",
    "lab tests": "lab_test",
    "lab test": "lab_test",
}
HELP_PHRASES = {
    "disease prediction from symptoms",
    "disease prediction",
    "ayurvedic remedies",
    "ayurvedic remedy",
    "home care advice",
    "diet recommendations",
    "diet recommendation",
    "lab tests",
    "lab test",
}
EXPLANATION_HINTS = {
    "meaning",
    "what does it mean",
    "what does that mean",
    "what is the meaning",
    "explain",
    "explain it",
    "explain that",
}
BASIC_SYMPTOM_TERMS = [
    "sneezing", "sneeze", "fever", "cough", "cold", "headache", "vomiting", "nausea",
    "constipation", "diarrhea", "diarrhoea", "stomach pain", "body pain", "runny nose",
    "sore throat", "weakness", "rash", "itching", "itchy",
]
UNSURE_SYMPTOM_PHRASES = {
    "i don't know what symptoms",
    "i dont know what symptoms",
    "i don't know my symptoms",
    "i dont know my symptoms",
    "i don't know what i am feeling",
    "i dont know what i am feeling",
    "i don't know what problem i have",
    "i dont know what problem i have",
}
BROAD_DISEASE_TERMS = {
    "cancer",
    "tumor",
    "tumour",
    "diabetes",
    "asthma",
    "arthritis",
    "migraine",
    "infection",
    "allergy",
    "flu",
    "covid",
}
CONDITION_SYNONYMS = {
    "fungus": "fungal infection",
    "skin fungus": "fungal infection",
    "ringworm": "fungal infection",
    "itchy skin": "itching",
    "itch": "itching",
    "itchy": "itching",
    "cold and cough": "cold",
    "sneez": "sneezing",
}
USER_NEED_KEYWORDS = {
    "medicine": ["ayurvedic", "remedy", "remedies", "medicine", "treatment", "solution"],
    "home_care": ["home care", "care at home", "self care", "what should i do", "what to do"],
    "diet": ["diet", "food", "eat", "avoid", "nutrition", "meal"],
    "lab_test": ["lab test", "tests", "test", "scan", "x-ray", "mri", "cbc", "blood test"],
    "disease": ["what is", "meaning", "explain", "condition", "disease", "cause", "likely cause"],
}


def normalize_text(value):
    normalized = " ".join(str(value or "").strip().lower().split())
    for source, target in TEXT_ALIASES:
        normalized = normalized.replace(source, target)
    for source, target in CONDITION_SYNONYMS.items():
        normalized = normalized.replace(source, target)
    return " ".join(normalized.split())


def extract_focus_terms(message):
    normalized_message = normalize_text(message)
    candidates = [normalized_message]

    prefixes = [
        "i have",
        "i am having",
        "i'm having",
        "i am feeling",
        "feeling",
        "suffering from",
        "tell me about",
        "what is",
        "for",
    ]

    for prefix in prefixes:
        if normalized_message.startswith(prefix):
            remainder = normalized_message[len(prefix):].strip(" ?.,")
            if remainder:
                candidates.append(remainder)

    words = [word.strip(" ?.,") for word in normalized_message.split() if word.strip(" ?.,")]
    candidates.extend(words)
    return [candidate for candidate in candidates if candidate]


def extract_topic_term(message):
    normalized_message = normalize_text(message)
    for term in sorted(BASIC_SYMPTOM_TERMS, key=len, reverse=True):
        if term in normalized_message:
            return term
    return ""


def fuzzy_message_match(message, term):
    normalized_message = normalize_text(message)
    normalized_term = normalize_text(term)

    if not normalized_term:
        return False
    if normalized_term in normalized_message:
        return True

    message_words = [word for word in normalized_message.split() if len(word) >= 4]
    term_words = [word for word in normalized_term.split() if len(word) >= 4]

    for term_word in term_words:
        if get_close_matches(term_word, message_words, n=1, cutoff=0.8):
            return True

    return False


@lru_cache(maxsize=1)
def load_disease_catalog():
    path = os.path.join(DATA_DIR, "diseases_10000_cleaned.xlsx")
    frame = pd.read_excel(path)
    records = []

    for _, row in frame.iterrows():
        symptoms = []
        for column in ["Symptom 1", "Symptom 2", "Symptom 3", "Symptom 4"]:
            value = row.get(column)
            if pd.notna(value):
                symptoms.append(str(value).strip())

        disease_name = str(row.get("Disease Name", "")).strip()
        if disease_name:
            records.append(
                {
                    "disease_name": disease_name,
                    "description": str(row.get("Description", "")).strip(),
                    "symptoms": symptoms,
                    "search_text": normalize_text(" ".join([disease_name] + symptoms)),
                }
            )

    return records


@lru_cache(maxsize=1)
def load_diet_catalog():
    path = os.path.join(DATA_DIR, "Disease_Diet_Plan_10000.xlsx")
    frame = pd.read_excel(path, header=1)
    frame.columns = [str(column).strip() for column in frame.columns]
    records = {}

    for _, row in frame.iterrows():
        disease_name = str(row.get("Disease Name", "")).strip()
        if not disease_name:
            continue

        records[normalize_text(disease_name)] = {
            "disease": disease_name,
            "recommended_foods": str(row.get("Recommended Foods", "")).strip(),
            "restricted_foods": str(row.get("Foods to Avoid", "")).strip(),
            "meal_plan": str(row.get("Sample Meal Plan (B/L/D)", "")).strip(),
            "ayurvedic_guidance": str(row.get("Ayurvedic Diet Guidance", "")).strip(),
            "hydration": str(row.get("Hydration Advice", "")).strip(),
            "supplements": str(row.get("Supplements", "")).strip(),
            "meal_frequency": str(row.get("Meal Frequency", "")).strip(),
            "benefit": str(row.get("Diet Benefit", "")).strip(),
            "diet_category": str(row.get("Diet Category", "")).strip(),
        }

    return records


@lru_cache(maxsize=1)
def load_lab_catalog():
    path = os.path.join(DATA_DIR, "diseases_10000_with_lab_tests_v2.xlsx")
    frame = pd.read_excel(path)
    records = {}

    for _, row in frame.iterrows():
        disease_name = str(row.get("Disease Name", "")).strip()
        if not disease_name:
            continue

        tests = []
        for index in range(1, 10):
            test_name = row.get(f"Lab Test {index} — Name")
            test_why = row.get(f"Lab Test {index} — Why You Need This Test (Patient Benefit)")
            if pd.notna(test_name):
                tests.append(
                    {
                        "test_name": str(test_name).strip(),
                        "why": str(test_why).strip() if pd.notna(test_why) else "",
                    }
                )

        records[normalize_text(disease_name)] = tests

    return records


@lru_cache(maxsize=1)
def load_ayurvedic_catalog():
    path = os.path.join(DATA_DIR, "ayurvedic_diseases_10000.xlsx")
    frame = pd.read_excel(path)
    records = []

    for _, row in frame.iterrows():
        disease_name = str(row.get("Disease Name", "")).strip()
        if not disease_name:
            continue

        symptom_entries = []
        for index in range(1, 5):
            symptom = row.get(f"Symptom {index}")
            medicine = row.get(f"Ayurvedic Medicine (S{index})")
            dosage = row.get(f"Dosage (S{index})")

            if pd.notna(symptom) and pd.notna(medicine):
                symptom_entries.append(
                    {
                        "symptom": str(symptom).strip(),
                        "medicine": str(medicine).strip(),
                        "dosage": str(dosage).strip() if pd.notna(dosage) else "",
                    }
                )

        records.append(
            {
                "disease_name": disease_name,
                "description": str(row.get("Description", "")).strip(),
                "symptom_entries": symptom_entries,
            }
        )

    return records


@lru_cache(maxsize=1)
def load_medicine_guide():
    with open(MEDICINE_GUIDE_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)

    normalized = {}
    for key, value in data.items():
        normalized[normalize_text(key)] = {"name": key, **value}
    return normalized


def find_disease_match(message):
    normalized_message = normalize_text(message)
    records = load_disease_catalog()

    for record in records:
        disease_key = normalize_text(record["disease_name"])
        if disease_key and disease_key in normalized_message:
            return record

    disease_map = {normalize_text(record["disease_name"]): record for record in records}
    disease_names = list(disease_map.keys())

    for candidate in extract_focus_terms(message):
        matches = get_close_matches(normalize_text(candidate), disease_names, n=1, cutoff=0.82)
        if matches:
            return disease_map[matches[0]]

    return None


def find_medicine_match(message):
    normalized_message = normalize_text(message)
    guide = load_medicine_guide()

    for key, value in guide.items():
        if key in normalized_message:
            return value

    return None


def detect_user_need(message):
    normalized_message = normalize_text(message)

    if normalized_message in AFFIRMATION_WORDS:
        return "follow_up"
    if any(phrase in normalized_message for phrase in UNSURE_SYMPTOM_PHRASES):
        return "symptom_guidance"
    if any(hint in normalized_message for hint in HOME_CARE_HINTS):
        return "home_care"

    for need, keywords in USER_NEED_KEYWORDS.items():
        if any(keyword in normalized_message for keyword in keywords):
            return need

    if any(term in normalized_message for term in BROAD_DISEASE_TERMS) or find_disease_match(normalized_message):
        return "disease"
    if any(hint in normalized_message for hint in SYMPTOM_HINTS):
        return "symptom"
    return "follow_up"


def build_condition_profile(condition_name, ml_analysis=None):
    normalized_condition = normalize_text(condition_name)
    if not normalized_condition:
        return {}

    disease_record = None
    for record in load_disease_catalog():
        if normalize_text(record["disease_name"]) == normalized_condition:
            disease_record = record
            break

    diet_info = load_diet_catalog().get(normalized_condition, {})
    lab_info = load_lab_catalog().get(normalized_condition, [])
    ayurvedic_options = get_ayurvedic_options(condition_name, condition_name)
    supportive_info = {}
    if ml_analysis:
        supportive_info = ml_analysis.get("supportive_care", {}) or {}

    keyword_values = []
    if disease_record:
        keyword_values.extend(disease_record.get("symptoms", []))
        keyword_values.append(disease_record.get("disease_name", ""))

    return {
        "disease_name": disease_record.get("disease_name", condition_name) if disease_record else condition_name,
        "symptoms": disease_record.get("symptoms", []) if disease_record else [],
        "description": disease_record.get("description", "") if disease_record else "",
        "ayurvedic_remedy": ayurvedic_options,
        "home_care": supportive_info.get("supportive", ""),
        "diet": diet_info,
        "tests": lab_info,
        "doctor_warning": supportive_info.get("when_to_see_doctor", ""),
        "keywords": [value for value in keyword_values if value],
    }


def get_ayurvedic_options(message, matched_disease=None):
    normalized_message = normalize_text(message)
    matched_disease_key = normalize_text(matched_disease)
    options = []
    seen = set()
    records = load_ayurvedic_catalog()

    if matched_disease_key:
        exact_records = [
            record for record in records
            if normalize_text(record["disease_name"]) == matched_disease_key
        ]
        if exact_records:
            for record in exact_records:
                symptom_matches = []
                for entry in record["symptom_entries"]:
                    if fuzzy_message_match(normalized_message, entry["symptom"]):
                        symptom_matches.append(entry)

                chosen_entries = symptom_matches or record["symptom_entries"][:2]
                for entry in chosen_entries:
                    option_key = (entry["medicine"], entry["dosage"])
                    if option_key not in seen:
                        seen.add(option_key)
                        options.append(
                            {
                                "medicine": entry["medicine"],
                                "dosage": entry["dosage"],
                                "symptom": entry["symptom"],
                                "disease": record["disease_name"],
                                "match_type": "disease",
                            }
                        )
            return options[:3]

    for record in records:
        disease_key = normalize_text(record["disease_name"])
        disease_match = bool(
            disease_key and (disease_key in normalized_message or (matched_disease_key and disease_key == matched_disease_key))
        )

        for entry in record["symptom_entries"]:
            symptom_match = fuzzy_message_match(normalized_message, entry["symptom"])
            if disease_match or symptom_match:
                option_key = (entry["medicine"], entry["dosage"])
                if option_key not in seen:
                    seen.add(option_key)
                    options.append(
                        {
                            "medicine": entry["medicine"],
                            "dosage": entry["dosage"],
                            "symptom": entry["symptom"],
                            "disease": record["disease_name"],
                            "match_type": "symptom" if symptom_match else "disease",
                        }
                    )

    options.sort(key=lambda item: 0 if item["match_type"] == "symptom" else 1)
    return options[:3]


def detect_intent(message):
    normalized_message = normalize_text(message)
    strong_symptom_query = any(
        phrase in normalized_message for phrase in ["i have", "i am having", "i'm having", "feeling", "suffering from", "i am faced", "i faced"]
    )

    if any(keyword in normalized_message for keyword in EMERGENCY_KEYWORDS):
        return "emergency"
    if normalized_message in GREETING_WORDS or any(normalized_message.startswith(word) for word in GREETING_WORDS):
        return "greeting"
    if normalized_message in AFFIRMATION_WORDS:
        return "follow_up"
    if any(phrase in normalized_message for phrase in UNSURE_SYMPTOM_PHRASES):
        return "symptom_guidance"
    if normalized_message in MENU_INTENT_OVERRIDES:
        return MENU_INTENT_OVERRIDES[normalized_message]
    if normalized_message in HELP_PHRASES:
        return "help"
    if any(phrase in normalized_message for phrase in FOLLOW_UP_PHRASES):
        return "follow_up"
    if any(hint in normalized_message for hint in HOME_CARE_HINTS):
        return "home_care"
    if find_medicine_match(normalized_message) or any(hint in normalized_message for hint in MEDICINE_HINTS):
        return "medicine"
    if any(hint in normalized_message for hint in DIET_HINTS):
        return "diet"
    if any(hint in normalized_message for hint in LAB_TEST_HINTS):
        return "lab_test"
    if strong_symptom_query:
        return "symptom"
    if any(hint in normalized_message for hint in SYMPTOM_HINTS):
        return "symptom"
    if any(term in normalized_message for term in BROAD_DISEASE_TERMS):
        return "disease"
    if find_disease_match(normalized_message) or any(hint in normalized_message for hint in DISEASE_HINTS):
        return "disease"
    return "follow_up"


def is_contextual_follow_up(message):
    normalized_message = normalize_text(message)
    words = normalized_message.split()

    if normalized_message in AFFIRMATION_WORDS:
        return True
    if normalized_message in EXPLANATION_HINTS:
        return True
    if any(hint in normalized_message for hint in FOLLOW_UP_REFERENCE_HINTS):
        return True
    if any(word in {"it", "that", "this", "same"} for word in words):
        return True
    return len(words) <= 4 and normalized_message.endswith("?")


def is_generic_context_request(message, intent):
    normalized_message = normalize_text(message)
    if intent not in GENERIC_CONTEXT_REQUESTS:
        return False
    if find_disease_match(normalized_message) or find_medicine_match(normalized_message):
        return False
    return any(term in normalized_message for term in GENERIC_CONTEXT_REQUESTS[intent])


def get_chat_memory():
    return session.get(
        "chat_memory",
        {
            "condition": None,
            "last_user_message": None,
            "last_resolved_message": None,
            "last_non_followup_intent": None,
            "last_user_need": None,
            "last_symptom_query": None,
            "last_disease": None,
            "recent_turns": [],
        },
    )


def get_recent_history(memory, limit=6):
    turns = (memory or {}).get("recent_turns") or []
    return turns[-limit:]


def resolve_message_with_memory(user_message, intent, memory):
    normalized_message = normalize_text(user_message)
    should_attach_memory = is_contextual_follow_up(user_message) or is_generic_context_request(user_message, intent)
    if not memory or not should_attach_memory:
        return user_message, intent

    if normalized_message in EXPLANATION_HINTS:
        if memory.get("last_disease"):
            return f"tell me about {memory['last_disease']}", "disease"
        if memory.get("last_symptom_query"):
            return memory["last_symptom_query"], "symptom"

    if normalized_message in AFFIRMATION_WORDS and memory.get("last_symptom_query"):
        return memory["last_symptom_query"], "follow_up"

    inferred_intent = intent
    if intent in {"follow_up", "symptom", "disease"} and memory.get("last_non_followup_intent"):
        inferred_intent = memory["last_non_followup_intent"]

    anchor = memory.get("last_symptom_query") or memory.get("last_disease") or memory.get("last_user_message")
    if anchor and normalize_text(anchor) not in normalized_message:
        return f"{anchor}. {user_message}", inferred_intent

    return user_message, inferred_intent


def update_chat_memory(original_message, resolved_message, intent, user_need, context, bot_response):
    memory = get_chat_memory()
    memory["condition"] = context.get("active_condition")
    session["condition"] = context.get("active_condition")
    memory["last_user_message"] = original_message
    memory["last_resolved_message"] = resolved_message

    if intent != "follow_up":
        memory["last_non_followup_intent"] = intent
    if user_need != "follow_up":
        memory["last_user_need"] = user_need

    if intent in {"symptom", "emergency"}:
        memory["last_symptom_query"] = resolved_message

    if context.get("active_condition"):
        memory["last_disease"] = context["active_condition"]

    recent_turns = memory.get("recent_turns") or []
    recent_turns.append(
        {
            "user": original_message,
            "assistant": bot_response,
            "intent": intent,
            "resolved": resolved_message,
        }
    )
    memory["recent_turns"] = recent_turns[-6:]

    session["chat_memory"] = memory


def assess_severity(message, ml_analysis):
    normalized_message = normalize_text(message)
    if any(keyword in normalized_message for keyword in EMERGENCY_KEYWORDS):
        return "emergency"

    disease_name = normalize_text(ml_analysis.get("disease"))
    confidence = float(ml_analysis.get("disease_confidence") or 0)
    severe_disease_terms = ["stroke", "sepsis", "pneumonia", "cardiac", "meningitis", "kidney", "liver"]

    if any(term in disease_name for term in severe_disease_terms) and confidence >= 25:
        return "high"
    if confidence >= 20:
        return "medium"
    return "low"


def build_chat_context(user_message, intent, user_need, ml_analysis, memory=None):
    disease_match = find_disease_match(user_message)
    medicine_match = find_medicine_match(user_message)
    severity = assess_severity(user_message, ml_analysis)
    normalized_message = normalize_text(user_message)
    remembered_condition = ((memory or {}).get("condition") or "").strip()
    topic_term = extract_topic_term(user_message)
    matched_disease = disease_match["disease_name"] if disease_match else None
    ml_disease = ml_analysis.get("disease")
    ml_confidence = float(ml_analysis.get("disease_confidence") or 0)
    is_broad_disease_query = intent == "disease" and not disease_match and any(
        term in normalized_message for term in BROAD_DISEASE_TERMS
    )
    active_condition = matched_disease or topic_term or remembered_condition or None

    if intent == "help":
        active_condition = None
    elif not active_condition and not is_broad_disease_query and ml_disease and (
        intent == "disease"
        or any(hint in normalized_message for hint in DISEASE_HINTS)
        or (intent == "symptom" and ml_confidence >= 35)
    ):
        active_condition = ml_disease

    if intent in {"greeting", "follow_up"} and not disease_match and not any(
        hint in normalized_message for hint in SYMPTOM_HINTS
    ):
        active_condition = remembered_condition or active_condition
    if user_need in {"medicine", "diet", "lab_test", "home_care"} and remembered_condition and not matched_disease and not topic_term:
        active_condition = remembered_condition

    condition_profile = build_condition_profile(active_condition, ml_analysis) if active_condition else {}
    active_condition_name = condition_profile.get("disease_name") or active_condition
    diet_info = condition_profile.get("diet") or {}
    lab_info = condition_profile.get("tests") or []
    ayurvedic_options = condition_profile.get("ayurvedic_remedy") or get_ayurvedic_options(user_message, active_condition_name)
    follow_up_topic = active_condition_name or topic_term or (medicine_match.get("name") if medicine_match else "your symptoms")

    context = {
        "intent": intent,
        "user_need": user_need,
        "severity": severity,
        "needs_appointment": severity in {"high", "emergency"},
        "matched_disease": active_condition_name,
        "active_condition": active_condition_name,
        "condition_profile": condition_profile,
        "disease_info": disease_match or {},
        "diet_info": diet_info or {},
        "lab_info": lab_info or [],
        "ayurvedic_options": ayurvedic_options,
        "medicine_name": medicine_match.get("name") if medicine_match else None,
        "medicine_info": medicine_match or {},
        "follow_up_topic": follow_up_topic,
        "is_broad_disease_query": is_broad_disease_query,
        "needs_clarification": (
            user_need in {"medicine", "diet", "lab_test", "home_care", "follow_up"}
            and not active_condition_name
            and not medicine_match
            and not any(hint in normalized_message for hint in SYMPTOM_HINTS)
        ),
    }

    if intent == "diet" and not context["diet_info"] and ml_analysis.get("diet_plan"):
        context["diet_info"] = ml_analysis["diet_plan"]
    if intent == "lab_test" and not context["lab_info"] and ml_analysis.get("lab_tests"):
        context["lab_info"] = ml_analysis["lab_tests"]
    if intent == "disease" and not context["disease_info"] and active_condition_name:
        context["disease_info"] = {
            "disease_name": active_condition_name,
            "description": condition_profile.get("description", ""),
            "symptoms": condition_profile.get("symptoms", []),
        }

    return context


def extract_condition_from_response(response_text):
    normalized_response = normalize_text(response_text)
    for record in load_disease_catalog():
        disease_name = record.get("disease_name", "")
        disease_key = normalize_text(disease_name)
        if disease_key and disease_key in normalized_response:
            return disease_name
    return None


def response_matches_condition(response_text, context):
    expected_condition = context.get("active_condition")
    if not expected_condition:
        return True

    mentioned_condition = extract_condition_from_response(response_text)
    if not mentioned_condition:
        return True

    return normalize_text(mentioned_condition) == normalize_text(expected_condition)


def serialize_ml_analysis(analysis):
    def convert(value):
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        if isinstance(value, list):
            return [convert(item) for item in value]
        if hasattr(value, "item"):
            return value.item()
        return value

    return convert(analysis)


@api_bp.route("/chat", methods=["POST"])
def chat():
    """Main chatbot endpoint with intent detection and formatted replies."""
    try:
        data = request.get_json(silent=True) or {}
        user_message = data.get("message", "").strip()
        user_id = session.get("user_id")

        if not user_message:
            return jsonify({"error": "Message is required"}), 400

        memory = get_chat_memory()
        history = get_recent_history(memory)
        intent = detect_intent(user_message)
        user_need = detect_user_need(user_message)
        resolved_message, intent = resolve_message_with_memory(user_message, intent, memory)
        ml_analysis = serialize_ml_analysis(current_app.ml_engine.get_full_analysis(resolved_message))
        context = build_chat_context(resolved_message, intent, user_need, ml_analysis, memory)
        response_intent = user_need if user_need not in {"follow_up"} else intent

        bot_response = current_app.chatbot.generate_response(
            user_message=user_message,
            intent=response_intent,
            ml_analysis=ml_analysis,
            context=context,
            history=history,
        )

        if not response_matches_condition(bot_response, context):
            bot_response = current_app.chatbot.generate_response(
                user_message=user_message,
                intent=response_intent,
                ml_analysis=ml_analysis,
                context={**context, "force_template": True},
                history=[],
            )

        update_chat_memory(user_message, resolved_message, intent, user_need, context, bot_response)

        if user_id:
            chat_log = ChatLog(
                user_id=user_id,
                user_message=user_message,
                bot_response=bot_response,
            )
            db.session.add(chat_log)
            db.session.commit()

        return jsonify(
            {
                "success": True,
                "intent": intent,
                "user_need": user_need,
                "severity": context["severity"],
                "needs_appointment": context["needs_appointment"],
                "response": bot_response,
                "ml_analysis": ml_analysis,
                "context": {
                    "active_condition": context.get("active_condition"),
                    "matched_disease": context.get("matched_disease"),
                    "medicine_name": context.get("medicine_name"),
                    "resolved_message": resolved_message,
                },
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/analyze", methods=["POST"])
def analyze():
    """Direct ML analysis endpoint."""
    try:
        data = request.get_json(silent=True) or {}
        symptoms = data.get("symptoms", "").strip()

        if not symptoms:
            return jsonify({"error": "Symptoms are required"}), 400

        analysis = serialize_ml_analysis(current_app.ml_engine.get_full_analysis(symptoms))
        return jsonify({"success": True, "analysis": analysis})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/chat/history", methods=["GET"])
@login_required
def get_chat_history():
    """Get user's chat history."""
    try:
        user_id = session["user_id"]
        limit = request.args.get("limit", 50, type=int)

        logs = (
            ChatLog.query.filter_by(user_id=user_id)
            .order_by(ChatLog.created_at.desc())
            .limit(limit)
            .all()
        )

        return jsonify(
            {
                "success": True,
                "history": [
                    {
                        "id": log.id,
                        "user_message": log.user_message,
                        "bot_response": log.bot_response,
                        "timestamp": log.created_at.isoformat(),
                    }
                    for log in reversed(logs)
                ],
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/auth/signup", methods=["POST"])
def signup():
    """User registration."""
    try:
        data = request.get_json()
        name = data.get("name", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        role = data.get("role", "patient")

        if not name or not email or not password:
            return jsonify({"error": "All fields are required"}), 400
        if len(password) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({"error": "Email already registered"}), 400

        from werkzeug.security import generate_password_hash

        user = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            role=role,
        )
        db.session.add(user)
        db.session.commit()

        if role == "doctor":
            doctor = Doctor(
                user_id=user.id,
                specialization=data.get("specialization", "General Physician"),
                qualification=data.get("qualification", "MBBS"),
                experience_years=data.get("experience", 0),
                consultation_fee=data.get("fee", 500),
                is_verified=False,
            )
            db.session.add(doctor)
            db.session.commit()

        return jsonify(
            {
                "success": True,
                "message": "Account created successfully",
                "user": {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "role": user.role,
                },
            }
        )

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@api_bp.route("/auth/login", methods=["POST"])
def login():
    """User login."""
    try:
        data = request.get_json()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        user = User.query.filter_by(email=email).first()

        from werkzeug.security import check_password_hash

        if not user or not check_password_hash(user.password, password):
            return jsonify({"error": "Invalid email or password"}), 401

        session["user_id"] = user.id
        session["user_name"] = user.name
        session["user_role"] = user.role

        return jsonify(
            {
                "success": True,
                "message": f"Welcome back, {user.name}!",
                "user": {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "role": user.role,
                },
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully"})


@api_bp.route("/auth/me", methods=["GET"])
def get_current_user():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    user = User.query.get(session["user_id"])
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"id": user.id, "name": user.name, "email": user.email, "role": user.role})


@api_bp.route("/doctors", methods=["GET"])
def get_doctors():
    """Get list of all doctors."""
    try:
        specialty = request.args.get("specialty")
        query = db.session.query(Doctor, User).join(User, Doctor.user_id == User.id).filter(User.role == "doctor")

        if specialty:
            query = query.filter(Doctor.specialization.ilike(f"%{specialty}%"))

        doctors = query.all()
        result = []
        for doctor, user in doctors:
            result.append(
                {
                    "id": doctor.id,
                    "user_id": doctor.user_id,
                    "name": user.name,
                    "specialization": doctor.specialization,
                    "qualification": doctor.qualification,
                    "experience_years": doctor.experience_years,
                    "consultation_fee": doctor.consultation_fee,
                    "rating": doctor.rating or 4.5,
                    "is_verified": doctor.is_verified,
                }
            )

        return jsonify({"doctors": result})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/doctors/<int:doctor_id>", methods=["GET"])
def get_doctor(doctor_id):
    try:
        doctor = Doctor.query.get_or_404(doctor_id)
        user = User.query.get(doctor.user_id)

        return jsonify(
            {
                "id": doctor.id,
                "user_id": doctor.user_id,
                "name": user.name if user else "Unknown",
                "specialization": doctor.specialization,
                "qualification": doctor.qualification,
                "experience_years": doctor.experience_years,
                "consultation_fee": doctor.consultation_fee,
                "rating": doctor.rating,
                "is_verified": doctor.is_verified,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/doctors/<int:doctor_id>/availability", methods=["GET"])
def get_doctor_availability(doctor_id):
    try:
        doctor = Doctor.query.get_or_404(doctor_id)
        slots = []
        if doctor.available_time:
            for day in doctor.available_time.split(","):
                if ":" in day:
                    parts = day.split(":")
                    slots.append({"day": parts[0].strip(), "hours": parts[1].strip()})

        return jsonify({"slots": slots})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/doctors/profile", methods=["PUT"])
@login_required
@doctor_required
def update_doctor_profile():
    try:
        user_id = session["user_id"]
        data = request.get_json()
        doctor = Doctor.query.filter_by(user_id=user_id).first()
        if not doctor:
            return jsonify({"error": "Doctor profile not found"}), 404

        if "specialization" in data:
            doctor.specialization = data["specialization"]
        if "qualification" in data:
            doctor.qualification = data["qualification"]
        if "experience_years" in data:
            doctor.experience_years = data["experience_years"]
        if "consultation_fee" in data:
            doctor.consultation_fee = data["consultation_fee"]
        if "available_time" in data:
            doctor.available_time = data["available_time"]

        db.session.commit()
        return jsonify({"success": True, "message": "Profile updated"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@api_bp.route("/appointments", methods=["POST"])
def book_appointment():
    """Book a new appointment."""
    try:
        data = request.get_json()
        patient_id = session.get("user_id") or data.get("user_id")
        doctor_id = data.get("doctor_id")
        date = data.get("date")
        time = data.get("time")
        notes = data.get("notes", "")

        if not patient_id or not doctor_id or not date or not time:
            return jsonify({"error": "Missing required fields"}), 400

        doctor = Doctor.query.get(doctor_id)
        if not doctor:
            return jsonify({"error": "Doctor not found"}), 404

        existing = Appointment.query.filter_by(
            doctor_id=doctor.user_id,
            date=date,
            time=time,
            status="confirmed",
        ).first()
        if existing:
            return jsonify({"error": "Slot already booked"}), 409

        appointment = Appointment(
            patient_id=patient_id,
            doctor_id=doctor.user_id,
            date=date,
            time=time,
            notes=notes,
            status="pending",
        )

        db.session.add(appointment)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "appointment_id": appointment.id,
                "message": "Appointment request sent successfully",
            }
        )

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@api_bp.route("/appointments/<int:user_id>", methods=["GET"])
def get_appointments_by_user(user_id):
    try:
        appointments = Appointment.query.filter(
            (Appointment.patient_id == user_id) | (Appointment.doctor_id == user_id)
        ).order_by(Appointment.date.desc()).all()

        result = []
        for appointment in appointments:
            patient = User.query.get(appointment.patient_id)
            doctor = User.query.get(appointment.doctor_id)
            result.append(
                {
                    "id": appointment.id,
                    "patient_name": patient.name if patient else "Unknown",
                    "doctor_name": doctor.name if doctor else "Unknown",
                    "date": appointment.date,
                    "time": appointment.time,
                    "status": appointment.status,
                    "notes": appointment.notes,
                }
            )

        return jsonify({"appointments": result})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/appointments", methods=["GET"])
@login_required
def get_appointments():
    try:
        user_id = session["user_id"]
        user = User.query.get(user_id)

        if user.role == "patient":
            appointments = Appointment.query.filter_by(patient_id=user_id).order_by(Appointment.date.desc()).all()
        else:
            appointments = Appointment.query.filter_by(doctor_id=user_id).order_by(Appointment.date.desc()).all()

        result = []
        for appointment in appointments:
            patient = User.query.get(appointment.patient_id)
            doctor = User.query.get(appointment.doctor_id)
            result.append(
                {
                    "id": appointment.id,
                    "patient_name": patient.name if patient else "Unknown",
                    "doctor_name": doctor.name if doctor else "Unknown",
                    "date": appointment.date,
                    "time": appointment.time,
                    "status": appointment.status,
                    "notes": appointment.notes,
                    "created_at": appointment.created_at.isoformat(),
                }
            )

        return jsonify({"appointments": result})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/appointments/<int:appointment_id>/status", methods=["PUT"])
@login_required
def update_appointment_status(appointment_id):
    try:
        data = request.get_json()
        new_status = data.get("status")

        if new_status not in ["pending", "confirmed", "completed", "cancelled"]:
            return jsonify({"error": "Invalid status"}), 400

        appointment = Appointment.query.get_or_404(appointment_id)
        user_id = session["user_id"]
        if appointment.doctor_id != user_id and appointment.patient_id != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        appointment.status = new_status
        db.session.commit()
        return jsonify({"success": True, "message": f"Appointment {new_status}"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@api_bp.route("/prescriptions/upload", methods=["POST"])
@login_required
def upload_prescription():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
        filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        extracted_text = "Sample extracted text from prescription"
        medicines = ["Paracetamol 500mg", "Vitamin C 500mg"]

        prescription = Prescription(
            patient_id=session["user_id"],
            image_path=filepath,
            extracted_text=extracted_text,
            medicines=",".join(medicines),
        )

        db.session.add(prescription)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "prescription_id": prescription.id,
                "extracted_text": extracted_text,
                "medicines": medicines,
            }
        )

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@api_bp.route("/prescriptions", methods=["GET"])
@login_required
def get_prescriptions():
    try:
        user_id = session["user_id"]
        prescriptions = Prescription.query.filter_by(patient_id=user_id).order_by(Prescription.created_at.desc()).all()

        return jsonify(
            {
                "prescriptions": [
                    {
                        "id": prescription.id,
                        "image_path": prescription.image_path,
                        "medicines": prescription.medicines.split(",") if prescription.medicines else [],
                        "created_at": prescription.created_at.isoformat(),
                    }
                    for prescription in prescriptions
                ]
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/feedback", methods=["POST"])
@login_required
def submit_feedback():
    try:
        data = request.get_json()
        rating = data.get("rating")
        comment = data.get("comment", "")

        if not rating or not 1 <= rating <= 5:
            return jsonify({"error": "Rating must be between 1 and 5"}), 400

        feedback = Feedback(user_id=session["user_id"], rating=rating, comment=comment)
        db.session.add(feedback)
        db.session.commit()
        return jsonify({"success": True, "message": "Thank you for your feedback!"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@api_bp.route("/feedback", methods=["GET"])
def get_feedback():
    try:
        feedbacks = Feedback.query.order_by(Feedback.created_at.desc()).limit(20).all()
        return jsonify(
            {
                "feedbacks": [
                    {
                        "rating": feedback.rating,
                        "comment": feedback.comment,
                        "created_at": feedback.created_at.isoformat(),
                    }
                    for feedback in feedbacks
                ]
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/profile", methods=["GET"])
@login_required
def get_profile():
    try:
        user = User.query.get(session["user_id"])
        profile = {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "created_at": user.created_at.isoformat(),
        }

        if user.role == "doctor":
            doctor = Doctor.query.filter_by(user_id=user.id).first()
            if doctor:
                profile["doctor"] = {
                    "specialization": doctor.specialization,
                    "qualification": doctor.qualification,
                    "experience_years": doctor.experience_years,
                    "consultation_fee": doctor.consultation_fee,
                    "available_time": doctor.available_time,
                    "rating": doctor.rating,
                    "is_verified": doctor.is_verified,
                }

        return jsonify({"profile": profile})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/profile", methods=["PUT"])
@login_required
def update_profile():
    try:
        data = request.get_json()
        user = User.query.get(session["user_id"])

        if "name" in data:
            user.name = data["name"]

        db.session.commit()
        return jsonify({"success": True, "message": "Profile updated"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@api_bp.route("/admin/users", methods=["GET"])
@login_required
@admin_required
def admin_get_users():
    try:
        users = User.query.all()
        return jsonify(
            {
                "users": [
                    {
                        "id": user.id,
                        "name": user.name,
                        "email": user.email,
                        "role": user.role,
                        "created_at": user.created_at.isoformat(),
                    }
                    for user in users
                ]
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/admin/doctors/verify/<int:doctor_id>", methods=["PUT"])
@login_required
@admin_required
def verify_doctor(doctor_id):
    try:
        doctor = Doctor.query.get_or_404(doctor_id)
        doctor.is_verified = True
        db.session.commit()
        return jsonify({"success": True, "message": "Doctor verified"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@api_bp.route("/admin/stats", methods=["GET"])
@login_required
@admin_required
def get_admin_stats():
    try:
        stats = {
            "total_users": User.query.count(),
            "total_doctors": User.query.filter_by(role="doctor").count(),
            "total_patients": User.query.filter_by(role="patient").count(),
            "total_appointments": Appointment.query.count(),
            "pending_appointments": Appointment.query.filter_by(status="pending").count(),
            "total_feedbacks": Feedback.query.count(),
            "avg_rating": db.session.query(db.func.avg(Feedback.rating)).scalar() or 0,
        }

        return jsonify({"stats": stats})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

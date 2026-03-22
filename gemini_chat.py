# ============================================
# GEMINI CHATBOT INTEGRATION
# Short response formatting and fallback conversation handling
# ============================================

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from config import GEMINI_API_KEY

try:
    from google import genai
except ImportError:  # pragma: no cover
    genai = None


logger = logging.getLogger(__name__)


class GeminiChatbot:
    def __init__(self, ml_engine):
        self.ml_engine = ml_engine
        self.use_gemini = bool(genai and GEMINI_API_KEY)
        self.client = genai.Client(api_key=GEMINI_API_KEY) if self.use_gemini else None
        self.model_name = "gemini-2.5-flash"
        self.max_response_chars = 240
        self.basic_symptom_care = {
            "fever": "Rest, fluids, and light clothing can help.",
            "diarrhea": "Stay hydrated and use oral rehydration fluids if needed.",
            "constipation": "Drink more water and add fiber-rich foods.",
            "cough": "Warm fluids and rest may help.",
            "cold": "Rest, fluids, and steam may help.",
            "sneezing": "Sneezing can happen with cold, allergy, or dust irritation. Rest, fluids, and avoiding dust can help.",
            "sneeze": "Sneezing can happen with cold, allergy, or dust irritation. Rest, fluids, and avoiding dust can help.",
            "itching": "Keep the area clean, avoid scratching, and use gentle skin products.",
            "itchy": "Keep the area clean, avoid scratching, and use gentle skin products.",
            "headache": "Rest, hydration, and reduced screen strain may help.",
            "vomiting": "Take small sips of fluids and avoid heavy foods.",
            "nausea": "Take small sips of fluids and bland foods.",
        }
        self.broad_disease_explanations = {
            "cancer": "Cancer is a broad term for diseases where abnormal cells grow uncontrollably. Tell me the type or symptoms if you want more specific help.",
            "diabetes": "Diabetes is a condition where blood sugar stays too high. Tell me the type or symptoms if you want more specific help.",
            "asthma": "Asthma is a condition that causes airway inflammation and breathing difficulty. Tell me the symptoms if you want more specific help.",
        }

    def generate_response(
        self,
        user_message: str,
        intent: str,
        ml_analysis: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        context = context or {}
        ml_analysis = ml_analysis or {}
        history = history or []

        if self.use_gemini and not context.get("force_template"):
            prompt = self._build_prompt(user_message, intent, ml_analysis, context, history)
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )
                text = getattr(response, "text", "").strip()
                if text:
                    return self._finalize_response(text)
                logger.warning("Gemini returned an empty response; using fallback reply.")
            except Exception as exc:
                logger.warning("Gemini request failed; using fallback reply: %s", exc)

        return self._finalize_response(
            self._fallback_response(user_message, intent, ml_analysis, context)
        )

    def get_response(self, user_message: str) -> str:
        ml_analysis = self.ml_engine.get_full_analysis(user_message)
        return self.generate_response(
            user_message=user_message,
            intent="symptom",
            ml_analysis=ml_analysis,
            context={"severity": "medium"},
        )

    def _build_prompt(
        self,
        user_message: str,
        intent: str,
        ml_analysis: Dict[str, Any],
        context: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> str:
        history_lines = []
        for turn in history[-6:]:
            user_text = str(turn.get("user") or "").strip()
            assistant_text = str(turn.get("assistant") or "").strip()
            if user_text:
                history_lines.append(f"User: {user_text}")
            if assistant_text:
                history_lines.append(f"Assistant: {assistant_text}")

        history_block = "\n".join(history_lines) if history_lines else "No prior conversation."
        return f"""
You are MediMind, a healthcare assistant that should feel like an actual LLM chat, not a rigid rule bot.

Intent: {intent}
User Need: {context.get("user_need", intent)}
Active Condition: {context.get("active_condition")}
Severity: {context.get("severity", "unknown")}
Needs Appointment CTA: {context.get("needs_appointment", False)}
Conversation Context: {context}
ML Analysis: {ml_analysis}
Recent conversation:
{history_block}
User message: "{user_message}"

Rules:
- Use the recent conversation to resolve follow-up meaning.
- Keep the answer aligned to the active condition when one exists.
- Answer only what the user asked.
- If the user clicked a generic menu item like diet, lab test, or ayurvedic remedies with no active symptom or disease context, ask for the symptom or condition first.
- Do not invent a disease just to fill space.
- Keep it under 60 words.
- Use at most 2 short paragraphs.
- Mention appointment only if serious.
- Do not over-explain.
""".strip()

    def _fallback_response(
        self,
        user_message: str,
        intent: str,
        ml_analysis: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        handler = getattr(self, f"_format_{intent}_response", self._format_default_response)
        return handler(user_message, ml_analysis, context)

    def _format_greeting_response(self, user_message: str, ml_analysis: Dict[str, Any], context: Dict[str, Any]) -> str:
        return "Hello. Tell me your symptoms or ask about a disease, medicine, diet, or lab test."

    def _format_help_response(self, user_message: str, ml_analysis: Dict[str, Any], context: Dict[str, Any]) -> str:
        return "Share symptoms like fever, cough, or stomach pain. I can then help with condition, Ayurvedic care, diet, tests, or home care."

    def _format_symptom_guidance_response(self, user_message: str, ml_analysis: Dict[str, Any], context: Dict[str, Any]) -> str:
        return "No problem. Tell me in simple words what you feel, like sneezing, fever, cough, cold, headache, stomach pain, vomiting, or weakness."

    def _format_emergency_response(self, user_message: str, ml_analysis: Dict[str, Any], context: Dict[str, Any]) -> str:
        return "This sounds urgent. Seek emergency care now. If safe, book a doctor immediately."

    def _format_symptom_response(self, user_message: str, ml_analysis: Dict[str, Any], context: Dict[str, Any]) -> str:
        parts = []
        disease = ml_analysis.get("disease")
        confidence = float(ml_analysis.get("disease_confidence") or 0)
        supportive = ml_analysis.get("supportive_care", {}).get("supportive")
        matched_disease = (context.get("matched_disease") or "").strip()
        matched_key = matched_disease.lower()
        disease_key = str(disease or "").strip().lower()
        symptom_key = self._detect_known_symptom_key(user_message, matched_disease)

        if symptom_key:
            parts.append(self.basic_symptom_care[symptom_key])
        elif disease and confidence >= 35:
            parts.append(f"Possible condition: {disease}.")

        if supportive and disease_key and disease_key == matched_key and not symptom_key:
            parts.append(f"Try: {supportive}.")

        if context.get("needs_appointment"):
            parts.append("Please book a doctor soon.")
        elif symptom_key:
            parts.append("Tell me if you want likely cause, home care, Ayurvedic care, diet, or tests.")
        else:
            parts.append("If symptoms worsen, book a doctor.")

        return " ".join(parts)

    def _format_disease_response(self, user_message: str, ml_analysis: Dict[str, Any], context: Dict[str, Any]) -> str:
        normalized_message = self._normalize_text(user_message)
        if context.get("is_broad_disease_query"):
            for term, reply in self.broad_disease_explanations.items():
                if term in normalized_message:
                    return reply
            return "Tell me the exact disease name or symptoms and I can explain it more clearly."

        condition_profile = context.get("condition_profile") or {}
        disease_name = self._condition_name(context, ml_analysis)
        description = condition_profile.get("description") or context.get("disease_info", {}).get("description")
        symptoms = condition_profile.get("symptoms") or context.get("disease_info", {}).get("symptoms", [])

        if description:
            return f"{disease_name}: {description}. Ask if you want diet, tests, or home care."
        if symptoms:
            return f"{disease_name}: Common signs include {', '.join(symptoms[:3])}. Ask if you want diet, tests, or home care."
        return f"{disease_name}: I can help with diet, tests, or home care for this condition."

    def _format_medicine_response(self, user_message: str, ml_analysis: Dict[str, Any], context: Dict[str, Any]) -> str:
        medicine = context.get("medicine_name", "this medicine")
        medicine_info = context.get("medicine_info") or {}
        condition_profile = context.get("condition_profile") or {}
        ayurvedic_options = condition_profile.get("ayurvedic_remedy") or context.get("ayurvedic_options") or []
        matched_disease = context.get("active_condition")

        if context.get("needs_clarification") and not matched_disease and not medicine_info:
            return "Tell me the symptom or condition first, then I can suggest Ayurvedic options."

        if not medicine_info:
            if ayurvedic_options:
                first = ayurvedic_options[0]
                medicine_names = []
                seen = set()
                for item in ayurvedic_options:
                    raw_value = item.get("medicine", "")
                    for name in [part.strip() for part in raw_value.split(",") if part.strip()]:
                        key = name.lower()
                        if key not in seen:
                            seen.add(key)
                            medicine_names.append(name)

                base = f"Ayurvedic options for {matched_disease or first.get('disease', 'this issue')}: {', '.join(medicine_names[:4])}."
                if first.get("dosage"):
                    base += f" Typical use: {first['dosage']}."
                return base

            ayurvedic = ml_analysis.get("ayurvedic") or []
            if ayurvedic:
                names = [item.get("medicine") for item in ayurvedic[:2] if item.get("medicine")]
                if names:
                    return f"Ayurvedic options: {', '.join(names)}. Use them only with doctor guidance."
            return f"I could not find details for {medicine}. Share the exact medicine name."

        parts = [f"{medicine}:"]
        if medicine_info.get("usage"):
            parts.append(f"Use: {medicine_info['usage']}.")
        if medicine_info.get("precautions"):
            parts.append(f"Caution: {medicine_info['precautions']}.")
        return " ".join(parts)

    def _format_diet_response(self, user_message: str, ml_analysis: Dict[str, Any], context: Dict[str, Any]) -> str:
        condition_profile = context.get("condition_profile") or {}
        diet_info = condition_profile.get("diet") or context.get("diet_info") or ml_analysis.get("diet_plan") or {}
        disease_name = self._condition_name(context, ml_analysis)

        if context.get("needs_clarification") and not context.get("matched_disease"):
            return "Tell me the symptom or condition first, then I can give diet advice."
        if not diet_info:
            return "Tell me the disease name or symptoms first for diet advice."

        parts = [f"Diet for {disease_name}:"]
        if diet_info.get("recommended_foods"):
            parts.append(f"Eat: {diet_info['recommended_foods']}.")
        if diet_info.get("restricted_foods"):
            parts.append(f"Avoid: {diet_info['restricted_foods']}.")
        return " ".join(parts)

    def _format_lab_test_response(self, user_message: str, ml_analysis: Dict[str, Any], context: Dict[str, Any]) -> str:
        condition_profile = context.get("condition_profile") or {}
        tests = condition_profile.get("tests") or context.get("lab_info") or self._extract_lab_test_names(ml_analysis)
        disease_name = self._condition_name(context, ml_analysis)

        if context.get("needs_clarification") and not context.get("matched_disease"):
            return "Tell me the symptom or condition first, then I can suggest tests."
        if not tests:
            return "Share symptoms or a disease name so I can suggest tests."

        names = []
        for item in tests[:3]:
            if isinstance(item, dict):
                names.append(item.get("test_name", "Lab test"))
            else:
                names.append(str(item))

        return f"Tests for {disease_name}: {', '.join(names)}."

    def _format_follow_up_response(self, user_message: str, ml_analysis: Dict[str, Any], context: Dict[str, Any]) -> str:
        topic = context.get("active_condition") or context.get("follow_up_topic", "your symptoms")
        return f"For {topic}, I can help with likely cause, home care, Ayurvedic care, diet, or tests. Tell me which one you want."

    def _format_home_care_response(self, user_message: str, ml_analysis: Dict[str, Any], context: Dict[str, Any]) -> str:
        matched_disease = context.get("active_condition") or ""
        condition_profile = context.get("condition_profile") or {}
        symptom_key = self._detect_known_symptom_key(user_message, matched_disease)
        supportive = condition_profile.get("home_care") or ml_analysis.get("supportive_care", {}).get("supportive")

        if context.get("needs_clarification") and not matched_disease and not symptom_key:
            return "Tell me the symptom or condition first, then I can suggest home care."
        if symptom_key and symptom_key in self.basic_symptom_care:
            return f"Home care for {symptom_key}: {self.basic_symptom_care[symptom_key]} If it gets worse, book a doctor."
        if supportive:
            return f"Home care: {supportive}. If it gets worse, book a doctor."

        topic = context.get("follow_up_topic", "this issue")
        return f"For {topic}, rest, hydration, and symptom monitoring can help. If it gets worse, book a doctor."

    def _format_default_response(self, user_message: str, ml_analysis: Dict[str, Any], context: Dict[str, Any]) -> str:
        return "Tell me your symptoms or ask about a disease, medicine, diet, lab test, or doctor advice."

    def _normalize_text(self, value: str) -> str:
        return " ".join(str(value or "").strip().lower().split())

    def _condition_name(self, context: Dict[str, Any], ml_analysis: Dict[str, Any]) -> str:
        condition_profile = context.get("condition_profile") or {}
        return (
            condition_profile.get("disease_name")
            or context.get("active_condition")
            or context.get("matched_disease")
            or ml_analysis.get("disease")
            or "this condition"
        )

    def _detect_known_symptom_key(self, user_message: str, matched_disease: str) -> str:
        matched_key = self._normalize_text(matched_disease)
        if matched_key in self.basic_symptom_care:
            return matched_key

        normalized_message = self._normalize_text(user_message)
        for key in sorted(self.basic_symptom_care, key=len, reverse=True):
            if key in normalized_message:
                return key

        return ""

    def _extract_lab_test_names(self, ml_analysis: Dict[str, Any]) -> List[str]:
        results = []
        for test in ml_analysis.get("lab_tests", []):
            if isinstance(test, dict):
                name = test.get("test_name")
                if name:
                    results.append(name)
            elif test:
                results.append(str(test))
        return results

    def _finalize_response(self, text: str) -> str:
        text = " ".join(str(text).replace("\r", "\n").split())
        if len(text) <= self.max_response_chars:
            return text

        trimmed = text[: self.max_response_chars].rsplit(" ", 1)[0].strip()
        return f"{trimmed}..."

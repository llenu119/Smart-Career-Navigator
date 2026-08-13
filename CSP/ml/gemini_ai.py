"""
Gemini AI Integration
======================
Powers the four core AI functionalities using the Google GenAI SDK:
  1. Enhanced resume feedback (JSON)
  2. Smart skill gap explanations (JSON)
  3. AI career advisor chatbot (multi-turn conversation)
  4. AI-generated cover letters (JSON)

Includes monthly token limits check, warnings, notifications, and usage logging.
"""

import os
import json
import re
import logging
from datetime import datetime
from google import genai
from google.genai import types
from utils.db import get_db

FENCE_RE = re.compile(r'```(?:json)?', re.IGNORECASE)


def _extract_json(raw):
    """
    Robustly pull a JSON object/array out of an LLM response.
    See ml/groq_ai.py::_extract_json for the full rationale -- the old
    anchored-fence approach broke whenever the model added a leading
    blank line or any preamble text before the JSON.
    """
    text = FENCE_RE.sub('', raw).strip()

    start_obj = text.find('{')
    start_arr = text.find('[')
    candidates = [i for i in (start_obj, start_arr) if i != -1]
    if candidates:
        start = min(candidates)
        end_char = '}' if text[start] == '{' else ']'
        end = text.rfind(end_char)
        if end > start:
            text = text[start:end + 1]
    else:
        text = '{}'

    return text


GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def _get_client():
    """Return a Gemini Client; raises RuntimeError if key is missing."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Add it to your .env file and restart."
        )
    return genai.Client(api_key=api_key)


def get_monthly_token_usage(user_id):
    """Calculate the total token usage for the user in the current calendar month."""
    now = datetime.utcnow()
    start_of_month = f"{now.year}-{now.month:02d}-01 00:00:00"
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SUM(total_tokens) as total FROM ai_requests WHERE user_id = %s AND timestamp >= %s",
        (user_id, start_of_month)
    )
    row = cursor.fetchone()
    total = row['total'] if row and row['total'] is not None else 0
    conn.close()
    return total


def get_token_limit_and_warning(user_id):
    """
    Returns (allowed, used, limit, warning_message).
    - If monthly usage exceeds limit, allowed=False.
    - If monthly usage is >= 80% of limit, sets a warning message.
    """
    if not user_id:
        return True, 0, 0, None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT token_limit, username FROM users WHERE id = %s", (user_id,))
    user_row = cursor.fetchone()
    conn.close()

    if not user_row:
        return True, 0, 0, None

    limit = user_row['token_limit'] or 100000
    used = get_monthly_token_usage(user_id)

    warning_msg = None
    allowed = True

    if used >= limit:
        allowed = False
        warning_msg = f"Monthly token limit exceeded. Limit: {limit:,}, Used: {used:,}."
    elif used >= 0.8 * limit:
        pct = (used / limit) * 100
        warning_msg = f"Warning: You have used {pct:.1f}% of your monthly AI token limit ({used:,} / {limit:,} tokens)."
        _create_monthly_warning_notification(user_id, warning_msg)

    return allowed, used, limit, warning_msg


def _create_monthly_warning_notification(user_id, message):
    """Create a DB notification alert if it doesn't already exist for the current month."""
    now = datetime.utcnow()
    start_of_month = f"{now.year}-{now.month:02d}-01 00:00:00"
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM notifications WHERE user_id = %s AND message LIKE 'Warning: You have used%%' AND created_at >= %s",
        (user_id, start_of_month)
    )
    existing = cursor.fetchone()

    if not existing:
        cursor.execute(
            "INSERT INTO notifications (user_id, message, type) VALUES (%s, %s, %s)",
            (user_id, message, 'warning')
        )
        conn.commit()

    conn.close()


def _log_ai_request(user_id, feature, prompt_tokens, completion_tokens, total_tokens, status='success', error_message=None):
    """Record the token usage and status for audit logs."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO ai_requests (user_id, feature, prompt_tokens, completion_tokens, total_tokens, status, error_message)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, feature, prompt_tokens, completion_tokens, total_tokens, status, error_message)
    )
    conn.commit()
    conn.close()


def _generate_with_gemini(user_id, feature, system_prompt, user_message, max_output_tokens=1024, json_mode=False):
    """
    Internal helper: checks limits, runs Gemini, logs token count, and handles errors.
    Returns the generated response string.
    """
    if user_id:
        allowed, used, limit, warning = get_token_limit_and_warning(user_id)
        if not allowed:
            raise ValueError(warning)

    try:
        client = _get_client()

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=max_output_tokens,
            temperature=0.7,
            response_mime_type="application/json" if json_mode else "text/plain"
        )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_message,
            config=config
        )

        prompt_t = 0
        comp_t = 0
        total_t = 0

        if response.usage_metadata:
            prompt_t = response.usage_metadata.prompt_token_count or 0
            comp_t = response.usage_metadata.candidates_token_count or 0
            total_t = response.usage_metadata.total_token_count or 0

        _log_ai_request(user_id, feature, prompt_t, comp_t, total_t, 'success')

        return response.text.strip()

    except Exception as e:
        error_msg = str(e)
        _log_ai_request(user_id, feature, 0, 0, 0, 'failed', error_msg)
        raise e


def get_ai_resume_feedback(user_id, resume_text, extracted_skills, resume_score):
    """Generate structured AI resume enhancement advice."""
    system = (
        "You are a senior technical recruiter and resume expert at a top tech firm. "
        "Provide concise, actionable feedback. "
        "Respond ONLY with valid JSON — no markdown, no preamble."
    )

    skills_str = ", ".join(extracted_skills[:20]) if extracted_skills else "none detected"
    user_msg = f"""
    Analyse this resume and return JSON with exactly these keys:
    {{
      "overall":      "2-sentence summary of the resume quality",
      "strengths":    ["strength 1", "strength 2", "strength 3"],
      "improvements": ["tip 1", "tip 2", "tip 3", "tip 4"],
      "ats_tips":     ["ATS tip 1", "ATS tip 2", "ATS tip 3"]
    }}

    Resume score (rule-based): {resume_score}/100
    Skills detected: {skills_str}
    Resume text (first 2000 chars):
    \"\"\"
    {resume_text[:2000]}
    \"\"\"
    """

    try:
        raw = _generate_with_gemini(user_id, "resume_feedback", system, user_msg, max_output_tokens=800, json_mode=True)
        clean = _extract_json(raw)
        data = json.loads(clean)
        data.setdefault("error", None)
        return data
    except Exception as exc:
        return {
            "overall":      "AI feedback temporarily unavailable.",
            "strengths":    [],
            "improvements": [],
            "ats_tips":     [],
            "error":        str(exc),
        }


def get_skill_gap_explanation(user_id, career_role, missing_skills, existing_skills):
    """Explain why lacking skills are important and recommend how to acquire them."""
    system = (
        "You are a career coach specialising in tech roles. "
        "Give practical, motivating guidance. "
        "Respond ONLY with valid JSON — no markdown, no preamble."
    )

    missing_str  = ", ".join(missing_skills[:10])  if missing_skills  else "none"
    existing_str = ", ".join(existing_skills[:10]) if existing_skills else "none"

    user_msg = f"""
    The user wants to become a {career_role}.
    They already know: {existing_str}.
    They are missing: {missing_str}.

    Return JSON with exactly these keys:
    {{
      "summary": "2-3 sentence personalised overview",
      "skill_explanations": [
        {{"skill": "SkillName", "why_important": "one sentence", "how_to_learn": "one sentence"}}
      ],
      "quick_wins": ["easiest skill 1", "easiest skill 2", "easiest skill 3"]
    }}

    Fill skill_explanations for each missing skill listed above (up to 8).
    """

    try:
        raw = _generate_with_gemini(user_id, "skill_explanation", system, user_msg, max_output_tokens=900, json_mode=True)
        clean = _extract_json(raw)
        data = json.loads(clean)
        data.setdefault("error", None)
        return data
    except Exception as exc:
        return {
            "summary":            "AI explanation temporarily unavailable.",
            "skill_explanations": [],
            "quick_wins":         [],
            "error":              str(exc),
        }


def chat_with_advisor(user_id, messages, profile):
    """Provide multi-turn advisor chatbot support."""
    name   = profile.get("name") or "Student"
    branch = profile.get("branch", "")
    skills = profile.get("technical_skills", "")
    interests = profile.get("interests", "")

    background_desc = f"a {branch} student" if branch else "a student"
    if branch and ("Level" in branch or "Professional" in branch or branch == "Graduate" or branch == "Post Graduate"):
        background_desc = f"a {branch} professional"
    system = (
        f"You are an expert AI career advisor inside Smart Career Navigator. "
        f"You are talking to {name}, {background_desc} interested in {interests}. "
        f"Their current technical skills: {skills}. "
        "Give personalised, encouraging, practical career advice. "
        "Keep replies concise (3-5 sentences max unless asked for more). "
        "Use bullet points for lists. Do NOT use markdown headers."
    )

    history_prompt = ""
    for msg in messages[-6:]:
        role_label = "Student" if msg['role'] == 'user' else "Advisor"
        history_prompt += f"\n{role_label}: {msg['content']}"

    history_prompt += "\nAdvisor:"

    try:
        reply = _generate_with_gemini(
            user_id,
            "chatbot",
            system,
            f"Here is the dialogue history. Respond to the last message.{history_prompt}",
            max_output_tokens=512
        )
        return reply
    except Exception as exc:
        return f"I'm temporarily unavailable. Please try again shortly. ({exc})"


def generate_cover_letter(user_id, profile, career_role, company_name="", tone="professional"):
    """Generate a cover letter tailored to the user's profile and target job role."""
    system = (
        "You are a professional cover letter writer who crafts compelling, "
        "personalised letters that get interviews. "
        "Respond ONLY with valid JSON — no markdown, no preamble."
    )

    name   = profile.get("name") or "Applicant"
    branch = profile.get("branch", "")
    year   = profile.get("year_of_study", "")
    skills = profile.get("technical_skills", "")
    soft   = profile.get("soft_skills", "")
    interests = profile.get("interests", "")
    company_line = f"at {company_name}" if company_name else "at your organisation"
    background = f"{year} {branch} student".strip() if (year or branch) else "student"
    if branch and ("Level" in branch or "Professional" in branch):
        background = f"{branch} professional"

    user_msg = f"""
    Write a {tone} cover letter for:
    - Applicant: {name}, {background}
    - Target role: {career_role} {company_line}
    - Technical skills: {skills}
    - Soft skills: {soft}
    - Interests: {interests}

    Return JSON with exactly these keys:
    {{
      "subject": "Email subject line for this application",
      "cover_letter": "Full cover letter text (3-4 paragraphs, no placeholders, ready to send)"
    }}

    The letter should be specific to the role, highlight relevant skills,
    show enthusiasm, and end with a clear call to action.
    """

    try:
        raw = _generate_with_gemini(user_id, "cover_letter", system, user_msg, max_output_tokens=1024, json_mode=True)
        clean = _extract_json(raw)
        data = json.loads(clean)
        data.setdefault("error", None)
        return data
    except Exception as exc:
        return {
            "subject":      f"Application for {career_role} Position",
            "cover_letter": "Cover letter generation temporarily unavailable.",
            "error":        str(exc),
        }
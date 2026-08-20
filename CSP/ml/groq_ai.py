"""
Groq AI Integration
===================
Powers four AI features using Groq's ultra-fast inference:
  1. Enhanced resume feedback  (AI-written suggestions)
  2. Smart skill gap explanations  (why each skill matters)
  3. AI career advice chatbot  (conversational assistant)
  4. AI-generated cover letters  (profile + target role -> draft)

All functions return plain Python dicts / strings.
They fail gracefully -- if the API key is missing or the call
fails, they return a sensible fallback so the rest of the app
keeps working.

Setup: add  GROQ_API_KEY=gsk_...  to your .env file.
"""

import os
import json
import re
import logging
from datetime import datetime
from groq import Groq

FENCE_RE = re.compile(r'```(?:json)?', re.IGNORECASE)


def _extract_json(raw):
    """
    Robustly pull a JSON object/array out of an LLM response.

    The old approach (FENCE_RE.sub anchored to ^ / $) only worked if the
    reply started with exactly ```json at character 0 and ended with ```
    at the very last character. In practice the model sometimes adds a
    leading blank line, or a sentence like "Here's the cover letter:"
    before the fence, which made json.loads() fail and silently triggered
    the fallback error message for every AI-JSON feature.

    This strips fences wherever they occur, then -- if there's still
    leading/trailing text around the JSON -- extracts the first balanced
    {...} or [...] block instead of assuming the whole string is JSON.
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
        # No JSON structure found — return empty object so json.loads
        # doesn't fail with a confusing error downstream.
        text = '{}'

    return text


GROQ_MODEL = "openai/gpt-oss-120b"
MAX_TOKENS  = 2048

# Non-CSE fallback recommendations (used when AI is unavailable)
_FALLBACK_RECOMMENDATIONS = {
    "CSE": ["Software Developer", "Data Scientist", "Full Stack Developer", "Machine Learning Engineer", "Cloud Engineer"],
    "IT": ["Software Developer", "Web Developer", "Cybersecurity Analyst", "Cloud Engineer", "Database Administrator"],
    "ECE": ["Embedded Systems Engineer", "IoT Engineer", "VLSI Design Engineer", "Network Engineer", "Electronics Design Engineer"],
    "EEE": ["Power Systems Engineer", "Electrical Design Engineer", "Control Systems Engineer", "Renewable Energy Engineer", "Automation Engineer"],
    "MECH": ["Mechanical Design Engineer", "Automotive Engineer", "Production Engineer", "Aerospace Engineer", "Robotics Engineer"],
    "CIVIL": ["Structural Engineer", "Transportation Engineer", "Geotechnical Engineer", "Construction Manager", "Environmental Engineer"],
    "B.Sc": ["Research Scientist", "Data Analyst", "Lab Technician", "Science Educator", "Environmental Consultant"],
    "M.Sc": ["Research Scientist", "Data Scientist", "Biomedical Researcher", "Science Consultant", "R&D Manager"],
    "B.Com": ["Accountant", "Financial Analyst", "Business Analyst", "Tax Consultant", "Auditor"],
    "BBA": ["Business Analyst", "Marketing Manager", "Operations Manager", "Human Resources Manager", "Management Consultant"],
    "MBA": ["Management Consultant", "Investment Banker", "Marketing Manager", "Operations Manager", "Strategy Manager"],
    "BA": ["Content Writer", "Journalist", "Public Relations Specialist", "Social Media Manager", "Copywriter"],
    "MA": ["Content Strategist", "Editor", "UX Writer", "Academic Researcher", "Communications Manager"],
    "BCA": ["Software Developer", "Web Developer", "Data Analyst", "Cybersecurity Analyst", "IT Support Specialist"],
    "MCA": ["Software Developer", "Full Stack Developer", "Cloud Engineer", "Data Scientist", "DevOps Engineer"],
    "CA": ["Chartered Accountant", "Financial Controller", "Tax Consultant", "Auditor", "CFO"],
    "Other": ["Project Manager", "Business Analyst", "Data Analyst", "Content Writer", "Entrepreneur"],
}


def _get_api_keys():
    """
    Collect all configured Groq API keys, in fallback order.

    Reads GROQ_API_KEY (primary) plus GROQ_API_KEY_2 and GROQ_API_KEY_3
    (backups) from the environment. Any of the backup slots can be left
    blank -- they're simply skipped. Add more keys by extending this list
    and adding matching env vars if you ever need a fourth/fifth.
    """
    keys = []
    for var_name in ("GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3"):
        key = os.environ.get(var_name, "").strip()
        if key:
            keys.append((var_name, key))
    if not keys:
        raise RuntimeError(
            "No Groq API key configured. Add GROQ_API_KEY (and optionally "
            "GROQ_API_KEY_2 / GROQ_API_KEY_3 for fallback) to your .env file "
            "and restart."
        )
    return keys


# Clients are cached per API key so we don't reconstruct one on every call.
_client_cache = {}


def _get_client(api_key):
    """Return a (cached) Groq client for the given API key."""
    if api_key not in _client_cache:
        _client_cache[api_key] = Groq(api_key=api_key)
    return _client_cache[api_key]


def _create_completion(**kwargs):
    """
    Call the Groq chat completions endpoint, automatically failing over
    to the next configured API key if the current one errors out
    (rate limit hit, key revoked/invalid, temporary outage, etc).

    This is the single choke point all Groq calls go through, so every
    AI feature in this file (chatbot, cover letters, interview questions,
    quizzes, roadmaps, ...) gets multi-key resilience for free.

    kwargs are passed straight through to client.chat.completions.create()
    (model, messages, max_tokens, temperature, ...).
    """
    keys = _get_api_keys()
    last_exc = None

    for i, (var_name, api_key) in enumerate(keys):
        try:
            client = _get_client(api_key)
            response = client.chat.completions.create(**kwargs)
            if i > 0:
                # We only reach here after at least one earlier key failed.
                logging.warning(
                    f"Groq fallback: {var_name} succeeded after {i} "
                    f"earlier key(s) failed."
                )
            return response
        except Exception as exc:
            last_exc = exc
            logging.warning(
                f"Groq API call failed on {var_name} "
                f"({i + 1}/{len(keys)}): {exc}"
            )
            continue

    # Every configured key failed -- raise the most recent error so the
    # caller's existing except block produces its normal graceful fallback.
    raise last_exc


def _log_ai_request(user_id, feature, status='success', error_message=None):
    """Record the AI request for token tracking."""
    if not user_id:
        return
    try:
        from utils.db import get_db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO ai_requests (user_id, feature, total_tokens, status, error_message)
               VALUES (%s, %s, 1, %s, %s)""",
            (user_id, feature, status, error_message)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _limit_check(user_id):
    """Check if user has exceeded their monthly token limit."""
    if not user_id:
        return True
    try:
        from ml.gemini_ai import get_token_limit_and_warning
        allowed, used, limit, warning = get_token_limit_and_warning(user_id)
        if not allowed:
            raise ValueError(warning)
    except ValueError:
        raise
    except Exception:
        pass
    return True


def _chat(system_prompt, user_message, max_tokens=MAX_TOKENS):
    """Send a single-turn chat request to Groq (with multi-key fallback)."""
    response = _create_completion(
        model=GROQ_MODEL,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


def get_field_relevant_roles(branch="", user_id=None):
    """Get career roles relevant to a specific field of study via AI, with fallback."""
    if not branch:
        return _FALLBACK_RECOMMENDATIONS.get("Other", [])
    try:
        _limit_check(user_id)
    except ValueError:
        pass  # Use fallback
    try:
        system = "You are a career counselor. List exactly 10 career roles most relevant to someone studying a specific field. Return ONLY a JSON array of strings."
        user = f"List 10 career roles suitable for someone with a background in {branch}. Return as JSON array of strings like [\"Role 1\", \"Role 2\", ...]"
        raw = _chat(system, user, max_tokens=600)
        clean = _extract_json(raw)
        data = json.loads(clean)
        if isinstance(data, list) and len(data) > 0:
            return data[:12]
    except Exception:
        pass
    # Fallback to hardcoded dict
    bl = branch.lower()
    for key, roles in _FALLBACK_RECOMMENDATIONS.items():
        if branch == key or bl == key.lower():
            return roles
    for key, roles in _FALLBACK_RECOMMENDATIONS.items():
        if bl in key.lower() or key.lower() in bl:
            return roles
    return _FALLBACK_RECOMMENDATIONS.get("Other", [])


def generate_ai_recommendations(profile, user_id=None):
    """Suggest career roles using AI based on the user's field of study, skills, and interests."""
    try:
        _limit_check(user_id)
    except ValueError:
        return _fallback_recommendations(profile)

    name   = profile.get("name", "User")
    branch = profile.get("branch", "")
    year   = profile.get("year_of_study", "")
    skills = profile.get("technical_skills", "")
    soft   = profile.get("soft_skills", "")
    interests = profile.get("interests", "")
    domains = profile.get("preferred_domains", "")
    academic = profile.get("academic_performance", "")

    system = (
        "You are an expert career counselor with deep knowledge of all academic fields "
        "(Engineering, Science, Commerce, Arts, Management) and their corresponding career paths. "
        "Suggest 5 career roles that best match this person's profile. "
        "Respond ONLY with valid JSON -- no markdown, no preamble."
    )
    user = f"""
Analyze this profile and suggest the 5 most suitable career roles:

Name: {name}
Field of Study: {branch}
Stage: {year}
Technical Skills: {skills}
Soft Skills: {soft}
Interests: {interests}
Preferred Domains: {domains}
Academic Performance: {academic}

Return a JSON array of exactly 5 objects, each with:
{{
  "career_role": "Role Name",
  "match_score": 85,
  "matched_skills": ["skill1", "skill2"],
  "missing_skills": ["skill3", "skill4"],
  "reason": "One sentence why this role fits this profile"
}}

The match_score should be 0-100 based on how well the profile matches each role.
Be specific to the person's field of study - don't suggest tech roles to a commerce student unless they have tech skills.
"""
    try:
        raw = _chat(system, user, max_tokens=1500)
        clean = _extract_json(raw)
        data = json.loads(clean)
        if isinstance(data, list) and len(data) > 0:
            _log_ai_request(user_id, "ai_recommendations", 'success')
            return data[:5]
    except Exception as exc:
        _log_ai_request(user_id, "ai_recommendations", 'failed', str(exc))

    _log_ai_request(user_id, "ai_recommendations", 'fallback')
    return _fallback_recommendations(profile)


def _fallback_recommendations(profile):
    """Return hardcoded recommendations when AI is unavailable, based on field of study."""
    branch = profile.get("branch", "Other").strip()
    bl = branch.lower()
    # Phase 1: exact match (case-insensitive)
    for key, roles in _FALLBACK_RECOMMENDATIONS.items():
        if branch == key or bl == key.lower():
            return [{"career_role": r, "match_score": 70, "matched_skills": [], "missing_skills": [], "reason": f"Recommended for {branch} students"} for r in roles[:5]]
    # Phase 2: substring match (e.g. 'CSE' in 'Computer Science' or vice versa)
    best_key, best_roles = "Other", _FALLBACK_RECOMMENDATIONS["Other"]
    for key, roles in _FALLBACK_RECOMMENDATIONS.items():
        kl = key.lower()
        if kl in bl or bl in kl:
            if len(key) > len(best_key):
                best_key, best_roles = key, roles
    return [{"career_role": r, "match_score": 70, "matched_skills": [], "missing_skills": [], "reason": f"Recommended for {branch} students"} for r in best_roles[:5]]


def generate_ai_skill_gap(user_skills_str, career_role, field_of_study="", user_id=None):
    """Analyze skill gap using AI when role is not in the database."""
    try:
        _limit_check(user_id)
    except ValueError:
        return None
    system = (
        "You are a career coach who analyzes skill gaps across all fields. "
        "Given a person's skills and a target role, determine what they're missing. "
        "Respond ONLY with valid JSON -- no markdown, no preamble."
    )
    user = f"""
User's current skills: {user_skills_str}
Target role: {career_role}
Field of study: {field_of_study or 'General'}

Return a JSON object with exactly this structure:
{{
  "match_percentage": 45,
  "existing_skills": ["skill1", "skill2"],
  "missing_skills": ["skill3", "skill4"],
  "extra_skills": ["skill5"],
  "role_description": "Brief 1-sentence description of this role"
}}

The match_percentage should be 0-100 based on how many required skills the user has.
existing_skills = skills the user has that are relevant to this role.
missing_skills = key skills needed for this role that the user lacks.
extra_skills = user's skills that are not directly required.
"""
    try:
        raw = _chat(system, user, max_tokens=800)
        clean = _extract_json(raw)
        data = json.loads(clean)
        data.setdefault("match_percentage", 50)
        data.setdefault("existing_skills", [])
        data.setdefault("missing_skills", [])
        data.setdefault("extra_skills", [])
        data.setdefault("role_description", "")
        data.setdefault("total_required", len(data.get("missing_skills", [])) + len(data.get("existing_skills", [])))
        data.setdefault("priority_skills", data.get("missing_skills", [])[:5])
        missing = data.get("missing_skills", [])
        data.setdefault("missing_categorized", {
            "beginner": missing[:2] if missing else [],
            "intermediate": missing[2:4] if len(missing) > 2 else [],
            "advanced": missing[4:] if len(missing) > 4 else [],
        })
        data["career_role"] = career_role
        _log_ai_request(user_id, "ai_skill_gap", 'success')
        return data
    except Exception as exc:
        _log_ai_request(user_id, "ai_skill_gap", 'failed', str(exc))
        return None


def generate_ai_courses(field_of_study, skill, career_role, user_id=None):
    """Suggest courses for a given skill using AI."""
    try:
        _limit_check(user_id)
    except ValueError:
        return []

    system = (
        "You are an education advisor who knows courses across all fields. "
        "Suggest 3-4 high-quality courses for a specific skill/role combination. "
        "Respond ONLY with valid JSON -- no markdown, no preamble."
    )
    user = f"""
Suggest courses for:
- Field of Study: {field_of_study}
- Skill: {skill}
- Target Role: {career_role}

Return a JSON array of course objects, each with:
{{
  "course_name": "Course Title",
  "platform": "Platform Name (e.g. Coursera, Udemy, edX, YouTube)",
  "free_paid": "Free or Paid",
  "difficulty": "Beginner/Intermediate/Advanced",
  "link": "https://...",
  "skill": "{skill}"
}}
Recommend 3-4 courses from different platforms when possible.
Only include real, well-known courses.
"""
    try:
        raw = _chat(system, user, max_tokens=1000)
        clean = _extract_json(raw)
        data = json.loads(clean)
        if isinstance(data, list):
            for c in data:
                c.setdefault("free_paid", "Free")
                c.setdefault("difficulty", "Beginner")
                c.setdefault("link", "")
                c.setdefault("skill", skill)
            return data
    except Exception:
        pass
    return []


def get_ai_resume_feedback(resume_text, extracted_skills, resume_score, user_id=None):
    """Generate AI-written resume improvement suggestions."""
    try:
        _limit_check(user_id)
    except ValueError:
        return {
            "overall": "AI feedback temporarily unavailable due to token limits.",
            "strengths": [],
            "improvements": [],
            "ats_tips": [],
            "error": "Monthly token limit exceeded.",
        }
    system = (
        "You are a senior technical recruiter and resume expert at a top tech firm. "
        "Provide concise, actionable feedback. "
        "Respond ONLY with valid JSON -- no markdown, no preamble."
    )

    skills_str = ", ".join(extracted_skills[:20]) if extracted_skills else "none detected"
    user = f"""
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
        raw = _chat(system, user, max_tokens=700)
        clean = _extract_json(raw)
        data = json.loads(clean)
        data.setdefault("error", None)
        _log_ai_request(user_id, "resume_feedback", 'success')
        return data
    except Exception as exc:
        _log_ai_request(user_id, "resume_feedback", 'failed', str(exc))
        return {
            "overall":      "AI feedback temporarily unavailable.",
            "strengths":    [],
            "improvements": [],
            "ats_tips":     [],
            "error":        str(exc),
        }


def get_skill_gap_explanation(career_role, missing_skills, existing_skills, user_id=None, field_of_study=""):
    """Explain *why* each missing skill matters for the target role."""
    try:
        _limit_check(user_id)
    except ValueError:
        return {
            "summary": "AI explanation temporarily unavailable due to token limits.",
            "skill_explanations": [],
            "quick_wins": [],
            "error": "Monthly token limit exceeded.",
        }
    field_context = f" Their background is {field_of_study}." if field_of_study else ""
    system = (
        "You are a career coach who understands skills across all fields "
        "(Engineering, Science, Commerce, Arts, Management, and Technology). "
        "Give practical, motivating guidance. "
        "Respond ONLY with valid JSON -- no markdown, no preamble."
    )

    missing_str  = ", ".join(missing_skills[:10])  if missing_skills  else "none"
    existing_str = ", ".join(existing_skills[:10]) if existing_skills else "none"

    user = f"""
The user wants to become a {career_role}.
They already know: {existing_str}.
They are missing: {missing_str}.{field_context}

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
        raw = _chat(system, user, max_tokens=900)
        clean = _extract_json(raw)
        data = json.loads(clean)
        data.setdefault("error", None)
        _log_ai_request(user_id, "skill_explanation", 'success')
        return data
    except Exception as exc:
        _log_ai_request(user_id, "skill_explanation", 'failed', str(exc))
        return {
            "summary":            "AI explanation temporarily unavailable.",
            "skill_explanations": [],
            "quick_wins":         [],
            "error":              str(exc),
        }


def chat_with_advisor(messages, profile, user_id=None):
    """Multi-turn career advice chatbot."""
    try:
        _limit_check(user_id)
    except ValueError:
        return "AI limits reached. Please try again later or upgrade your plan."
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

    try:
        full_messages = [{"role": "system", "content": system}] + messages
        response = _create_completion(
            model=GROQ_MODEL,
            max_tokens=512,
            messages=full_messages,
            temperature=0.75,
        )
        _log_ai_request(user_id, "chatbot", 'success')
        return response.choices[0].message.content.strip()
    except Exception as exc:
        _log_ai_request(user_id, "chatbot", 'failed', str(exc))
        return f"I'm temporarily unavailable. Please try again shortly. ({exc})"


def generate_cover_letter(profile, career_role, company_name="", tone="professional", user_id=None):
    """Generate a tailored cover letter for a specific role."""
    try:
        _limit_check(user_id)
    except ValueError:
        return _template_cover_letter(profile, career_role, company_name, tone,
                                       error="Monthly token limit exceeded.")
    system = (
        "You are a professional cover letter writer who crafts compelling, "
        "personalised letters that get interviews. "
        "Respond ONLY with valid JSON -- no markdown, no preamble."
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

    user = f"""
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
        raw = _chat(system, user, max_tokens=900)
        clean = _extract_json(raw)
        data = json.loads(clean)
        data.setdefault("error", None)
        _log_ai_request(user_id, "cover_letter", 'success')
        return data
    except Exception as exc:
        _log_ai_request(user_id, "cover_letter", 'failed', str(exc))
        return _template_cover_letter(profile, career_role, company_name, tone,
                                       error=f"Cover letter generation temporarily unavailable. Using template fallback ({exc}).")


def _template_cover_letter(profile, career_role, company_name="", tone="professional", error=None):
    """Generate a template-based cover letter when AI is unavailable."""
    name = profile.get("name") or "Applicant"
    branch = profile.get("branch", "")
    year = profile.get("year_of_study", "")
    skills = profile.get("technical_skills", "")
    soft = profile.get("soft_skills", "")
    interests = profile.get("interests", "")
    company = company_name or "your organisation"

    skills_bullets = ""
    if skills:
        skill_list = [s.strip() for s in skills.split(",") if s.strip()]
        if skill_list:
            skills_bullets = "\n".join(f"    \u2022 {s}" for s in skill_list[:5])
    soft_bullets = ""
    if soft:
        soft_list = [s.strip() for s in soft.split(",") if s.strip()]
        if soft_list:
            soft_bullets = "\n".join(f"    \u2022 {s}" for s in soft_list[:3])

    background = f"{year} {branch} student".strip() if (year or branch) else "student"
    if branch and ("Level" in branch or "Professional" in branch):
        background = f"{branch} professional"

    interest_line = f"I am particularly passionate about {interests}." if interests else ""

    body = (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to express my strong interest in the {career_role} position at {company}. "
        f"As a {background}, I have developed a solid foundation in the skills and knowledge "
        f"required to excel in this role and contribute meaningfully to your team.\n\n"
    )
    if skills_bullets:
        body += (
            f"My technical skills include:\n{skills_bullets}\n\n"
        )
    if soft_bullets:
        body += (
            f"Additionally, I bring strong soft skills such as:\n{soft_bullets}\n\n"
        )
    body += (
        f"{interest_line}\n\n"
        f"I am confident that my combination of technical expertise, dedication, and enthusiasm "
        f"makes me a strong candidate for this position. I am eager to bring my skills to {company} "
        f"and contribute to your continued success.\n\n"
        f"I would welcome the opportunity to discuss how my qualifications align with your needs "
        f"in an interview. Thank you for considering my application.\n\n"
        f"Sincerely,\n{name}"
    )

    result = {
        "subject": f"Application for {career_role} Position",
        "cover_letter": body,
    }
    if error:
        result["error"] = error
    return result


# ====================================================================
# NEW: AI Mock Interview
# ====================================================================

INTERVIEW_QUESTIONS = {
    "general": [
        "Tell me about yourself and your background.",
        "What are your greatest strengths and weaknesses?",
        "Where do you see yourself in five years?",
        "Why did you choose your field of study?",
        "Describe a challenging project you worked on and how you handled it.",
        "How do you handle working under pressure?",
        "Tell me about a time you worked in a team to achieve a goal.",
        "What technical skills are you currently developing?",
    ],
}

def generate_interview_questions(career_role, level="junior", count=6, field_of_study="", user_id=None):
    """Generate AI-powered interview questions for a specific career role."""
    try:
        _limit_check(user_id)
    except ValueError:
        return INTERVIEW_QUESTIONS["general"][:count]
    field_context = f" The candidate's field of study is {field_of_study}. Adjust questions to be relevant to their background." if field_of_study else ""
    try:
        system = f"You are a senior interviewer hiring for {career_role}.{field_context}"
        user = f"Generate {count} interview questions for a {level} {career_role} candidate. Mix of technical and behavioral questions relevant to someone from {field_of_study or 'this field'}. Return as JSON array of strings."
        raw = _chat(system, user, max_tokens=800)
        clean = _extract_json(raw)
        questions = json.loads(clean)
        if isinstance(questions, list) and len(questions) > 0:
            _log_ai_request(user_id, "mock_interview_questions", 'success')
            return questions[:count]
    except Exception:
        pass

    # Fallback to general questions
    _log_ai_request(user_id, "mock_interview_questions", 'success')
    return INTERVIEW_QUESTIONS["general"][:count]


def evaluate_interview_answer(question, answer, career_role, user_id=None, field_of_study=""):
    """Evaluate a candidate's interview answer using AI."""
    try:
        _limit_check(user_id)
    except ValueError:
        return _fallback_evaluate_answer(question, answer, career_role)
    field_context = f" The candidate's field of study is {field_of_study}." if field_of_study else ""
    system = (
        "You are an expert interviewer across all fields (Engineering, Science, Commerce, Arts, Management). "
        "Evaluate the candidate's answer honestly but constructively. "
        f"Return JSON with: score (1-10), feedback (2-3 sentences), "
        "strengths (list of 1-2), improvements (list of 1-2). "
        "Respond ONLY with valid JSON -- no markdown, no preamble."
    )
    user = f"""
Question: {question}
Candidate's Answer: {answer}
Target Role: {career_role}{field_context}
Evaluate this answer and return JSON:
{{
  "score": 8,
  "feedback": "Your answer showed good understanding of...",
  "strengths": ["strength1", "strength2"],
  "improvements": ["improvement1", "improvement2"]
}}
"""
    try:
        raw = _chat(system, user, max_tokens=600)
        clean = _extract_json(raw)
        data = json.loads(clean)
        data.setdefault("error", None)
        _log_ai_request(user_id, "mock_interview_eval", 'success')
        return data
    except Exception as exc:
        _log_ai_request(user_id, "mock_interview_eval", 'failed', str(exc))
        return _fallback_evaluate_answer(question, answer, career_role)


def _fallback_evaluate_answer(question, answer, career_role):
    """Provide fallback interview answer evaluation when AI is unavailable."""
    answer_len = len(answer.split())
    if answer_len < 10:
        score = 3
        feedback = "Your answer was too brief. Try to provide more detail, specific examples, and demonstrate your thought process."
        strengths = ["Attempted to answer"]
        improvements = ["Provide more detail (aim for 3-5 sentences)", "Include specific examples from your experience"]
    elif answer_len < 30:
        score = 6
        feedback = "Good start! Your answer has some substance but could benefit from more structure and specific examples."
        strengths = ["Showed understanding of the topic", "Provided some context"]
        improvements = ["Use the STAR method (Situation, Task, Action, Result)", "Quantify achievements where possible"]
    else:
        score = 8
        feedback = "Strong answer! You provided detailed context and demonstrated good understanding. Consider adding more specific metrics or outcomes."
        strengths = ["Comprehensive response", "Good structure and examples", "Demonstrated relevant knowledge"]
        improvements = ["Try to quantify your impact with specific metrics", "Connect your experience directly to the role requirements"]
    return {
        "score": score,
        "feedback": feedback,
        "strengths": strengths[:2],
        "improvements": improvements[:2],
        "error": None,
    }


# ====================================================================
# NEW: AI Skill Assessment Quiz
# ====================================================================

def generate_skill_quiz(career_role, skill, count=5, user_id=None, field_of_study=""):
    """Generate a quiz to assess knowledge of a specific skill for a career role."""
    try:
        _limit_check(user_id)
    except ValueError:
        return _fallback_quiz_questions(skill, count)
    field_context = f" The user's field of study is {field_of_study}." if field_of_study else ""
    system = (
        "You are a skills assessor across all fields (Engineering, Science, Commerce, Arts, Management). "
        "Generate quiz questions to evaluate a candidate's knowledge of a specific skill. "
        "Return JSON array of objects. "
        "Respond ONLY with valid JSON -- no markdown, no preamble."
    )
    user = f"""
Generate {count} quiz questions about "{skill}" for someone pursuing "{career_role}".{field_context}

Each question should have:
{{
  "question": "What is...",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
  "correct": 0,
  "explanation": "Brief explanation of why this is correct"
}}

Return as a JSON array. Make questions practical and job-relevant.
"""
    try:
        raw = _chat(system, user, max_tokens=1200)
        clean = _extract_json(raw)
        questions = json.loads(clean)
        if isinstance(questions, list) and len(questions) > 0:
            _log_ai_request(user_id, "skill_quiz", 'success')
            return questions[:count]
    except Exception:
        pass

    _log_ai_request(user_id, "skill_quiz", 'failed', "Failed to generate quiz, using fallback")
    return _fallback_quiz_questions(skill, count)


def _fallback_quiz_questions(skill, count=5):
    """Provide fallback quiz questions when Groq API is unavailable."""
    fallback_quizzes = {
        "python": [
            {"question": "What is the correct way to create a list in Python?", "options": ["list = []", "list = {}", "list = ()", "list = <>"], "correct": 0, "explanation": "Square brackets [] create a list in Python."},
            {"question": "Which of the following is a mutable data type in Python?", "options": ["Tuple", "String", "List", "Integer"], "correct": 2, "explanation": "Lists are mutable, meaning their elements can be changed after creation."},
            {"question": "What does the 'len()' function do in Python?", "options": ["Returns the length of an object", "Converts to lowercase", "Creates a new list", "Joins two strings"], "correct": 0, "explanation": "len() returns the number of items in an object like a list, string, or tuple."},
            {"question": "How do you handle exceptions in Python?", "options": ["try-except", "if-else", "switch-case", "for-while"], "correct": 0, "explanation": "try-except blocks are used to handle exceptions in Python."},
            {"question": "What is the output of print(2 ** 3)?", "options": ["6", "8", "9", "5"], "correct": 1, "explanation": "The ** operator performs exponentiation, so 2**3 = 8."},
        ],
        "machine learning": [
            {"question": "What is the purpose of the training set in ML?", "options": ["To train the model", "To test the model", "To validate the model", "To deploy the model"], "correct": 0, "explanation": "The training set is used to train the model on labeled data."},
            {"question": "Which algorithm is used for classification tasks?", "options": ["Linear Regression", "Logistic Regression", "K-Means", "PCA"], "correct": 1, "explanation": "Logistic Regression is used for binary and multi-class classification tasks."},
            {"question": "What is overfitting in machine learning?", "options": ["Model performs well on training but poorly on test", "Model performs poorly on both", "Model performs well on test but poorly on training", "Model cannot learn"], "correct": 0, "explanation": "Overfitting occurs when a model learns noise in the training data and fails to generalize."},
            {"question": "What does the 'fit' method do in scikit-learn?", "options": ["Trains the model", "Predicts the output", "Scores the model", "Transforms the data"], "correct": 0, "explanation": "The fit() method trains the model on the provided training data."},
            {"question": "What is the confusion matrix used for?", "options": ["Evaluating classification performance", "Clustering data", "Reducing dimensions", "Feature selection"], "correct": 0, "explanation": "A confusion matrix shows true positives, false positives, true negatives, and false negatives."},
        ],
        "sql": [
            {"question": "Which SQL statement is used to retrieve data?", "options": ["SELECT", "GET", "RETRIEVE", "FETCH"], "correct": 0, "explanation": "SELECT is used to query and retrieve data from a database."},
            {"question": "What does JOIN do in SQL?", "options": ["Combines rows from two tables", "Deletes a table", "Creates a new database", "Sorts the results"], "correct": 0, "explanation": "JOIN combines columns from one or more tables based on a related column."},
            {"question": "Which clause is used to filter records in SQL?", "options": ["WHERE", "HAVING", "FILTER", "MATCH"], "correct": 0, "explanation": "WHERE is used to filter records that meet a specified condition."},
            {"question": "What is a primary key?", "options": ["A unique identifier for each row", "A foreign key reference", "An index on a column", "A type of join"], "correct": 0, "explanation": "A primary key uniquely identifies each record in a database table."},
            {"question": "Which SQL function counts the number of rows?", "options": ["COUNT()", "SUM()", "TOTAL()", "ROWS()"], "correct": 0, "explanation": "COUNT() returns the number of rows that match a specified condition."},
        ],
    }
    skill_lower = skill.lower().strip()
    for key, questions in fallback_quizzes.items():
        if key in skill_lower or skill_lower in key:
            return questions[:count]
    return [
        {"question": f"What is the main purpose of {skill}?", "options": [f"To solve problems using {skill}", "To create databases", "To design websites", "To manage servers"], "correct": 0, "explanation": f"{skill} is a technology used to solve specific problems in software development."},
        {"question": f"Which industry commonly uses {skill}?", "options": ["Technology", "Healthcare", "Finance", "All of the above"], "correct": 3, "explanation": f"{skill} is widely used across multiple industries including technology, healthcare, and finance."},
    ][:count]


# ====================================================================
# AI-Powered Learning Roadmap
# ====================================================================

def generate_ai_roadmap(career_role, user_skills=None, user_id=None, field_of_study=""):
    """Generate a personalised AI learning roadmap for a career role."""
    try:
        _limit_check(user_id)
    except ValueError:
        return None
    field_context = f" The student's field of study is {field_of_study}." if field_of_study else ""
    system = (
        "You are a senior career coach and educator across all fields. "
        "Create a detailed, practical learning roadmap tailored to the person's background. "
        "Respond ONLY with valid JSON -- no markdown, no preamble."
    )
    user_skills_line = f"The student already knows: {user_skills}." if user_skills else ""
    user = f"""
Create a learning roadmap for becoming a {career_role}.{field_context} {user_skills_line}

Return JSON with exactly this structure:
{{
  "timeline": "Estimated total duration (e.g. 6-8 months)",
  "beginner": {{
    "duration": "1-2 months",
    "skills": ["skill 1", "skill 2", "skill 3", "skill 4"],
    "projects": ["project 1", "project 2"]
  }},
  "intermediate": {{
    "duration": "2-3 months",
    "skills": ["skill 1", "skill 2", "skill 3", "skill 4", "skill 5"],
    "projects": ["project 1", "project 2", "project 3"]
  }},
  "advanced": {{
    "duration": "2-3 months",
    "skills": ["skill 1", "skill 2", "skill 3", "skill 4"],
    "projects": ["project 1", "project 2", "project 3"]
  }},
  "certifications": ["cert 1", "cert 2", "cert 3"]
}}

Make skills specific and practical. Projects should be real, buildable projects.
Certifications should be well-known industry certs.
"""
    try:
        raw = _chat(system, user, max_tokens=1200)
        clean = _extract_json(raw)
        data = json.loads(clean)
        _log_ai_request(user_id, "ai_roadmap", 'success')
        return data
    except Exception as exc:
        _log_ai_request(user_id, "ai_roadmap", 'failed', str(exc))
        return None


# ====================================================================
# AI Career Recommendation Explanation
# ====================================================================

def generate_recommendation_explanation(career_role, match_score, matched_skills, missing_skills, user_id=None, field_of_study=""):
    """Generate an AI explanation for why a career role matches the student."""
    try:
        _limit_check(user_id)
    except ValueError:
        return {
            "summary": f"Based on your skills, {career_role} is a good match ({match_score}% compatibility).",
            "why_match": f"Your existing skills in areas like {matched_skills or 'relevant domains'} align well with this role.",
            "what_to_learn": f"Focus on developing {missing_skills or 'key skills required for this role'} to improve your fit.",
        }
    field_context = f" The student's field of study is {field_of_study}." if field_of_study else ""
    system = (
        "You are a career guidance expert across all academic fields. Give a concise, "
        "personalised explanation of why a career role suits a student based on their skill match and background. "
        "Respond ONLY with valid JSON -- no markdown, no preamble."
    )
    user = f"""
Role: {career_role}
Match Score: {match_score}%
Matched Skills: {matched_skills}
Missing Skills: {missing_skills}{field_context}

Return JSON:
{{
  "summary": "2-3 sentence explanation of why this role fits",
  "why_match": "what the student's existing skills make them a good fit",
  "what_to_learn": "key areas to focus on (1-2 sentences)"
}}
"""
    try:
        raw = _chat(system, user, max_tokens=500)
        clean = _extract_json(raw)
        data = json.loads(clean)
        _log_ai_request(user_id, "recommendation_explanation", 'success')
        return data
    except Exception as exc:
        _log_ai_request(user_id, "recommendation_explanation", 'failed', str(exc))
        return {
            "summary": f"Based on your skills, {career_role} is a good match ({match_score}% compatibility).",
            "why_match": f"Your existing skills in areas like {matched_skills or 'relevant domains'} align well with this role.",
            "what_to_learn": f"Focus on developing {missing_skills or 'key skills required for this role'} to improve your fit.",
        }


# ====================================================================
# NEW: AI Career Insights
# ====================================================================

def get_career_insight(career_role, question, user_id=None, field_of_study=""):
    """Answer a specific career insight question about a role."""
    try:
        _limit_check(user_id)
    except ValueError:
        return _fallback_career_insight(career_role, question)
    field_context = f" The person asking is from {field_of_study} background." if field_of_study else ""
    system = (
        "You are a career insights analyst with deep knowledge of all industries "
        "(Engineering, Science, Commerce, Arts, Management, Technology, Healthcare, Finance). "
        "Give concise, accurate, data-driven answers. Maximum 3-4 sentences."
    )
    user = f"""
Role: {career_role}
Question: {question}{field_context}

Provide a helpful, specific answer about this career role relevant to the person's background.
"""
    try:
        result = _chat(system, user, max_tokens=400)
        _log_ai_request(user_id, "career_insight", 'success')
        return result
    except Exception as exc:
        _log_ai_request(user_id, "career_insight", 'failed', str(exc))
        return _fallback_career_insight(career_role, question)


def _fallback_career_insight(career_role, question):
    """Provide fallback career insights when AI is unavailable."""
    insights = {
        "data scientist": {
            "salary": "Data Scientists typically earn between $90k-$150k annually for entry to mid-level positions in the US, with senior roles exceeding $180k.",
            "skills": "Key skills for Data Scientists include Python, SQL, Machine Learning, Statistics, Data Visualization, and Deep Learning.",
            "growth": "Data Science roles are projected to grow 36% by 2031, much faster than average, driven by increasing data collection across industries.",
        },
        "ml engineer": {
            "salary": "ML Engineers earn $110k-$170k typically, with top companies offering $200k+ for experienced professionals.",
            "skills": "Core skills: Python, TensorFlow/PyTorch, ML algorithms, MLOps, Docker, Kubernetes, and cloud platforms (AWS/GCP/Azure).",
            "growth": "Machine Learning engineering is one of the fastest-growing fields with 40%+ projected growth over the next decade.",
        },
        "software developer": {
            "salary": "Software Developers earn $70k-$130k depending on experience, with senior roles at top tech companies reaching $200k+.",
            "skills": "Essential skills: Programming (Python/Java/JS), Data Structures, Algorithms, Version Control (Git), Databases, and Cloud basics.",
            "growth": "Software development continues to grow at 25% annually, with particular demand in full-stack and cloud-native development.",
        },
    }
    q_lower = question.lower()
    role_key = career_role.lower().strip()
    for key, data in insights.items():
        if key in role_key or role_key in key:
            if "salary" in q_lower:
                return data["salary"]
            elif "skill" in q_lower or "learn" in q_lower or "demand" in q_lower:
                return data["skills"]
            elif "growth" in q_lower or "future" in q_lower or "progression" in q_lower or "career" in q_lower:
                return data["growth"]
    return f"For {career_role}: {question} - This role typically requires relevant technical skills and domain knowledge. Check the market data table above for salary ranges and demand levels."


def generate_personalized_insights(profile, user_id=None):
    """Generate AI-powered personalized career insights based on user's field of study and skills."""
    try:
        _limit_check(user_id)
    except ValueError:
        return None
    branch = profile.get("branch", "")
    skills = profile.get("technical_skills", "")
    soft = profile.get("soft_skills", "")
    interests = profile.get("interests", "")
    system = (
        "You are a career insights analyst specializing in personalized career guidance. "
        "Given a person's academic field, skills, and interests, generate tailored career insights. "
        "Respond ONLY with valid JSON -- no markdown, no preamble."
    )
    user = f"""
Generate personalized career insights for this person:
- Field of Study: {branch or 'General'}
- Technical Skills: {skills or 'None listed'}
- Soft Skills: {soft or 'None listed'}
- Interests: {interests or 'None listed'}

Return JSON with exactly these keys:
{{
  "summary": "2-3 sentence personalized overview of their career landscape based on their field and skills",
  "best_roles": ["Role 1 (1 sentence why it fits)", "Role 2 (1 sentence why it fits)", "Role 3 (1 sentence why it fits)"],
  "skills_to_develop": ["Skill 1 - why it matters", "Skill 2 - why it matters", "Skill 3 - why it matters"],
  "industry_trends": "2-3 sentence summary of relevant industry trends for their field",
  "growth_areas": ["Growth area 1", "Growth area 2", "Growth area 3"]
}}

Be specific to their field of study. If they're in Commerce/Arts, don't suggest tech roles unless their skills justify it.
"""
    try:
        raw = _chat(system, user, max_tokens=800)
        clean = _extract_json(raw)
        data = json.loads(clean)
        _log_ai_request(user_id, "personalized_insights", 'success')
        return data
    except Exception as exc:
        _log_ai_request(user_id, "personalized_insights", 'failed', str(exc))
        return None
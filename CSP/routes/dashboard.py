"""
Dashboard Routes (Security & Gemini Upgrade)
=============================================
Handles dashboard stats, career roadmap generations, skill-gap analysis,
career advice chatbot, PDF report downloads, and security settings.
Integrates Gemini token calculations and user warning notifications.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g, current_app
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from utils.db import get_db
from ml.recommender import get_recommendations_for_user
from ml.skill_gap import analyze_skill_gap, get_course_recommendations, generate_roadmap
from ml.groq_ai import (
    chat_with_advisor,
    generate_cover_letter,
    generate_interview_questions,
    evaluate_interview_answer,
    generate_skill_quiz,
    get_skill_gap_explanation,
    generate_recommendation_explanation,
    generate_ai_roadmap,
    get_career_insight,
    generate_ai_recommendations,
    generate_ai_courses,
    generate_ai_skill_gap,
    get_field_relevant_roles,
    generate_personalized_insights,
)
from ml.gemini_ai import (
    get_token_limit_and_warning,
    get_monthly_token_usage
)
from utils.jwt_auth import rate_limit, log_system_event

dashboard_bp = Blueprint('dashboard', __name__)


# ══════════════════════════════════════════════════════════════
# STUDENT DASHBOARD
# ══════════════════════════════════════════════════════════════

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    """Main student dashboard showing recommendations, resume stats, and token usages."""
    conn = get_db()
    cursor = conn.cursor()

    # Fetch student profile
    cursor.execute("SELECT * FROM student_profiles WHERE user_id = %s", (current_user.id,))
    profile = cursor.fetchone()

    # Fetch recommendations
    cursor.execute(
        "SELECT * FROM recommendations WHERE user_id = %s ORDER BY match_score DESC",
        (current_user.id,)
    )
    recommendations = cursor.fetchall()

    # Fetch latest resume
    cursor.execute(
        "SELECT * FROM resumes WHERE user_id = %s ORDER BY uploaded_at DESC LIMIT 1",
        (current_user.id,)
    )
    resume = cursor.fetchone()

    # Fetch all career roles for cover letter dropdown
    cursor.execute("SELECT role_name FROM career_roles ORDER BY role_name")
    cover_roles = [r['role_name'] for r in cursor.fetchall()]

    # Fetch unread notifications
    cursor.execute(
        "SELECT * FROM notifications WHERE user_id = %s AND is_read = 0 ORDER BY created_at DESC",
        (current_user.id,)
    )
    notifications = cursor.fetchall()

    # Fetch token stats
    allowed, used_tokens, limit_tokens, warning = get_token_limit_and_warning(current_user.id)
    token_percentage = min((used_tokens / limit_tokens) * 100, 100) if limit_tokens > 0 else 0

    conn.close()

    return render_template(
        'dashboard.html',
        profile=profile,
        recommendations=recommendations,
        resume=resume,
        notifications=notifications,
        token_used=used_tokens,
        token_limit=limit_tokens,
        token_percentage=token_percentage,
        token_warning=warning,
        cover_roles=cover_roles
    )


@dashboard_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Edit student profile with skills, interests, etc."""
    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        name = request.form.get('name', '')
        branch = request.form.get('branch', '')
        year_of_study = request.form.get('year_of_study', '')
        technical_skills = request.form.get('technical_skills', '')
        soft_skills = request.form.get('soft_skills', '')
        interests = request.form.get('interests', '')
        preferred_domains = request.form.get('preferred_domains', '')
        academic_performance = request.form.get('academic_performance', '')

        cursor.execute('''
            UPDATE student_profiles SET
                name = %s, branch = %s, year_of_study = %s,
                technical_skills = %s, soft_skills = %s, interests = %s,
                preferred_domains = %s, academic_performance = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
        ''', (name, branch, year_of_study, technical_skills, soft_skills,
              interests, preferred_domains, academic_performance, current_user.id))
        conn.commit()
        conn.close()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('dashboard.dashboard'))

    cursor.execute("SELECT * FROM student_profiles WHERE user_id = %s", (current_user.id,))
    profile = cursor.fetchone()
    conn.close()
    return render_template('profile.html', profile=profile)


@dashboard_bp.route('/recommendations')
@login_required
def get_recommendations():
    """AI-powered career roles matching based on field of study + skills."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM student_profiles WHERE user_id = %s", (current_user.id,))
    profile = cursor.fetchone()
    conn.close()

    if not profile:
        flash('Please complete your profile first.', 'warning')
        return redirect(url_for('dashboard.dashboard'))

    profile_dict = dict(profile)

    # Try AI-based recommendations first (field-aware)
    ai_recs = generate_ai_recommendations(profile_dict, user_id=current_user.id)
    if ai_recs and len(ai_recs) > 0:
        # Save AI recs to DB
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM recommendations WHERE user_id = %s", (current_user.id,))
        for rec in ai_recs:
            matched = ",".join(rec.get("matched_skills", []))
            missing = ",".join(rec.get("missing_skills", []))
            cursor.execute('''
                INSERT INTO recommendations (user_id, career_role, match_score, matched_skills, missing_skills)
                VALUES (%s, %s, %s, %s, %s)
            ''', (current_user.id, rec["career_role"], rec.get("match_score", 70), matched, missing))
        conn.commit()
        conn.close()
        flash(f'AI found {len(ai_recs)} career recommendations for your profile!', 'success')
        return redirect(url_for('dashboard.dashboard'))

    # Fallback: CSV-based matching
    if not profile_dict.get('technical_skills'):
        flash('Please add technical skills to your profile for better recommendations.', 'warning')
        return redirect(url_for('dashboard.dashboard'))

    recommendations = get_recommendations_for_user(current_user.id)
    if recommendations:
        flash(f'Found {len(recommendations)} career recommendations for you!', 'success')
    else:
        flash('Could not generate recommendations. Please update your profile.', 'warning')

    return redirect(url_for('dashboard.dashboard'))


@dashboard_bp.route('/recommendation-explain/<path:career_role>')
@login_required
def recommendation_explain(career_role):
    """AI explanation for why a career role matches the student."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT matched_skills, missing_skills, match_score FROM recommendations WHERE user_id = %s AND career_role = %s", (current_user.id, career_role))
    rec = cursor.fetchone()
    cursor.execute("SELECT technical_skills, branch FROM student_profiles WHERE user_id = %s", (current_user.id,))
    profile_row = cursor.fetchone()
    conn.close()

    if not rec or not profile_row:
        return jsonify({"error": "No data found"}), 404

    profile_dict = dict(profile_row)
    branch = profile_dict.get('branch', '')
    result = generate_recommendation_explanation(
        career_role=career_role,
        match_score=rec['match_score'],
        matched_skills=rec['matched_skills'],
        missing_skills=rec['missing_skills'],
        user_id=current_user.id,
        field_of_study=branch,
    )
    if not result:
        return jsonify({"error": "AI explanation unavailable"}), 503
    return jsonify(result)


# ══════════════════════════════════════════════════════════════
# SKILL GAP AND ROADMAP
# ══════════════════════════════════════════════════════════════

@dashboard_bp.route('/skill-gap/<career_role>')
@login_required
def skill_gap(career_role):
    """Analyze student's skills vs target career role requirements."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM student_profiles WHERE user_id = %s", (current_user.id,))
    profile = cursor.fetchone()
    conn.close()

    if not profile:
        flash('Please complete your profile first.', 'warning')
        return redirect(url_for('dashboard.dashboard'))

    profile_dict = dict(profile)
    user_skills = (profile_dict.get('technical_skills', '') or '') + ',' + (profile_dict.get('soft_skills', '') or '')
    branch = profile_dict.get('branch', '')
    gap_analysis = analyze_skill_gap(user_skills, career_role)

    if not gap_analysis:
        gap_analysis = generate_ai_skill_gap(user_skills, career_role, field_of_study=branch, user_id=current_user.id)

    if not gap_analysis:
        flash(f'Career role "{career_role}" not found and AI analysis unavailable.', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    courses = get_course_recommendations(gap_analysis.get('missing_skills', []), career_role)
    if not courses and gap_analysis.get('missing_skills'):
        ai_course = generate_ai_courses(branch, gap_analysis['missing_skills'][0], career_role, user_id=current_user.id)
        if ai_course:
            courses = ai_course

    return render_template(
        'skill_gap.html',
        analysis=gap_analysis,
        courses=courses,
        career_role=career_role
    )


@dashboard_bp.route('/roadmap/<career_role>')
@login_required
def roadmap(career_role):
    """Generates sequential learning roadmaps using AI, falls back to hardcoded."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM career_roles WHERE role_name = %s", (career_role,))
    role = cursor.fetchone()

    cursor.execute("SELECT technical_skills, branch FROM student_profiles WHERE user_id = %s", (current_user.id,))
    profile_row = cursor.fetchone()
    user_skills = profile_row['technical_skills'] if profile_row else None
    user_branch = profile_row['branch'] if profile_row else ''
    conn.close()

    roadmap_data = generate_ai_roadmap(career_role, user_skills=user_skills, user_id=current_user.id, field_of_study=user_branch)
    if not roadmap_data:
        roadmap_data = generate_roadmap(career_role)

    courses = []
    if role:
        all_skills = (role['required_technical_skills'] or '').split(',')
        courses = get_course_recommendations([s.strip() for s in all_skills], career_role)
    if not courses and roadmap_data:
        first_skills = []
        for level in ['beginner', 'intermediate', 'advanced']:
            if level in roadmap_data:
                first_skills.extend(roadmap_data[level].get('skills', []))
        if first_skills:
            ai_course = generate_ai_courses(user_branch, first_skills[0], career_role, user_id=current_user.id)
            if ai_course:
                courses = ai_course

    return render_template(
        'roadmap.html',
        roadmap=roadmap_data or {},
        career_role=career_role,
        courses=courses
    )


@dashboard_bp.route('/download-report')
@login_required
def download_report():
    """Generates PDF analysis report for download."""
    from utils.report_generator import generate_career_report

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM student_profiles WHERE user_id = %s", (current_user.id,))
    profile = cursor.fetchone()

    cursor.execute(
        "SELECT * FROM recommendations WHERE user_id = %s ORDER BY match_score DESC",
        (current_user.id,)
    )
    recommendations = cursor.fetchall()

    cursor.execute(
        "SELECT * FROM resumes WHERE user_id = %s ORDER BY uploaded_at DESC LIMIT 1",
        (current_user.id,)
    )
    resume = cursor.fetchone()
    conn.close()

    if not profile:
        flash('Please complete your profile first.', 'warning')
        return redirect(url_for('dashboard.dashboard'))

    pdf_path = generate_career_report(
        profile=dict(profile) if profile else {},
        recommendations=[dict(r) for r in recommendations] if recommendations else [],
        resume=dict(resume) if resume else None,
        username=current_user.username
    )

    from flask import send_file
    return send_file(pdf_path, as_attachment=True, download_name='Career_Report.pdf')


# ══════════════════════════════════════════════════════════════
# SECURITY SETTINGS & AI HISTORY
# ══════════════════════════════════════════════════════════════

@dashboard_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Account settings: password updates, OAuth unlinking, and AI usage metrics."""
    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'change_password':
            current_pwd = request.form.get('current_password', '')
            new_pwd = request.form.get('new_password', '')
            confirm_pwd = request.form.get('confirm_password', '')

            cursor.execute("SELECT password_hash FROM users WHERE id = %s", (current_user.id,))
            user_row = cursor.fetchone()
            
            # Form validation
            from routes.auth import is_strong_password
            ok, msg = is_strong_password(new_pwd)

            if not user_row or not check_password_hash(user_row['password_hash'], current_pwd):
                flash('Incorrect current password.', 'danger')
            elif not ok:
                flash(msg, 'danger')
            elif new_pwd != confirm_pwd:
                flash('Passwords do not match.', 'danger')
            else:
                new_hash = generate_password_hash(new_pwd)
                cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, current_user.id))
                conn.commit()
                flash('Password updated successfully!', 'success')
                log_system_event('info', f"Password changed for user: {current_user.username}")

        elif action == 'unlink_oauth':
            provider = request.form.get('provider')
            
            # Ensure they have password fallback before unlinking
            cursor.execute("SELECT password_hash, email FROM users WHERE id = %s", (current_user.id,))
            user_row = cursor.fetchone()
            
            # Simple check if password is set (standard length check or mock check)
            if not user_row or not user_row['password_hash']:
                flash('You must set an account password first before unlinking social logins.', 'danger')
            else:
                if provider == 'google':
                    cursor.execute("UPDATE users SET google_id = NULL WHERE id = %s", (current_user.id,))
                elif provider == 'github':
                    cursor.execute("UPDATE users SET github_id = NULL WHERE id = %s", (current_user.id,))
                conn.commit()
                flash(f'Successfully unlinked {provider.capitalize()} account.', 'success')

    # Fetch User metadata (OAuth status)
    cursor.execute("SELECT google_id, github_id, created_at FROM users WHERE id = %s", (current_user.id,))
    user_meta = cursor.fetchone()

    # Fetch AI requests logs
    cursor.execute(
        "SELECT * FROM ai_requests WHERE user_id = %s ORDER BY timestamp DESC LIMIT 20",
        (current_user.id,)
    )
    ai_history = cursor.fetchall()

    conn.close()

    return render_template(
        'settings.html', 
        user_meta=user_meta, 
        ai_history=ai_history
    )


@dashboard_bp.route('/notifications/read/<int:notif_id>')
@login_required
def read_notification(notif_id):
    """Mark warning alerts as read."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE id = %s AND user_id = %s", (notif_id, current_user.id))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('dashboard.dashboard'))


# ══════════════════════════════════════════════════════════════
# AI AJAX ENDPOINTS (GEMINI INTEGRATION)
# ══════════════════════════════════════════════════════════════

@dashboard_bp.route('/ai-chat', methods=['POST'])
@login_required
@rate_limit(limit=10, period=60)
def ai_chat():
    """Gemini-powered interactive chatbot route."""
    data = request.get_json(silent=True) or {}
    messages = data.get('messages', [])

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM student_profiles WHERE user_id = %s", (current_user.id,))
    profile = cursor.fetchone()
    conn.close()

    profile_dict = dict(profile) if profile else {}
    
    try:
        reply = chat_with_advisor(messages, profile_dict, user_id=current_user.id)
        return jsonify({"reply": reply})
    except ValueError as val_err:
        return jsonify({"reply": f"AI limits reached: {str(val_err)}"}), 403
    except Exception as exc:
        return jsonify({"reply": f"AI error: {str(exc)}"}), 500


@dashboard_bp.route('/generate-cover-letter', methods=['POST'])
@login_required
@rate_limit(limit=5, period=60)
def generate_cover_letter_route():
    """Generates custom cover letters using student parameters."""
    data = request.get_json(silent=True) or {}
    career_role  = data.get('career_role', '')
    company_name = data.get('company_name', '')
    tone         = data.get('tone', 'professional')

    if not career_role:
        return jsonify({"error": "career_role is required"}), 400

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM student_profiles WHERE user_id = %s", (current_user.id,))
        profile = cursor.fetchone()
        conn.close()

        profile_dict = dict(profile) if profile else {}

        result = generate_cover_letter(profile_dict, career_role, company_name, tone, user_id=current_user.id)
        return jsonify(result)
    except ValueError as val_err:
        return jsonify({"error": f"AI limits reached: {str(val_err)}"}), 403
    except Exception as exc:
        # Anything unexpected (DB hiccup, etc.) still comes back as JSON so
        # the frontend's res.json() doesn't choke on an HTML error page --
        # log the real traceback server-side so it's still debuggable.
        current_app.logger.exception("generate_cover_letter_route failed")
        return jsonify({"error": f"Cover letter generation failed: {exc}"}), 500


@dashboard_bp.route('/interview')
@login_required
def interview_page():
    """Render the AI mock interview page."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT branch FROM student_profiles WHERE user_id = %s", (current_user.id,))
    prof_row = cursor.fetchone()
    conn.close()
    branch = prof_row['branch'] if prof_row else ''
    roles = get_field_relevant_roles(branch, user_id=current_user.id)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM mock_interviews WHERE user_id = %s ORDER BY started_at DESC LIMIT 5",
        (current_user.id,)
    )
    history = cursor.fetchall()
    conn.close()
    return render_template('interview.html', roles=roles, history=history)


@dashboard_bp.route('/quiz')
@login_required
def quiz_page():
    """Render the skill assessment quiz page."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT branch FROM student_profiles WHERE user_id = %s", (current_user.id,))
    prof_row = cursor.fetchone()
    conn.close()
    branch = prof_row['branch'] if prof_row else ''
    roles = get_field_relevant_roles(branch, user_id=current_user.id)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT skill, best_score, confidence, taken_at FROM (
               SELECT DISTINCT ON (skill) skill, score AS best_score, confidence, taken_at
               FROM skill_assessments
               WHERE user_id = %s
               ORDER BY skill, score DESC, taken_at DESC
           ) AS best_per_skill
           ORDER BY taken_at DESC LIMIT 10""",
        (current_user.id,)
    )
    history = cursor.fetchall()
    conn.close()
    return render_template('skill_assessment.html', roles=roles, history=history)


@dashboard_bp.route('/insights')
@login_required
def insights_page():
    """Render the career insights page with field-relevant roles."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT branch FROM student_profiles WHERE user_id = %s", (current_user.id,))
    prof_row = cursor.fetchone()
    conn.close()
    branch = prof_row['branch'] if prof_row else ''
    field_roles = get_field_relevant_roles(branch, user_id=current_user.id)
    market_data = []
    # Get market data only for field-relevant roles, fallback to all roles
    if field_roles:
        placeholders = ','.join(['%s'] * len(field_roles))
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(f"SELECT role_name, avg_salary_min, avg_salary_max, demand_level, growth_rate, description FROM career_roles WHERE role_name IN ({placeholders}) ORDER BY demand_level", field_roles)
        market_data = cursor.fetchall()
        conn.close()
    if not market_data:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT role_name, avg_salary_min, avg_salary_max, demand_level, growth_rate, description FROM career_roles ORDER BY demand_level")
        market_data = cursor.fetchall()
        conn.close()
    # Generate AI-powered personalized insights based on user's field + skills
    insights_prof = None
    conn2 = get_db()
    cur2 = conn2.cursor()
    cur2.execute("SELECT * FROM student_profiles WHERE user_id = %s", (current_user.id,))
    insights_prof = cur2.fetchone()
    conn2.close()
    personalized_insights = None
    if insights_prof:
        personalized_insights = generate_personalized_insights(dict(insights_prof), user_id=current_user.id)
    return render_template('career_insights.html', market_data=market_data, personalized_insights=personalized_insights)


@dashboard_bp.route('/courses')
@login_required
def courses_page():
    """Render the course tracking page."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM course_progress WHERE user_id = %s ORDER BY started_at DESC",
        (current_user.id,)
    )
    progress = cursor.fetchall()
    cursor.execute("SELECT branch FROM student_profiles WHERE user_id = %s", (current_user.id,))
    prof_row = cursor.fetchone()
    conn.close()
    branch = prof_row['branch'] if prof_row else ''
    roles = get_field_relevant_roles(branch, user_id=current_user.id)
    return render_template('course_tracker.html', progress=progress, roles=roles)


@dashboard_bp.route('/ai-skill-explanation/<path:career_role>', methods=['GET'])
@login_required
@rate_limit(limit=5, period=60)
def ai_skill_explanation(career_role):
    """Provides detailed analysis explaining skill gap requirements."""
    from ml.skill_gap import analyze_skill_gap

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM student_profiles WHERE user_id = %s", (current_user.id,))
    profile = cursor.fetchone()
    conn.close()

    if not profile:
        return jsonify({"error": "Profile not found"}), 404

    profile_dict = dict(profile)
    user_skills = (profile_dict.get('technical_skills', '') or '') + ',' + (profile_dict.get('soft_skills', '') or '')
    gap = analyze_skill_gap(user_skills, career_role)

    if not gap:
        return jsonify({"error": f"Role '{career_role}' not found"}), 404

    branch = profile_dict.get('branch', '')
    try:
        result = get_skill_gap_explanation(
            career_role=career_role,
            missing_skills=gap.get('missing_skills', []),
            existing_skills=gap.get('existing_skills', []),
            user_id=current_user.id,
            field_of_study=branch,
        )
        return jsonify(result)
    except ValueError as val_err:
        return jsonify({"error": f"AI limits reached: {str(val_err)}"}), 403
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ══════════════════════════════════════════════════════════════
# AI MOCK INTERVIEW SYSTEM
# ══════════════════════════════════════════════════════════════

@dashboard_bp.route('/interview/start', methods=['POST'])
@login_required
@rate_limit(limit=5, period=60)
def start_interview():
    """Start a new AI mock interview for a career role."""
    data = request.get_json(silent=True) or {}
    career_role = data.get('career_role', '')
    level = data.get('level', 'junior')

    if not career_role:
        return jsonify({"error": "career_role is required"}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT branch FROM student_profiles WHERE user_id = %s", (current_user.id,))
    prof = cursor.fetchone()
    field = prof['branch'] if prof else ''

    questions = generate_interview_questions(career_role, level, count=6, field_of_study=field, user_id=current_user.id)

    cursor.execute(
        """INSERT INTO mock_interviews (user_id, career_role, status, question_count)
           VALUES (%s, %s, 'in_progress', %s)
           RETURNING id""",
        (current_user.id, career_role, len(questions))
    )
    interview_id = cursor.fetchone()['id']

    for i, q in enumerate(questions):
        cursor.execute(
            """INSERT INTO interview_qa (interview_id, question, question_order)
               VALUES (%s, %s, %s)""",
            (interview_id, q, i)
        )

    conn.commit()
    conn.close()

    return jsonify({
        "interview_id": interview_id,
        "career_role": career_role,
        "questions": questions,
        "total": len(questions),
    })


@dashboard_bp.route('/interview/answer', methods=['POST'])
@login_required
def submit_answer():
    """Submit an answer for the current interview question."""
    data = request.get_json(silent=True) or {}
    interview_id = data.get('interview_id')
    question = data.get('question', '')
    answer = data.get('answer', '')
    career_role = data.get('career_role', '')

    if not all([interview_id, question, answer]):
        return jsonify({"error": "Missing required fields"}), 400

    conn2 = get_db()
    cur2 = conn2.cursor()
    cur2.execute("SELECT branch FROM student_profiles WHERE user_id = %s", (current_user.id,))
    prof = cur2.fetchone()
    conn2.close()
    field = prof['branch'] if prof else ''

    evaluation = evaluate_interview_answer(question, answer, career_role, user_id=current_user.id, field_of_study=field)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE interview_qa SET answer = %s, feedback = %s, score = %s
           WHERE interview_id = %s AND question = %s""",
        (answer, evaluation.get('feedback', ''), evaluation.get('score', 0),
         interview_id, question)
    )
    cursor.execute(
        """UPDATE mock_interviews SET current_question = current_question + 1
           WHERE id = %s""",
        (interview_id,)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "score": evaluation.get('score', 0),
        "feedback": evaluation.get('feedback', ''),
        "strengths": evaluation.get('strengths', []),
        "improvements": evaluation.get('improvements', []),
    })


@dashboard_bp.route('/interview/<int:interview_id>/complete', methods=['POST'])
@login_required
def complete_interview(interview_id):
    """Complete and score the interview."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM mock_interviews WHERE id = %s AND user_id = %s",
        (interview_id, current_user.id)
    )
    interview = cursor.fetchone()
    if not interview:
        conn.close()
        return jsonify({"error": "Interview not found"}), 404

    cursor.execute(
        "SELECT score, feedback FROM interview_qa WHERE interview_id = %s AND score IS NOT NULL",
        (interview_id,)
    )
    answers = cursor.fetchall()

    total_score = 0
    count = 0
    all_feedback = []
    for row in answers:
        if row['score']:
            total_score += row['score']
            count += 1
        if row['feedback']:
            all_feedback.append(row['feedback'])

    avg_score = round(total_score / count, 1) if count > 0 else 0

    cursor.execute(
        """UPDATE mock_interviews SET status = 'completed', score = %s,
           completed_at = CURRENT_TIMESTAMP WHERE id = %s""",
        (int(avg_score * 10), interview_id)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "score": int(avg_score * 10),
        "total_answers": count,
        "feedback_summary": all_feedback,
        "career_role": interview['career_role'],
    })


@dashboard_bp.route('/interview/history')
@login_required
def interview_history():
    """View past interview results."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM mock_interviews WHERE user_id = %s
           ORDER BY started_at DESC LIMIT 10""",
        (current_user.id,)
    )
    interviews = cursor.fetchall()
    conn.close()
    return jsonify([dict(i) for i in interviews])


# ══════════════════════════════════════════════════════════════
# AI SKILL ASSESSMENT QUIZ
# ══════════════════════════════════════════════════════════════

@dashboard_bp.route('/quiz/generate', methods=['POST'])
@login_required
@rate_limit(limit=10, period=60)
def generate_quiz():
    """Generate a skill assessment quiz."""
    data = request.get_json(silent=True) or {}
    career_role = data.get('career_role', '')
    skill = data.get('skill', '')
    count = min(int(data.get('count', 5)), 10)

    if not skill:
        return jsonify({"error": "skill is required"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT branch FROM student_profiles WHERE user_id = %s", (current_user.id,))
    prof = cursor.fetchone()
    conn.close()
    field = prof['branch'] if prof else ''

    questions = generate_skill_quiz(career_role, skill, count=count, user_id=current_user.id, field_of_study=field)
    return jsonify({"questions": questions, "skill": skill, "career_role": career_role})


@dashboard_bp.route('/quiz/submit', methods=['POST'])
@login_required
def submit_quiz():
    """Submit quiz answers and get assessment."""
    data = request.get_json(silent=True) or {}
    career_role = data.get('career_role', '')
    skill = data.get('skill', '')
    answers = data.get('answers', [])

    correct = 0
    for a in answers:
        if a.get('selected') == a.get('correct'):
            correct += 1

    total = len(answers)
    score = round((correct / total) * 100) if total > 0 else 0

    if score >= 80:
        confidence = "advanced"
    elif score >= 50:
        confidence = "intermediate"
    else:
        confidence = "beginner"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO skill_assessments
           (user_id, career_role, skill, score, total_questions, correct_answers, confidence)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (current_user.id, career_role, skill, score, total, correct, confidence)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "score": score,
        "correct": correct,
        "total": total,
        "confidence": confidence,
    })


@dashboard_bp.route('/quiz/history')
@login_required
def quiz_history():
    """View quiz assessment history."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM skill_assessments WHERE user_id = %s
           ORDER BY taken_at DESC LIMIT 20""",
        (current_user.id,)
    )
    results = cursor.fetchall()
    conn.close()
    return jsonify([dict(r) for r in results])


# ══════════════════════════════════════════════════════════════
# COURSE PROGRESS TRACKING
# ══════════════════════════════════════════════════════════════

@dashboard_bp.route('/course/start', methods=['POST'])
@login_required
def start_course():
    """Mark a course as started."""
    data = request.get_json(silent=True) or {}
    career_role = data.get('career_role', '')
    skill = data.get('skill', '')
    course_name = data.get('course_name', '')

    if not all([career_role, skill, course_name]):
        return jsonify({"error": "Missing required fields"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO course_progress
           (user_id, career_role, skill, course_name, status, started_at)
           VALUES (%s, %s, %s, %s, 'in_progress', CURRENT_TIMESTAMP)
           ON CONFLICT (user_id, course_name) DO NOTHING""",
        (current_user.id, career_role, skill, course_name)
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "started"})


@dashboard_bp.route('/course/complete', methods=['POST'])
@login_required
def complete_course():
    """Mark a course as completed."""
    data = request.get_json(silent=True) or {}
    course_name = data.get('course_name', '')
    rating = data.get('rating')

    if not course_name:
        return jsonify({"error": "course_name is required"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE course_progress SET status = 'completed',
           completed_at = CURRENT_TIMESTAMP, rating = %s
           WHERE user_id = %s AND course_name = %s""",
        (rating, current_user.id, course_name)
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "completed"})


@dashboard_bp.route('/course/progress')
@login_required
def course_progress():
    """Get course progress for the current user."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM course_progress WHERE user_id = %s
           ORDER BY started_at DESC""",
        (current_user.id,)
    )
    progress = cursor.fetchall()
    conn.close()
    return jsonify([dict(p) for p in progress])


# ══════════════════════════════════════════════════════════════
# CAREER INSIGHTS
# ══════════════════════════════════════════════════════════════

@dashboard_bp.route('/career-insight', methods=['POST'])
@login_required
@rate_limit(limit=10, period=60)
def career_insight():
    """Get AI-powered insight about a career role or question."""
    data = request.get_json(silent=True) or {}
    career_role = data.get('career_role', '')
    question = data.get('question', '')

    if not career_role or not question:
        return jsonify({"error": "career_role and question are required"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT branch FROM student_profiles WHERE user_id = %s", (current_user.id,))
    prof = cursor.fetchone()
    conn.close()
    field = prof['branch'] if prof else ''

    result = get_career_insight(career_role, question, user_id=current_user.id, field_of_study=field)
    return jsonify({"reply": result})


@dashboard_bp.route('/career-insight/analyze-role', methods=['POST'])
@login_required
@rate_limit(limit=5, period=60)
def analyze_role():
    """Get end-to-end AI analysis for a career role."""
    data = request.get_json(silent=True) or {}
    career_role = data.get('career_role', '')
    if not career_role:
        return jsonify({"error": "career_role is required"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT branch FROM student_profiles WHERE user_id = %s", (current_user.id,))
    prof = cursor.fetchone()
    conn.close()
    field = prof['branch'] if prof else ''

    try:
        field_suffix = f" for someone in {field}" if field else ""
        salary  = get_career_insight(career_role, f"What is the average salary range for this role{field_suffix}", user_id=current_user.id, field_of_study=field)
        skills  = get_career_insight(career_role, f"What are the top technical and soft skills required{field_suffix}", user_id=current_user.id, field_of_study=field)
        growth  = get_career_insight(career_role, f"What is the growth outlook, demand level, and future prospects{field_suffix}", user_id=current_user.id, field_of_study=field)
        roadmap = get_career_insight(career_role, f"What is the typical career progression and learning roadmap{field_suffix}", user_id=current_user.id, field_of_study=field)
        return jsonify({"salary": salary, "skills": skills, "growth": growth, "roadmap": roadmap})
    except Exception as exc:
        return jsonify({"error": f"Analysis failed: {exc}"}), 500
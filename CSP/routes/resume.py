"""
Resume Routes
=============
Handles resume file upload, parsing, and analysis.
Supports PDF and DOCX file formats.
"""

import os
import io
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from utils.db import get_db

# ── Create Blueprint ──
resume_bp = Blueprint('resume', __name__, url_prefix='/resume')

# Allowed file extensions for resume upload
ALLOWED_EXTENSIONS = {'pdf', 'docx'}


def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ──────────────────────────────────────────────
# UPLOAD - Resume upload page
# ──────────────────────────────────────────────
@resume_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """
    GET  → Show the resume upload form
    POST → Process the uploaded file, extract data, and analyze
    """
    if request.method == 'POST':
        # Check if a file was submitted
        if 'resume' not in request.files:
            flash('No file selected. Please choose a resume file.', 'danger')
            return redirect(request.url)

        file = request.files['resume']

        if file.filename == '':
            flash('No file selected. Please choose a resume file.', 'danger')
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash('Invalid file type. Please upload a PDF or DOCX file.', 'danger')
            return redirect(request.url)

        # ── Save the uploaded file ──
        filename = secure_filename(file.filename)
        # Add user ID prefix to avoid name conflicts
        unique_filename = f"user_{current_user.id}_{filename}"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)

        # ── Optional Job Description to match the resume against ──
        job_description = request.form.get('job_description', '').strip()

        # ── Analyze the resume ──
        try:
            from ml.resume_analyzer import analyze_resume
            analysis = analyze_resume(filepath, jd_text=job_description or None)

            # ── Save results to database ──
            conn = get_db()
            cursor = conn.cursor()

            # Delete old resume records for this user (keep only latest)
            cursor.execute("DELETE FROM resumes WHERE user_id = %s", (current_user.id,))

            cursor.execute('''
                INSERT INTO resumes 
                (user_id, filename, filepath, extracted_skills, education,
                 experience, projects, certifications, resume_score, analysis_result,
                 jd_text, jd_match_result)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                current_user.id,
                filename,
                filepath,
                ','.join(analysis.get('skills', [])),
                json.dumps(analysis.get('education', [])),
                json.dumps(analysis.get('experience', [])),
                json.dumps(analysis.get('projects', [])),
                json.dumps(analysis.get('certifications', [])),
                analysis.get('resume_score', 0),
                json.dumps(analysis.get('analysis', {})),
                job_description or None,
                json.dumps(analysis.get('jd_match')) if analysis.get('jd_match') else None
            ))

            conn.commit()
            conn.close()

            flash(f'Resume analyzed successfully! Score: {analysis.get("resume_score", 0)}/100', 'success')
            return redirect(url_for('resume.results'))

        except Exception as e:
            flash(f'Error analyzing resume: {str(e)}', 'danger')
            return redirect(request.url)

    return render_template('resume_upload.html')


# ──────────────────────────────────────────────
# RESULTS - Show resume analysis results
# ──────────────────────────────────────────────
@resume_bp.route('/results')
@login_required
def results():
    """Display the results of the most recent resume analysis."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM resumes WHERE user_id = %s ORDER BY uploaded_at DESC LIMIT 1",
        (current_user.id,)
    )
    resume = cursor.fetchone()
    conn.close()

    if not resume:
        flash('No resume found. Please upload a resume first.', 'warning')
        return redirect(url_for('resume.upload'))

    # Parse JSON fields for display
    resume_data = dict(resume)
    try:
        resume_data['analysis'] = json.loads(resume_data.get('analysis_result', '{}'))
        resume_data['education_list'] = json.loads(resume_data.get('education', '[]'))
        resume_data['experience_list'] = json.loads(resume_data.get('experience', '[]'))
        resume_data['projects_list'] = json.loads(resume_data.get('projects', '[]'))
        resume_data['certifications_list'] = json.loads(resume_data.get('certifications', '[]'))
        resume_data['skills_list'] = resume_data.get('extracted_skills', '').split(',')
    except (json.JSONDecodeError, TypeError):
        resume_data['analysis'] = {}
        resume_data['education_list'] = []
        resume_data['experience_list'] = []
        resume_data['projects_list'] = []
        resume_data['certifications_list'] = []
        resume_data['skills_list'] = []

    try:
        resume_data['jd_match'] = json.loads(resume_data.get('jd_match_result') or 'null')
    except (json.JSONDecodeError, TypeError):
        resume_data['jd_match'] = None

    return render_template('resume_results.html', resume=resume_data)


# ──────────────────────────────────────────────
# AI FEEDBACK  – Gemini-powered resume feedback
# ──────────────────────────────────────────────
@resume_bp.route('/ai-feedback', methods=['GET'])
@login_required
def ai_feedback():
    """
    Returns AI-written resume feedback as JSON.
    Called via AJAX from resume_results.html.
    """
    from ml.groq_ai import get_ai_resume_feedback
    from ml.resume_analyzer import extract_text

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM resumes WHERE user_id = %s ORDER BY uploaded_at DESC LIMIT 1",
        (current_user.id,)
    )
    resume = cursor.fetchone()
    conn.close()

    if not resume:
        return jsonify({"error": "No resume found. Please upload a resume first."}), 404

    # Extract raw text from the saved file for Gemini to read
    filepath = resume['filepath']
    resume_text = ""
    if filepath and os.path.exists(filepath):
        try:
            resume_text = extract_text(filepath)
        except Exception:
            resume_text = resume.get('extracted_skills', '')

    skills_list = [s.strip() for s in (resume['extracted_skills'] or '').split(',') if s.strip()]
    result = get_ai_resume_feedback(
        resume_text=resume_text,
        extracted_skills=skills_list,
        resume_score=int(resume['resume_score'] or 0),
        user_id=current_user.id,
        jd_text=resume.get('jd_text') or '',
    )

    # Persist the AI feedback so it can also be included in the downloadable report
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE resumes SET ai_feedback_result = %s WHERE id = %s",
            (json.dumps(result), resume['id'])
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    return jsonify(result)


# ──────────────────────────────────────────────
# DOWNLOAD - Export the full analysis as a PDF
# ──────────────────────────────────────────────
@resume_bp.route('/download')
@login_required
def download():
    """Generate and download the resume analysis report as a PDF file."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM resumes WHERE user_id = %s ORDER BY uploaded_at DESC LIMIT 1",
        (current_user.id,)
    )
    resume = cursor.fetchone()
    conn.close()

    if not resume:
        flash('No resume found. Please upload a resume first.', 'warning')
        return redirect(url_for('resume.upload'))

    resume_data = dict(resume)
    try:
        resume_data['analysis'] = json.loads(resume_data.get('analysis_result') or '{}')
        resume_data['education_list'] = json.loads(resume_data.get('education') or '[]')
        resume_data['experience_list'] = json.loads(resume_data.get('experience') or '[]')
        resume_data['projects_list'] = json.loads(resume_data.get('projects') or '[]')
        resume_data['certifications_list'] = json.loads(resume_data.get('certifications') or '[]')
        resume_data['skills_list'] = [s.strip() for s in (resume_data.get('extracted_skills') or '').split(',') if s.strip()]
    except (json.JSONDecodeError, TypeError):
        resume_data['analysis'] = {}
        resume_data['education_list'] = []
        resume_data['experience_list'] = []
        resume_data['projects_list'] = []
        resume_data['certifications_list'] = []
        resume_data['skills_list'] = []

    try:
        resume_data['jd_match'] = json.loads(resume_data.get('jd_match_result') or 'null')
    except (json.JSONDecodeError, TypeError):
        resume_data['jd_match'] = None

    try:
        resume_data['ai_feedback'] = json.loads(resume_data.get('ai_feedback_result') or 'null')
    except (json.JSONDecodeError, TypeError):
        resume_data['ai_feedback'] = None

    from utils.report_generator import generate_resume_report_pdf
    pdf_bytes = generate_resume_report_pdf(resume_data)

    download_name = f"Resume_Analysis_{current_user.id}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=download_name
    )
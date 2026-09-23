"""
Resume Report Generator
========================
Renders the resume analysis (score, extracted sections, JD match,
AI feedback) into a downloadable PDF using fpdf2 (already a project
dependency -- no new packages required).

Compatible with: routes/resume.py → download()
"""

from fpdf import FPDF
from fpdf.enums import XPos, YPos


PRIMARY = (37, 99, 235)      # blue
SUCCESS = (25, 135, 84)      # green
WARNING = (255, 152, 0)      # amber
DANGER = (220, 53, 69)       # red
MUTED = (108, 117, 125)      # gray
DARK = (33, 37, 41)


def _score_color(score):
    if score >= 70:
        return SUCCESS
    if score >= 40:
        return WARNING
    return DANGER


class ResumeReportPDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 16)
        self.set_text_color(*PRIMARY)
        self.cell(0, 10, 'Smart Career Navigator - Resume Analysis Report', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*PRIMARY)
        self.set_line_width(0.6)
        self.line(10, 20, 200, 20)
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(*MUTED)
        self.cell(0, 10, f'Page {self.page_no()}', align='C')

    def section_title(self, text, color=DARK):
        self.set_font('Helvetica', 'B', 13)
        self.set_text_color(*color)
        self.cell(0, 9, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*DARK)
        self.ln(1)

    def body_text(self, text, size=10, style=''):
        self.set_font('Helvetica', style, size)
        self.set_text_color(*DARK)
        self.multi_cell(0, 6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def bullet_list(self, items, empty_message="None detected"):
        self.set_font('Helvetica', '', 10)
        self.set_text_color(*DARK)
        if not items:
            self.set_text_color(*MUTED)
            self.cell(0, 6, f'- {empty_message}', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_text_color(*DARK)
            return
        for item in items:
            clean = str(item).encode('latin-1', 'replace').decode('latin-1')
            self.multi_cell(0, 6, f'- {clean}', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)


def _safe(text):
    """fpdf2's core fonts are Latin-1 only; drop characters it can't render."""
    if text is None:
        return ''
    return str(text).encode('latin-1', 'replace').decode('latin-1')


def generate_resume_report_pdf(resume_data):
    """
    Build the PDF report.

    Args:
        resume_data: dict shaped like the one built in routes/resume.py
                      (results()/download()) -- filename, resume_score,
                      skills_list, education_list, experience_list,
                      projects_list, certifications_list, analysis,
                      jd_match (optional), ai_feedback (optional)

    Returns:
        bytes -- the PDF file content
    """
    pdf = ResumeReportPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    filename = _safe(resume_data.get('filename', 'Resume'))
    score = resume_data.get('resume_score', 0) or 0
    analysis = resume_data.get('analysis') or {}

    # ── Score summary ──
    pdf.body_text(f'File: {filename}', size=11, style='B')
    pdf.set_font('Helvetica', 'B', 28)
    pdf.set_text_color(*_score_color(score))
    pdf.cell(0, 16, f'{score:.0f} / 100', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('Helvetica', '', 11)
    pdf.set_text_color(*DARK)
    pdf.cell(0, 7, f"Overall Rating: {_safe(analysis.get('overall_rating', 'N/A'))}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    # ── Score breakdown ──
    breakdown = analysis.get('breakdown') or {}
    if breakdown:
        pdf.section_title('Score Breakdown', PRIMARY)
        max_scores = {'skills': 25, 'education': 15, 'projects': 20,
                      'experience': 20, 'certifications': 10, 'contact': 5, 'depth': 5}
        for section, points in breakdown.items():
            cap = max_scores.get(section, 1)
            pdf.body_text(f"{section.replace('_', ' ').title()}: {points}/{cap}")
        pdf.ln(2)

    # ── Extracted sections ──
    pdf.section_title('Extracted Skills', PRIMARY)
    pdf.bullet_list(resume_data.get('skills_list', []), 'No skills detected')

    pdf.section_title('Education', PRIMARY)
    pdf.bullet_list(resume_data.get('education_list', []), 'No education details detected')

    pdf.section_title('Projects', PRIMARY)
    pdf.bullet_list(resume_data.get('projects_list', []), 'No projects detected')

    pdf.section_title('Experience', PRIMARY)
    pdf.bullet_list(resume_data.get('experience_list', []), 'No experience details detected')

    pdf.section_title('Certifications', PRIMARY)
    pdf.bullet_list(resume_data.get('certifications_list', []), 'No certifications detected')

    # ── Improvement suggestions (rule-based) ──
    suggestions = analysis.get('suggestions') or []
    if suggestions:
        pdf.section_title('Improvement Suggestions', WARNING)
        for s in suggestions:
            msg = s.get('message', s) if isinstance(s, dict) else s
            pdf.bullet_list([msg])

    missing_sections = analysis.get('missing_sections') or []
    if missing_sections:
        pdf.section_title('Missing Sections', DANGER)
        pdf.bullet_list(missing_sections)

    # ── Job Description match ──
    jd_match = resume_data.get('jd_match')
    if jd_match:
        pdf.add_page()
        pdf.section_title('Job Description Match', PRIMARY)
        pdf.set_font('Helvetica', 'B', 20)
        pdf.set_text_color(*_score_color(jd_match.get('match_score', 0)))
        pdf.cell(0, 12, f"{jd_match.get('match_score', 0)}% - {_safe(jd_match.get('match_rating', ''))}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*DARK)
        pdf.ln(1)

        pdf.body_text('Matched Skills:', style='B')
        pdf.bullet_list(jd_match.get('matched_skills', []), 'None')

        pdf.body_text('Missing Skills (present in JD, not in resume):', style='B')
        pdf.bullet_list(jd_match.get('missing_skills', []), 'None')

        jd_suggestions = jd_match.get('suggestions') or []
        if jd_suggestions:
            pdf.body_text('JD Match Suggestions:', style='B')
            pdf.bullet_list(jd_suggestions)

    # ── AI feedback (Groq) ──
    ai_feedback = resume_data.get('ai_feedback')
    if ai_feedback and not ai_feedback.get('error'):
        pdf.add_page()
        pdf.section_title('AI Resume Feedback (Groq AI)', PRIMARY)
        if ai_feedback.get('overall'):
            pdf.body_text(_safe(ai_feedback['overall']))
            pdf.ln(2)

        pdf.body_text('Strengths:', style='B')
        pdf.bullet_list(ai_feedback.get('strengths', []))

        pdf.body_text('Improvements:', style='B')
        pdf.bullet_list(ai_feedback.get('improvements', []))

        pdf.body_text('ATS Tips:', style='B')
        pdf.bullet_list(ai_feedback.get('ats_tips', []))

        if ai_feedback.get('jd_fit'):
            pdf.body_text('Fit for the target Job Description:', style='B')
            pdf.bullet_list([ai_feedback['jd_fit']])

    output = pdf.output()
    return bytes(output)

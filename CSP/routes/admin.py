"""
Admin Routes (Analytics & Security Upgrade)
============================================
Handles admin dashboard statistics, career roles datasets, course recommendations,
student account control (block/unblock, token adjustments), and system log viewers.
Protected with JWT admin authentication guards.
"""

import os
import json
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from utils.db import get_db
from utils.jwt_auth import admin_required, log_system_event

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ──────────────────────────────────────────────
# ADMIN DASHBOARD & ANALYTICS
# ──────────────────────────────────────────────

@admin_bp.route('/')
@login_required
@admin_required
def admin_panel():
    """Main administrative view showing analytics, global token usages, and recent activities."""
    conn = get_db()
    cursor = conn.cursor()

    # Base counts
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'student'")
    student_count = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM career_roles")
    roles_count = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM courses")
    courses_count = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM resumes")
    resumes_count = cursor.fetchone()['count']

    # AI Stats
    cursor.execute("SELECT COUNT(*) as count FROM ai_requests")
    ai_requests_count = cursor.fetchone()['count']

    cursor.execute("SELECT SUM(total_tokens) as total FROM ai_requests")
    total_tokens_row = cursor.fetchone()
    total_tokens_count = total_tokens_row['total'] if total_tokens_row and total_tokens_row['total'] is not None else 0

    cursor.execute("SELECT COUNT(*) as count FROM ai_requests WHERE status = 'failed'")
    failed_requests_count = cursor.fetchone()['count']

    # Distinct active users in the last 30 days
    cutoff_date = (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "SELECT COUNT(DISTINCT user_id) as count FROM ai_requests WHERE timestamp >= %s",
        (cutoff_date,)
    )
    active_users_count = cursor.fetchone()['count']

    # Recent student registrations
    cursor.execute('''
        SELECT u.id, u.username, u.email, u.created_at, u.is_blocked, u.token_limit,
               sp.branch, sp.year_of_study
        FROM users u
        LEFT JOIN student_profiles sp ON u.id = sp.user_id
        WHERE u.role = 'student'
        ORDER BY u.created_at DESC
        LIMIT 8
    ''')
    recent_students = cursor.fetchall()

    conn.close()

    stats = {
        'students': student_count,
        'roles': roles_count,
        'courses': courses_count,
        'resumes': resumes_count,
        'ai_requests': ai_requests_count,
        'total_tokens': total_tokens_count,
        'failed_requests': failed_requests_count,
        'active_users': active_users_count
    }

    return render_template('admin.html', stats=stats, students=recent_students)


# ──────────────────────────────────────────────
# SYSTEM LOGS VIEW
# ──────────────────────────────────────────────

@admin_bp.route('/logs')
@login_required
@admin_required
def view_system_logs():
    """Reads and displays system activity logs from the local text file."""
    log_file_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
        'database', 
        'system.log'
    )
    
    logs = []
    if os.path.exists(log_file_path):
        try:
            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                logs = f.readlines()[-150:]  # Fetch last 150 entries
            logs.reverse()  # Reverse to place newest logs at the top
        except Exception as e:
            logs = [f"Error reading log file: {str(e)}"]
    else:
        logs = ["No system log file generated yet."]

    return render_template('admin_logs.html', logs=logs)


# ──────────────────────────────────────────────
# USER MANAGEMENT (BLOCK, LIMITS)
# ──────────────────────────────────────────────

@admin_bp.route('/students')
@login_required
@admin_required
def view_students():
    """Displays user tables detailing study status, verification details, and block states."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.id, u.username, u.email, u.created_at, u.is_blocked, u.token_limit, u.is_verified,
               sp.name, sp.branch, sp.year_of_study, sp.technical_skills
        FROM users u
        LEFT JOIN student_profiles sp ON u.id = sp.user_id
        WHERE u.role = 'student'
        ORDER BY u.created_at DESC
    ''')
    students = cursor.fetchall()
    
    # Calculate token usage for each student to display in admin dashboard
    students_list = []
    for s in students:
        s_dict = dict(s)
        cursor.execute("SELECT SUM(total_tokens) as total FROM ai_requests WHERE user_id = %s", (s['id'],))
        total_row = cursor.fetchone()
        s_dict['used_tokens'] = total_row['total'] if total_row and total_row['total'] is not None else 0
        students_list.append(s_dict)
        
    conn.close()
    return render_template('admin_students.html', students=students_list)


@admin_bp.route('/students/toggle-block/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_block_student(user_id):
    """Toggle the suspended block state of a student account."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT is_blocked, username FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        flash('User not found.', 'danger')
        return redirect(url_for('admin.view_students'))

    new_block = 0 if row['is_blocked'] else 1
    cursor.execute("UPDATE users SET is_blocked = %s WHERE id = %s", (new_block, user_id))
    conn.commit()
    conn.close()

    status_str = "blocked" if new_block else "unblocked"
    flash(f"User '{row['username']}' has been {status_str} successfully.", 'success')
    log_system_event('warning', f"Admin toggled user state: {row['username']} is now {status_str}.")
    
    return redirect(url_for('admin.view_students'))


@admin_bp.route('/students/set-limit/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def set_token_limit(user_id):
    """Adjust individual monthly token usage limits."""
    new_limit = request.form.get('token_limit', type=int)
    
    if new_limit is None or new_limit < 0:
        flash('Invalid token limit value.', 'danger')
        return redirect(url_for('admin.view_students'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        flash('User not found.', 'danger')
        return redirect(url_for('admin.view_students'))

    cursor.execute("UPDATE users SET token_limit = %s WHERE id = %s", (new_limit, user_id))
    conn.commit()
    conn.close()

    flash(f"Monthly token limit for '{row['username']}' set to {new_limit:,}.", 'success')
    log_system_event('info', f"Admin adjusted token limit for {row['username']} to {new_limit}.")
    
    return redirect(url_for('admin.view_students'))


# ──────────────────────────────────────────────
# CAREER ROLES & COURSES MANAGEMENT
# ──────────────────────────────────────────────

@admin_bp.route('/roles')
@login_required
@admin_required
def manage_roles():
    """Display all career roles for management."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM career_roles ORDER BY role_name")
    roles = cursor.fetchall()
    conn.close()
    return render_template('admin_roles.html', roles=roles)


@admin_bp.route('/roles/add', methods=['POST'])
@login_required
@admin_required
def add_role():
    """Add a new career role to the database."""
    role_name = request.form.get('role_name', '').strip()
    technical_skills = request.form.get('required_technical_skills', '').strip()
    soft_skills = request.form.get('required_soft_skills', '').strip()
    preferred_domains = request.form.get('preferred_domains', '').strip()
    description = request.form.get('description', '').strip()
    min_skill_match = request.form.get('min_skill_match', 60, type=int)
    avg_salary_min = request.form.get('avg_salary_min', type=int)
    avg_salary_max = request.form.get('avg_salary_max', type=int)
    demand_level = request.form.get('demand_level', 'Medium').strip()
    growth_rate = request.form.get('growth_rate', '').strip()
    related_roles = request.form.get('related_roles', '').strip()

    if not role_name:
        flash('Role name is required.', 'danger')
        return redirect(url_for('admin.manage_roles'))

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO career_roles 
            (role_name, required_technical_skills, required_soft_skills, 
             preferred_domains, description, min_skill_match,
             avg_salary_min, avg_salary_max, demand_level, growth_rate, related_roles)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (role_name, technical_skills, soft_skills,
              preferred_domains, description, min_skill_match,
              avg_salary_min, avg_salary_max, demand_level, growth_rate, related_roles))
        conn.commit()
        flash(f'Career role "{role_name}" added successfully!', 'success')
        log_system_event('info', f"Admin added role: {role_name}")
    except Exception as e:
        flash(f'Error adding role: {str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('admin.manage_roles'))


@admin_bp.route('/roles/edit/<int:role_id>', methods=['POST'])
@login_required
@admin_required
def edit_role(role_id):
    """Update an existing career role."""
    role_name = request.form.get('role_name', '').strip()
    technical_skills = request.form.get('required_technical_skills', '').strip()
    soft_skills = request.form.get('required_soft_skills', '').strip()
    preferred_domains = request.form.get('preferred_domains', '').strip()
    description = request.form.get('description', '').strip()
    min_skill_match = request.form.get('min_skill_match', 60, type=int)
    avg_salary_min = request.form.get('avg_salary_min', type=int)
    avg_salary_max = request.form.get('avg_salary_max', type=int)
    demand_level = request.form.get('demand_level', 'Medium').strip()
    growth_rate = request.form.get('growth_rate', '').strip()
    related_roles = request.form.get('related_roles', '').strip()

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE career_roles 
            SET role_name=%s, required_technical_skills=%s, required_soft_skills=%s,
                preferred_domains=%s, description=%s, min_skill_match=%s,
                avg_salary_min=%s, avg_salary_max=%s, demand_level=%s, growth_rate=%s, related_roles=%s
            WHERE id=%s
        ''', (role_name, technical_skills, soft_skills,
              preferred_domains, description, min_skill_match,
              avg_salary_min, avg_salary_max, demand_level, growth_rate, related_roles, role_id))
        conn.commit()
        flash(f'Role "{role_name}" updated successfully!', 'success')
        log_system_event('info', f"Admin updated role: {role_name}")
    except Exception as e:
        flash(f'Error updating role: {str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('admin.manage_roles'))


@admin_bp.route('/roles/delete/<int:role_id>', methods=['POST'])
@login_required
@admin_required
def delete_role(role_id):
    """Delete a career role from the database."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT role_name FROM career_roles WHERE id = %s", (role_id,))
        row = cursor.fetchone()
        role_name = row['role_name'] if row else ""
        
        cursor.execute("DELETE FROM career_roles WHERE id = %s", (role_id,))
        conn.commit()
        flash('Career role deleted successfully.', 'success')
        log_system_event('info', f"Admin deleted role: {role_name}")
    except Exception as e:
        flash(f'Error deleting role: {str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('admin.manage_roles'))


# ──────────────────────────────────────────────
# COURSES MANAGEMENT
# ──────────────────────────────────────────────

@admin_bp.route('/courses')
@login_required
@admin_required
def manage_courses():
    """Display all courses for management."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM courses ORDER BY skill, difficulty")
    courses = cursor.fetchall()
    conn.close()
    return render_template('admin_courses.html', courses=courses)


@admin_bp.route('/courses/add', methods=['POST'])
@login_required
@admin_required
def add_course():
    """Add a new course to the database."""
    skill = request.form.get('skill', '').strip()
    course_name = request.form.get('course_name', '').strip()
    platform = request.form.get('platform', '').strip()
    free_paid = request.form.get('free_paid', 'Free').strip()
    difficulty = request.form.get('difficulty', 'Beginner').strip()
    link = request.form.get('link', '').strip()
    career_roles = request.form.get('career_roles', '').strip()

    if not skill or not course_name:
        flash('Skill and course name are required.', 'danger')
        return redirect(url_for('admin.manage_courses'))

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO courses 
            (skill, course_name, platform, free_paid, difficulty, link, career_roles)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (skill, course_name, platform, free_paid, difficulty, link, career_roles))
        conn.commit()
        flash(f'Course "{course_name}" added successfully!', 'success')
        log_system_event('info', f"Admin added course: {course_name}")
    except Exception as e:
        flash(f'Error adding course: {str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('admin.manage_courses'))


@admin_bp.route('/courses/delete/<int:course_id>', methods=['POST'])
@login_required
@admin_required
def delete_course(course_id):
    """Delete a course from the database."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT course_name FROM courses WHERE id = %s", (course_id,))
        row = cursor.fetchone()
        course_name = row['course_name'] if row else ""
        
        cursor.execute("DELETE FROM courses WHERE id = %s", (course_id,))
        conn.commit()
        flash('Course deleted successfully.', 'success')
        log_system_event('info', f"Admin deleted course: {course_name}")
    except Exception as e:
        flash(f'Error deleting course: {str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('admin.manage_courses'))

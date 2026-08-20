"""
Authentication Routes (JWT & MFA Upgrade)
===========================================
Handles user registration, verification via email OTP, password resets,
secure JWT authentication with cookie tokens, and Google/GitHub OAuth.
Includes simulated sandbox logins for testing environment without keys.
"""

import os
import re
import random
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from requests_oauthlib import OAuth2Session
from utils.db import get_db
from models import User
from utils.jwt_auth import generate_tokens, rotate_refresh_token, rate_limit, log_system_event
from utils.email_service import send_otp_email, send_password_reset_email

auth_bp = Blueprint('auth', __name__)

# Allow OAuth2Session to work over plain http (127.0.0.1) during local development.
# Google/GitHub normally require https for redirect URIs; this relaxes that check
# for oauthlib on localhost only. Do NOT enable this in a real production deployment.
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

# Real OAuth credentials (falls back to sandbox simulator if either ID or secret is missing)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "").strip()
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "").strip()

GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

GITHUB_AUTHORIZATION_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


def is_strong_password(password):
    """Validate password strength (min 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special char)."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character."
    return True, ""


# ══════════════════════════════════════════════════════════════
# REGISTER & OTP VERIFICATION
# ══════════════════════════════════════════════════════════════

@auth_bp.route('/register', methods=['GET', 'POST'])
@rate_limit(limit=5, period=60)
def register():
    """Register a new student account and initiate email verification."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Input validation
        errors = []
        if len(username) < 3:
            errors.append('Username must be at least 3 characters.')
        if '@' not in email:
            errors.append('Please enter a valid email address.')
        
        ok, msg = is_strong_password(password)
        if not ok:
            errors.append(msg)
        if password != confirm_password:
            errors.append('Passwords do not match.')

        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('register.html')

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
        existing = cursor.fetchone()

        if existing:
            flash('Username or email already registered.', 'danger')
            conn.close()
            return render_template('register.html')

        # Create account (unverified)
        try:
            password_hash = generate_password_hash(password)
            # Generate 6-digit OTP
            otp = f"{random.randint(100000, 999999)}"
            expiry = (datetime.utcnow() + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')

            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role, otp, otp_expiry, is_verified)
                VALUES (%s, %s, %s, %s, %s, %s, 0)
                RETURNING id
                """,
                (username, email, password_hash, 'student', otp, expiry)
            )
            user_id = cursor.fetchone()['id']

            # Create profiles record
            cursor.execute(
                "INSERT INTO student_profiles (user_id, name) VALUES (%s, %s)",
                (user_id, username)
            )
            conn.commit()

            # Attempt to send OTP email
            _, mode = send_otp_email(email, otp, username)
            session['verification_email'] = email
            
            if mode == 'sandbox':
                flash("Developer Mode: Check the terminal console log to find your OTP code.", "info")
            
            flash('Registration successful! A verification code has been sent to your email.', 'success')
            log_system_event('info', f"New user registration (unverified): {username} ({email})")
            return redirect(url_for('auth.verify_otp'))

        except Exception as e:
            flash(f'Registration failed: {str(e)}', 'danger')
            log_system_event('error', f"Registration error for {username}: {str(e)}")
        finally:
            conn.close()

    return render_template('register.html')


@auth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    """Verify the registration OTP code."""
    email = session.get('verification_email')
    if not email:
        flash('No pending verification found. Please register or login.', 'warning')
        return redirect(url_for('auth.register'))

    if request.method == 'POST':
        otp_input = request.form.get('otp', '').strip()
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user_row = cursor.fetchone()

        if not user_row:
            conn.close()
            flash('Account not found.', 'danger')
            return redirect(url_for('auth.register'))

        stored_otp = user_row["otp"]
        otp_expiry = user_row["otp_expiry"]

        # SQLite returns string, PostgreSQL returns datetime
        if isinstance(otp_expiry, str):
            otp_expiry = datetime.strptime(
                otp_expiry,
                "%Y-%m-%d %H:%M:%S"
            )

        if not stored_otp or stored_otp != otp_input:
            conn.close()
            flash("Invalid verification code.", "danger")
            return render_template("verify_otp.html", email=email)

        if otp_expiry and otp_expiry < datetime.utcnow():
            conn.close()
            flash("Verification code has expired. Please request a new one.", "danger")
            return render_template("verify_otp.html", email=email)

        # Mark user verified and clear OTP
        cursor.execute(
            "UPDATE users SET is_verified = 1, otp = NULL, otp_expiry = NULL WHERE email = %s",
            (email,)
        )
        conn.commit()

        # Log user in and issue JWT cookies
        user = User(user_row['id'], user_row['username'], user_row['email'], user_row['role'])
        login_user(user)

        access_token, refresh_token = generate_tokens(user.id, user.role)

        flash('Email verified successfully! Welcome to your dashboard.', 'success')
        log_system_event('info', f"User email verified: {user.username} ({email})")
        session.pop('verification_email', None)
        conn.close()

        response = redirect(url_for('dashboard.dashboard'))
        response.set_cookie('access_token', access_token, httponly=True, samesite='Lax', max_age=900)
        response.set_cookie('refresh_token', refresh_token, httponly=True, samesite='Lax', max_age=604800)
        return response

    return render_template('verify_otp.html', email=email)


@auth_bp.route('/resend-otp')
@rate_limit(limit=3, period=120)
def resend_otp():
    """Generate and resend a new OTP code to the registered email."""
    email = session.get('verification_email') or session.get('reset_email')
    if not email:
        flash('Session expired. Please request verification again.', 'warning')
        return redirect(url_for('auth.login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE email = %s", (email,))
    user_row = cursor.fetchone()

    if not user_row:
        conn.close()
        flash('Account not found.', 'danger')
        return redirect(url_for('auth.register'))

    otp = f"{random.randint(100000, 999999)}"
    expiry = (datetime.utcnow() + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute(
        "UPDATE users SET otp = %s, otp_expiry = %s WHERE email = %s",
        (otp, expiry, email)
    )
    conn.commit()
    conn.close()

    _, mode = send_otp_email(email, otp, user_row['username'])
    
    if mode == 'sandbox':
        flash("Developer Mode: Check the terminal console log to find your new OTP code.", "info")
    
    flash('A new verification code has been sent.', 'success')
    return redirect(request.referrer or url_for('auth.verify_otp'))


# ══════════════════════════════════════════════════════════════
# PASSWORD MANAGEMENT (FORGOT/RESET)
# ══════════════════════════════════════════════════════════════

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Request password reset via OTP."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username FROM users WHERE email = %s", (email,))
        user_row = cursor.fetchone()

        if user_row:
            otp = f"{random.randint(100000, 999999)}"
            expiry = (datetime.utcnow() + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')

            cursor.execute(
                "UPDATE users SET otp = %s, otp_expiry = %s WHERE email = %s",
                (otp, expiry, email)
            )
            conn.commit()
            conn.close()

            _, mode = send_password_reset_email(email, otp, user_row['username'])
            session['reset_email'] = email

            if mode == 'sandbox':
                flash("Developer Mode: Check the terminal console log for the reset code.", "info")
            flash('A password reset code has been sent to your email.', 'success')
            return redirect(url_for('auth.reset_password'))
        else:
            conn.close()
            # Security best practice: don't reveal email existence
            flash('If the email is registered, a reset code has been sent.', 'success')
            return redirect(url_for('auth.reset_password'))

    return render_template('forgot_password.html')


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Reset password using OTP validation."""
    email = session.get('reset_email')

    if not email:
        flash('Please request a password reset first.', 'warning')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        otp_input = request.form.get('otp', '').strip()
        new_password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # -------------------------
        # Password validation
        # -------------------------
        errors = []

        ok, msg = is_strong_password(new_password)

        if not ok:
            errors.append(msg)

        if new_password != confirm_password:
            errors.append('Passwords do not match.')

        if errors:
            for error in errors:
                flash(error, 'danger')

            return render_template(
                'reset_password.html',
                email=email
            )

        conn = None
        cursor = None

        try:
            conn = get_db()
            cursor = conn.cursor()

            # -------------------------
            # Get user
            # -------------------------
            cursor.execute(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )

            user_row = cursor.fetchone()

            if not user_row:
                flash('Error validating account.', 'danger')
                return redirect(url_for('auth.forgot_password'))

            # -------------------------
            # Get OTP
            # -------------------------
            stored_otp = user_row['otp']
            expiry = user_row['otp_expiry']

            # -------------------------
            # Validate OTP
            # -------------------------
            if not stored_otp or stored_otp != otp_input:
                flash('Invalid reset code.', 'danger')

                return render_template(
                    'reset_password.html',
                    email=email
                )

            # -------------------------
            # Validate expiry
            # -------------------------
            if expiry:
 
                # PostgreSQL may already return
                # a Python datetime object.
                if isinstance(expiry, str):
                    expiry = datetime.strptime(
                        expiry,
                        '%Y-%m-%d %H:%M:%S'
                    )

                # Compare with current UTC time
                if expiry < datetime.utcnow():
                    flash(
                        'Reset code has expired. Please request a new one.',
                        'danger'
                    )

                    return redirect(
                        url_for('auth.forgot_password')
                    )

            # -------------------------
            # Hash new password
            # -------------------------
            password_hash = generate_password_hash(new_password)

            # -------------------------
            # Update password
            # -------------------------
            cursor.execute(
                """
                UPDATE users
                SET password_hash = %s,
                    otp = NULL,
                    otp_expiry = NULL
                WHERE email = %s
                """,
                (password_hash, email)
            )

            conn.commit()

            # -------------------------
            # Close database connection
            # -------------------------
            cursor.close()
            conn.close()

            # -------------------------
            # Clear reset session
            # -------------------------
            session.pop('reset_email', None)

            flash(
                'Your password has been reset successfully. Please log in.',
                'success'
            )

            # Logging should not break password reset
            try:
                log_system_event(
                    'info',
                    f"Password reset successful for: {email}"
                )
            except Exception as log_error:
                print(f"Warning: Could not log password reset: {log_error}")

            return redirect(url_for('auth.login'))

        except Exception as e:

            # Rollback if something went wrong
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass

            print(f"RESET PASSWORD ERROR: {type(e).__name__}: {e}")

            flash(
                'An error occurred while resetting your password. Please try again.',
                'danger'
            )

            return render_template(
                'reset_password.html',
                email=email
            )

        finally:
            # Safely close connection if still open
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass

            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    return render_template(
        'reset_password.html',
        email=email
    )


# ══════════════════════════════════════════════════════════════
# SECURE LOGIN & LOGOUT
# ══════════════════════════════════════════════════════════════

@auth_bp.route('/login', methods=['GET', 'POST'])
@rate_limit(limit=10, period=60)
def login():
    """Log user in and issue JWT cookies."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = 'remember' in request.form

        if not username or not password:
            flash('Please enter both username and password.', 'danger')
            return render_template('login.html')

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, username))
        user_row = cursor.fetchone()
        conn.close()

        if user_row and check_password_hash(user_row['password_hash'], password):
            # Check if blocked
            if user_row['is_blocked']:
                flash('Your account has been suspended. Please contact administrator.', 'danger')
                return render_template('login.html')

            # Check if email is verified
            if not user_row['is_verified']:
                session['verification_email'] = user_row['email']
                flash('Please verify your email address to log in.', 'warning')
                return redirect(url_for('auth.verify_otp'))

            user = User(user_row['id'], user_row['username'], user_row['email'], user_row['role'])
            login_user(user)

            # Generate token lifetime based on remember me
            # remember_me gives access to longer cookie retention
            access_token, refresh_token = generate_tokens(user.id, user.role)

            flash(f'Welcome back, {user.username}!', 'success')
            log_system_event('info', f"User logged in: {user.username}")

            response = None
            if user.role == 'admin':
                response = redirect(url_for('admin.admin_panel'))
            else:
                response = redirect(url_for('dashboard.dashboard'))

            # Set JWT cookies
            max_age_access = 900  # 15 mins
            max_age_refresh = 30 * 24 * 3600 if remember else 7 * 24 * 3600  # 30 days or 7 days
            response.set_cookie('access_token', access_token, httponly=True, samesite='Lax', max_age=max_age_access)
            response.set_cookie('refresh_token', refresh_token, httponly=True, samesite='Lax', max_age=max_age_refresh)
            return response
        else:
            flash('Invalid username or password.', 'danger')
            log_system_event('warning', f"Failed login attempt for: {username}")

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Clean up user tokens and secure logout."""
    refresh = request.cookies.get('refresh_token')
    if refresh:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM refresh_tokens WHERE token = %s", (refresh,))
        conn.commit()
        conn.close()

    logout_user()
    flash('You have been logged out.', 'info')
    log_system_event('info', "User logged out.")

    response = redirect(url_for('auth.login'))
    response.delete_cookie('access_token')
    response.delete_cookie('refresh_token')
    return response


# ══════════════════════════════════════════════════════════════
# SOCIAL LOGIN (SIMULATED / SANDBOX OAUTH FLOW)
# ══════════════════════════════════════════════════════════════

@auth_bp.route('/auth/google')
def google_login():
    """Initiates real Google OAuth if credentials are configured, otherwise shows the sandbox simulator."""
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
        # Sandbox OAuth Mock Screen (no real credentials configured)
        return render_template('mock_oauth.html', provider='Google', callback_url=url_for('auth.google_callback'))

    redirect_uri = url_for('auth.google_callback', _external=True)
    google = OAuth2Session(GOOGLE_CLIENT_ID, redirect_uri=redirect_uri, scope=["openid", "email", "profile"])
    authorization_url, state = google.authorization_url(
        GOOGLE_AUTHORIZATION_URL, access_type="offline", prompt="select_account"
    )
    session['oauth_state'] = state
    return redirect(authorization_url)


@auth_bp.route('/auth/google/callback')
def google_callback():
    """Handles OAuth redirect callback from Google (real or simulated)."""
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
        # Sandbox fallback (no real credentials configured)
        email = "google_student@scn.com"
        username = "GoogleStudent"
        google_id = "google-sandbox-12345"
    else:
        error = request.args.get('error')
        if error:
            flash(f"Google login was cancelled or failed: {error}", "danger")
            return redirect(url_for('auth.login'))

        redirect_uri = url_for('auth.google_callback', _external=True)
        google = OAuth2Session(
            GOOGLE_CLIENT_ID, redirect_uri=redirect_uri, state=session.get('oauth_state')
        )
        try:
            google.fetch_token(
                GOOGLE_TOKEN_URL,
                client_secret=GOOGLE_CLIENT_SECRET,
                authorization_response=request.url,
            )
            userinfo = google.get(GOOGLE_USERINFO_URL).json()
        except Exception as e:
            flash("Google login failed. Please try again.", "danger")
            log_system_event('error', f"Google OAuth error: {str(e)}")
            return redirect(url_for('auth.login'))

        email = userinfo.get('email')
        username = userinfo.get('name') or (email.split('@')[0] if email else 'GoogleUser')
        google_id = userinfo.get('sub')

        if not email or not google_id:
            flash("Could not retrieve your Google account details. Please try again.", "danger")
            return redirect(url_for('auth.login'))

    conn = get_db()
    cursor = conn.cursor()
    
    # Fetch or create Google user
    cursor.execute("SELECT * FROM users WHERE google_id = %s OR email = %s", (google_id, email))
    user_row = cursor.fetchone()

    if not user_row:
        password_hash = generate_password_hash(str(random.random()))
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, role, google_id, is_verified)
            VALUES (%s, %s, %s, %s, %s, 1)
            RETURNING id
            """,
            (username, email, password_hash, 'student', google_id)
        )
        user_id = cursor.fetchone()['id']
        cursor.execute("INSERT INTO student_profiles (user_id, name) VALUES (%s, %s)", (user_id, username))
        conn.commit()
        
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user_row = cursor.fetchone()
    else:
        # Link Google ID if not linked
        if not user_row['google_id']:
            cursor.execute("UPDATE users SET google_id = %s WHERE id = %s", (google_id, user_row['id']))
            conn.commit()

    conn.close()

    if user_row['is_blocked']:
        flash('Account suspended.', 'danger')
        return redirect(url_for('auth.login'))

    user = User(user_row['id'], user_row['username'], user_row['email'], user_row['role'])
    login_user(user)

    access_token, refresh_token = generate_tokens(user.id, user.role)
    flash(f"Successfully logged in via Google!", "success")
    log_system_event('info', f"OAuth login via Google: {user.username}")

    response = redirect(url_for('dashboard.dashboard'))
    response.set_cookie('access_token', access_token, httponly=True, samesite='Lax', max_age=900)
    response.set_cookie('refresh_token', refresh_token, httponly=True, samesite='Lax', max_age=604800)
    return response


@auth_bp.route('/auth/github')
def github_login():
    """Initiates real GitHub OAuth if credentials are configured, otherwise shows the sandbox simulator."""
    if not (GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET):
        # Sandbox OAuth Mock Screen (no real credentials configured)
        return render_template('mock_oauth.html', provider='GitHub', callback_url=url_for('auth.github_callback'))

    redirect_uri = url_for('auth.github_callback', _external=True)
    github = OAuth2Session(GITHUB_CLIENT_ID, redirect_uri=redirect_uri, scope=["read:user", "user:email"])
    authorization_url, state = github.authorization_url(GITHUB_AUTHORIZATION_URL)
    session['oauth_state'] = state
    return redirect(authorization_url)


@auth_bp.route('/auth/github/callback')
def github_callback():
    """Handles OAuth redirect callback from GitHub (real or simulated)."""
    if not (GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET):
        # Sandbox fallback (no real credentials configured)
        email = "github_student@scn.com"
        username = "GitHubStudent"
        github_id = "github-sandbox-67890"
    else:
        error = request.args.get('error')
        if error:
            flash(f"GitHub login was cancelled or failed: {error}", "danger")
            return redirect(url_for('auth.login'))

        redirect_uri = url_for('auth.github_callback', _external=True)
        github = OAuth2Session(
            GITHUB_CLIENT_ID, redirect_uri=redirect_uri, state=session.get('oauth_state')
        )
        try:
            github.fetch_token(
                GITHUB_TOKEN_URL,
                client_secret=GITHUB_CLIENT_SECRET,
                authorization_response=request.url,
            )
            profile = github.get(GITHUB_USER_URL).json()
        except Exception as e:
            flash("GitHub login failed. Please try again.", "danger")
            log_system_event('error', f"GitHub OAuth error: {str(e)}")
            return redirect(url_for('auth.login'))

        username = profile.get('login') or 'GitHubUser'
        github_id = str(profile.get('id')) if profile.get('id') is not None else None

        email = profile.get('email')
        if not email:
            # Primary email is often private; the /user/emails endpoint requires the
            # user:email scope, which was requested above.
            try:
                emails = github.get(GITHUB_EMAILS_URL).json()
                primary = next((e['email'] for e in emails if e.get('primary') and e.get('verified')), None)
                email = primary or next((e['email'] for e in emails if e.get('verified')), None)
            except Exception:
                email = None

        if not email or not github_id:
            flash("Could not retrieve a verified email from your GitHub account. "
                  "Make sure your GitHub account has a verified email address.", "danger")
            return redirect(url_for('auth.login'))

    conn = get_db()
    cursor = conn.cursor()
    
    # Fetch or create GitHub user
    cursor.execute("SELECT * FROM users WHERE github_id = %s OR email = %s", (github_id, email))
    user_row = cursor.fetchone()

    if not user_row:
        password_hash = generate_password_hash(str(random.random()))
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, role, github_id, is_verified)
            VALUES (%s, %s, %s, %s, %s, 1)
            RETURNING id
            """,
            (username, email, password_hash, 'student', github_id)
        )
        user_id = cursor.fetchone()['id']
        cursor.execute("INSERT INTO student_profiles (user_id, name) VALUES (%s, %s)", (user_id, username))
        conn.commit()
        
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user_row = cursor.fetchone()
    else:
        # Link GitHub ID if not linked
        if not user_row['github_id']:
            cursor.execute("UPDATE users SET github_id = %s WHERE id = %s", (github_id, user_row['id']))
            conn.commit()

    conn.close()

    if user_row['is_blocked']:
        flash('Account suspended.', 'danger')
        return redirect(url_for('auth.login'))

    user = User(user_row['id'], user_row['username'], user_row['email'], user_row['role'])
    login_user(user)

    access_token, refresh_token = generate_tokens(user.id, user.role)
    flash(f"Successfully logged in via GitHub!", "success")
    log_system_event('info', f"OAuth login via GitHub: {user.username}")

    response = redirect(url_for('dashboard.dashboard'))
    response.set_cookie('access_token', access_token, httponly=True, samesite='Lax', max_age=900)
    response.set_cookie('refresh_token', refresh_token, httponly=True, samesite='Lax', max_age=604800)
    return response
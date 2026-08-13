"""
Smart Career Navigator - Main Application Entry Point
======================================================
This is the main Flask application file that initializes the app,
registers blueprints (routes), and starts the development server.
"""

import os
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for
from flask_login import LoginManager
from flask import g

# ── Import database utilities ──
from utils.db import init_db, load_csv_data, get_db

# ── Import route blueprints ──
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.resume import resume_bp
from routes.admin import admin_bp


def create_app():
    """
    Application factory function.
    Creates and configures the Flask application.
    """
    # Load environment variables from .env (absolute path so it's found
    # regardless of which directory the app is launched from)
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    load_dotenv(dotenv_path=env_path, override=True)

    app = Flask(__name__)

    # ── Configuration ──
    app.config['SECRET_KEY'] = 'smart-career-navigator-secret-key-2024'
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Max upload size: 16 MB

    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # ── Initialize Database ──
    # Creates all tables if they don't exist
    init_db()
    # Load sample data from CSV files into the database
    #load_csv_data()

    # ── Setup Flask-Login with JWT Request Loader ──
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'           # Redirect here if not logged in
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    from utils.jwt_auth import load_user_from_jwt
    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        """
        Flask-Login user_loader: reloads user from session user_id.

        This is required when Flask-Login persists the user ID in the session
        (session['_user_id']). Without this callback, session-based auth silently
        fails and the user is treated as anonymous after page reload.
        """
        return User.get_by_id(user_id)

    @login_manager.request_loader
    def load_user_from_request(request):
        """
        Loads a user using JWT access or refresh token cookies.
        """
        return load_user_from_jwt(request)

    @app.after_request
    def set_auth_cookies(response):
        """
        Flask after_request handler to set new rotated tokens
        if they were generated during this request cycle.
        """
        if hasattr(g, 'new_access_token') and g.new_access_token:
            response.set_cookie('access_token', g.new_access_token, httponly=True, samesite='Lax', max_age=900)
        if hasattr(g, 'new_refresh_token') and g.new_refresh_token:
            response.set_cookie('refresh_token', g.new_refresh_token, httponly=True, samesite='Lax', max_age=604800)
        return response

    @app.context_processor
    def inject_notifications():
        """
        Global context processor to inject active notifications into templates.
        """
        from flask_login import current_user
        if current_user.is_authenticated:
            try:
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM notifications WHERE user_id = %s AND is_read = 0 ORDER BY created_at DESC LIMIT 5",
                    (current_user.id,)
                )
                rows = cursor.fetchall()
                conn.close()
                return {'unread_notifications': rows}
            except Exception:
                return {'unread_notifications': []}
        return {'unread_notifications': []}

    # ── Register Blueprints ──
    # Each blueprint handles a group of related routes
    app.register_blueprint(auth_bp)           # /login, /register, /logout
    app.register_blueprint(dashboard_bp)      # /dashboard, /profile, /recommendations
    app.register_blueprint(resume_bp)         # /resume/upload, /resume/analyze
    app.register_blueprint(admin_bp)          # /admin, /admin/roles, /admin/courses

    # ── Home Route ──
    @app.route('/')
    def home():
        """Landing page - redirects to the index template."""
        return render_template('index.html')

    return app


# ── Run the Application ──
if __name__ == '__main__':
    app = create_app()
    print("\n✅ Smart Career Navigator is running!")
    print("📍 Open: http://127.0.0.1:5000")
    print("👤 Admin Login: admin / admin123\n")
    app.run(debug=True, port=5000)
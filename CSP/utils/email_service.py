"""
Email Service
=============
Handles sending OTP codes for email verification and password resets.
If SMTP settings are not configured in .env, it runs in Developer Sandbox Mode,
printing the OTP in a structured console box.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# SMTP Configurations from .env
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
SMTP_SENDER = os.environ.get("SMTP_SENDER", SMTP_USERNAME).strip()


def send_otp_email(to_email, otp, username=None):
    """
    Send a 6-digit verification OTP.
    Falls back to console print if SMTP is not configured.
    """
    subject = "Verify Your Account - Smart Career Navigator"
    body = f"""
    Hi {username or 'User'},

    Welcome to Smart Career Navigator! 

    Your 6-digit verification code is: {otp}

    This code is valid for 10 minutes. Please enter it on the verification page to activate your account.

    If you did not request this code, you can safely ignore this email.

    Best regards,
    The Smart Career Navigator Team
    """
    return _send_email(to_email, subject, body, otp, "Email Verification")


def send_password_reset_email(to_email, otp, username=None):
    """
    Send a 6-digit password reset OTP.
    Falls back to console print if SMTP is not configured.
    """
    subject = "Reset Your Password - Smart Career Navigator"
    body = f"""
    Hi {username or 'User'},

    We received a request to reset your password for your Smart Career Navigator account.

    Your 6-digit password reset code is: {otp}

    This code is valid for 10 minutes. Please enter this code on the password reset page.

    If you did not request a password reset, please secure your account immediately.

    Best regards,
    The Smart Career Navigator Team
    """
    return _send_email(to_email, subject, body, otp, "Password Reset")


def _send_email(to_email, subject, body, otp, email_type):
    """
    Internal helper to send an email using SMTP.
    If credentials are missing, logs a structured sandbox block to terminal console.
    """
    # Check if SMTP configuration is complete
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        # Developer Sandbox Mode
        print("\n" + "═"*50)
        print(" 🔍 DEVELOPER SANDBOX EMAIL")
        print(f"  To:      {to_email}")
        print(f"  Type:    {email_type}")
        print(f"  Subject: {subject}")
        print(f"  OTP:     {otp}")
        print("═"*50 + "\n")
        return True, "sandbox"

    try:
        # Construct message
        msg = MIMEMultipart()
        msg['From'] = SMTP_SENDER
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Connect to SMTP Server
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_SENDER, to_email, msg.as_string())
        server.quit()
        
        return True, "sent"
    except Exception as e:
        # Fallback warning if email fails to send
        print(f"❌ Failed to send SMTP email: {e}")
        print("\n" + "═"*50)
        print(" 🔍 DEVELOPER SANDBOX FALLBACK")
        print(f"  To:      {to_email}")
        print(f"  Type:    {email_type}")
        print(f"  OTP:     {otp}")
        print("═"*50 + "\n")
        return False, str(e)

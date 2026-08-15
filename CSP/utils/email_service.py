"""
Email Service
=============
Handles sending OTP codes for email verification
and password resets using the Brevo API.
"""

import os
import requests


# ============================================================
# BREVO CONFIGURATION
# ============================================================

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "").strip()

BREVO_SENDER = os.environ.get(
    "BREVO_SENDER",
    "kethanreddy706@gmail.com"
).strip()

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


print("BREVO API KEY FOUND:", bool(BREVO_API_KEY))
print("BREVO SENDER:", BREVO_SENDER)


# ============================================================
# EMAIL VERIFICATION OTP
# ============================================================

def send_otp_email(to_email, otp, username=None):
    """
    Send a 6-digit verification OTP using Brevo.

    Returns:
        (True, "sent")  -> email sent successfully
        (True, "sandbox") -> API key is not configured
        (False, error) -> email sending failed
    """

    subject = "Verify Your Account - Smart Career Navigator"

    body = f"""
    <html>
    <body>
        <p>Hi {username or 'User'},</p>

        <p>Welcome to Smart Career Navigator!</p>

        <p>
            Your 6-digit verification code is:
            <strong>{otp}</strong>
        </p>

        <p>
            This code is valid for 10 minutes.
            Please enter it on the verification page to activate your account.
        </p>

        <p>
            If you did not request this code, you can safely ignore this email.
        </p>

        <p>
            Best regards,<br>
            The Smart Career Navigator Team
        </p>
    </body>
    </html>
    """

    return _send_email(
        to_email,
        subject,
        body,
        otp,
        "Email Verification"
    )


# ============================================================
# PASSWORD RESET OTP
# ============================================================

def send_password_reset_email(to_email, otp, username=None):
    """
    Send a 6-digit password reset OTP using Brevo.

    Returns:
        (True, "sent")  -> email sent successfully
        (True, "sandbox") -> API key is not configured
        (False, error) -> email sending failed
    """

    subject = "Reset Your Password - Smart Career Navigator"

    body = f"""
    <html>
    <body>
        <p>Hi {username or 'User'},</p>

        <p>
            We received a request to reset your password
            for your Smart Career Navigator account.
        </p>

        <p>
            Your 6-digit password reset code is:
            <strong>{otp}</strong>
        </p>

        <p>
            This code is valid for 10 minutes.
            Please enter this code on the password reset page.
        </p>

        <p>
            If you did not request a password reset,
            you can safely ignore this email.
        </p>

        <p>
            Best regards,<br>
            The Smart Career Navigator Team
        </p>
    </body>
    </html>
    """

    return _send_email(
        to_email,
        subject,
        body,
        otp,
        "Password Reset"
    )


# ============================================================
# INTERNAL BREVO EMAIL SENDER
# ============================================================

def _send_email(to_email, subject, body, otp, email_type):
    """
    Internal helper used to send emails through Brevo.

    Brevo uses an HTTPS API, so this does not use Gmail SMTP.
    """

    # --------------------------------------------------------
    # Check Brevo API key
    # --------------------------------------------------------

    if not BREVO_API_KEY:

        print("\n" + "=" * 50)
        print("DEVELOPER SANDBOX EMAIL")
        print(f"To:      {to_email}")
        print(f"Type:    {email_type}")
        print(f"Subject: {subject}")
        print(f"OTP:     {otp}")
        print("=" * 50 + "\n")

        return True, "sandbox"


    # --------------------------------------------------------
    # Prepare Brevo API request
    # --------------------------------------------------------

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    payload = {
        "sender": {
            "name": "Smart Career Navigator",
            "email": BREVO_SENDER
        },
        "to": [
            {
                "email": to_email,
                "name": "User"
            }
        ],
        "subject": subject,
        "htmlContent": body
    }


    # --------------------------------------------------------
    # Send email through Brevo
    # --------------------------------------------------------

    try:

        response = requests.post(
            BREVO_API_URL,
            headers=headers,
            json=payload,
            timeout=15
        )

        # Raise an exception for HTTP errors
        response.raise_for_status()

        response_data = response.json()

        print(
            f"SUCCESS: {email_type} email sent to {to_email}"
        )

        print(
            f"Brevo response: {response_data}"
        )

        return True, "sent"


    # --------------------------------------------------------
    # Handle Brevo errors
    # --------------------------------------------------------

    except requests.exceptions.RequestException as e:

        print(
            f"ERROR: Failed to send {email_type} email"
        )

        print(
            f"Brevo error: {e}"
        )

        if hasattr(e, "response") and e.response is not None:
            print(
                f"Brevo response body: {e.response.text}"
            )

        return False, str(e)

    except Exception as e:

        print(
            f"ERROR: Unexpected email error: {e}"
        )

        return False, str(e)
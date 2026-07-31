import logging
from typing import TypedDict
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from rest_framework_simplejwt.tokens import RefreshToken
from apps.accounts.utils import (
    generate_magic_token, store_magic_token,
    get_magic_token_email, delete_magic_token, audit_log,
)
from apps.accounts.email import send_welcome_email,send_magic_link_email


User = get_user_model()
logger = logging.getLogger(__name__)


class SignupResult(TypedDict):
    magic_link: str | None
    message: str


class LoginResult(TypedDict):
    magic_link: str | None
    message: str


class VerifyResult(TypedDict):
    access: str
    refresh: str
    user: dict


def _build_magic_link(token: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/auth/callback?token={token}"

def _issue_jwt(user) -> tuple[str, str]:
    refresh = RefreshToken.for_user(user)
    refresh["email"] = user.email
    refresh["full_name"] = user.full_name
    return str(refresh.access_token), str(refresh)


def _user_to_dict(user) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "country": user.country,
        "is_verified": user.is_verified,
        "created_at": user.created_at.isoformat(),
    }
import traceback

def signup_service(email: str, full_name: str, country: str, password: str, ip: str) -> SignupResult:
    print("=== signup_service started ===")

    email = email.lower().strip()

    if User.objects.filter(email=email).exists():
        print("User already exists")
        audit_log("signup_duplicate", email, ip)
        raise ValueError("An account with this email already exists. Please log in instead.")

    print("Creating user...")
    user = User.objects.create_user(
        email=email,
        full_name=full_name,
        country=country,
        password=password,
    )
    print(f"User created: {user.email}")

    logger.info("New user created: %s", email)

    try:
     print("Calling send_welcome_email()...")
     dashboard_url = f"{settings.FRONTEND_URL.rstrip('/')}/dashboard"
     send_welcome_email(user, dashboard_url)
     print("✅ Welcome email sent successfully")
    except Exception:
     print("❌ Error sending welcome email:")
    traceback.print_exc()

    print("Generating magic token...")
    token = generate_magic_token()

    print("Storing magic token...")
    if not store_magic_token(token, email):
        print("❌ Failed to store magic token")
        raise RuntimeError(
            "Account created but could not generate a verification link. Please try logging in."
        )

    print("Signup completed successfully")

    audit_log("signup_success", email, ip)

    return SignupResult(
        message="Account created. Check your email to verify your account.",
        magic_link=_build_magic_link(token) if settings.DEBUG else None,
    )


from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()

def login_service(email: str, ip: str) -> LoginResult:
    print("=== login_service started ===")

    email = email.lower().strip()
    neutral = "If an account exists, a magic link has been sent."

    try:
        user = User.objects.get(email=email)
        print(f"Found user: {user.email}")
    except User.DoesNotExist:
        print("❌ User does not exist")
        audit_log("login_no_user", email, ip)
        return LoginResult(message=neutral, magic_link=None)

    if not user.is_active:
        print("❌ User is inactive")
        audit_log("login_inactive", email, ip)
        return LoginResult(message=neutral, magic_link=None)

    print("Generating magic token...")
    token = generate_magic_token()

    print("Storing magic token...")
    store_magic_token(token, email)

    magic_link = _build_magic_link(token)

    try:
        print("Calling send_magic_link_email()...")
        send_magic_link_email(
            user=user,
            magic_link=magic_link,
        )
        print("✅ Magic link email sent successfully")
    except Exception:
        print("❌ Error sending magic link email:")
        traceback.print_exc()

    audit_log("login_link_sent", email, ip)

    print("Login service completed")

    return LoginResult(
        message=neutral,
        magic_link=None,
    )


def verify_service(token: str, ip: str) -> VerifyResult:
    if not token or len(token) > 200:
        raise ValueError("Invalid token.")

    email = get_magic_token_email(token)

    if not email:
        audit_log("verify_invalid_token", "unknown", ip)
        raise ValueError("This link is invalid or has expired.")

    try:
        user = User.objects.get(email=email, is_active=True)
    except User.DoesNotExist:
        audit_log("verify_user_missing", email, ip)
        raise ValueError("Account not found or deactivated.")

    # NOW delete token (important: AFTER success check)
    delete_magic_token(token)

    if not user.is_verified:
        user.is_verified = True
        user.save(update_fields=["is_verified", "updated_at"])

    access, refresh = _issue_jwt(user)

    audit_log("verify_success", email, ip)

    return VerifyResult(
        access=access,
        refresh=refresh,
        user=_user_to_dict(user),
    )

def logout_service(refresh_token: str, ip: str, email: str) -> None:
    try:
        RefreshToken(refresh_token).blacklist()
        audit_log("logout", email, ip)
    except Exception as e:
        logger.warning("Logout blacklist error for %s: %s", email, e)

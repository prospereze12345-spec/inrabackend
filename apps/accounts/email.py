from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.templatetags.static import static


def _logo_url() -> str:
    return f"{settings.SITE_URL.rstrip('/')}{static('images/logo.png')}"


def send_welcome_email(user, dashboard_url: str | None = None) -> None:
    if dashboard_url is None:
        dashboard_url = f"{settings.FRONTEND_URL.rstrip('/')}/dashboard"

    html = render_to_string(
        "emails/welcome_email.html",
        {
            "user": user,
            "logo_url": _logo_url(),
            "dashboard_url": dashboard_url,
        },
    )

    msg = EmailMultiAlternatives(
        subject="Welcome to INRA Studio 🚀",
        body=f"Welcome to INRA Studio. Go to your dashboard: {dashboard_url}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    msg.attach_alternative(html, "text/html")
    msg.send()


def send_magic_link_email(user, magic_link: str) -> None:
    html = render_to_string(
        "emails/magic_link_email.html",
        {
            "user": user,
            "magic_link": magic_link,
            "logo_url": _logo_url(),
        },
    )

    msg = EmailMultiAlternatives(
        subject="Sign in to INRA Studio",
        body=f"Click here to login: {magic_link}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    msg.attach_alternative(html, "text/html")
    msg.send()
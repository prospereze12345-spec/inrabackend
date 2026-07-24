from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.templatetags.static import static


def send_welcome_email(request,user,dashboard_url):
    logo_url = request.build_absolute_uri(static('images/logo.png'))
    html = render_to_string(
        "emails/welcome_email.html",
        {
            "user": user,
            'logo_url': logo_url, 
            'dashboard_url': dashboard_url,
       }
    )

    msg = EmailMultiAlternatives(
        subject="Welcome to INRA Studio 🚀",
        body="Welcome to INRA Studio.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )

    msg.attach_alternative(html, "text/html")
    msg.send()


def send_magic_link_email(user, magic_link):
    logo_url = f"{settings.SITE_URL}{static('images/logo.png')}"

    html = render_to_string(
        "emails/magic_link_email.html",
        {
            "user": user,
            "magic_link": magic_link,
            "logo_url": logo_url,
        },
    )

    msg = EmailMultiAlternatives(
        subject="Sign in to INRA Studio ",
        body=f"Click here to login: {magic_link}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )

    msg.attach_alternative(html, "text/html")
    msg.send()
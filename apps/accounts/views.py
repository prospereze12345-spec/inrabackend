import logging
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from apps.accounts.serializers import (
    SignupSerializer, LoginSerializer,
    VerifyTokenSerializer, LogoutSerializer, UserProfileSerializer,
)
from apps.accounts.services import signup_service, login_service, verify_service, logout_service
from apps.accounts.throttles import (
    SignupEmailThrottle, SignupIPThrottle,
    LoginEmailThrottle, LoginIPThrottle, VerifyIPThrottle,
)
from apps.accounts.permissions import IsVerifiedUser
from apps.accounts.utils import get_client_ip

logger = logging.getLogger(__name__)
class SignupView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SignupEmailThrottle, SignupIPThrottle]

    def post(self, request):
        s = SignupSerializer(data=request.data)

        if not s.is_valid():
            logger.warning(f"Signup validation failed: {s.errors} | payload keys: {list(request.data.keys())}")
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

        data = s.validated_data

        try:
            result = signup_service(
                email=data["email"],
                full_name=data["full_name"],
                country=data["country"],
                password=data["password"],
                ip=get_client_ip(request),
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        except RuntimeError as e:
            return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(result, status=status.HTTP_201_CREATED)
    

    
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []          # <-- add this
    throttle_classes = [LoginEmailThrottle, LoginIPThrottle]

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            result = login_service(email=s.validated_data["email"], ip=get_client_ip(request))
        except RuntimeError as e:
            return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(result, status=status.HTTP_200_OK)


class VerifyMagicLinkView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []          # <-- add this too

    def post(self, request):
        token = request.data.get("token")  # also check this — see below
        if not token:
            return Response({"detail": "Missing token"}, status=status.HTTP_400_BAD_REQUEST)

        result = verify_service(token=token, ip=get_client_ip(request))

        return Response({
            "access": result["access"],
            "refresh": result["refresh"],
            "user": result["user"],
        })
class VerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes   = [VerifyIPThrottle]

    def post(self, request):
        s = VerifyTokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            result = verify_service(token=s.validated_data["token"], ip=get_client_ip(request))
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = LogoutSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        logout_service(
            refresh_token=s.validated_data["refresh"],
            ip=get_client_ip(request),
            email=request.user.email,
        )
        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [IsVerifiedUser]

    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)
from django.core.mail import EmailMessage
from django.conf import settings

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status


@api_view(["POST"])
@permission_classes([AllowAny])
def contact_message(request):
    name = str(request.data.get("name", "")).strip()
    email = str(request.data.get("email", "")).strip()
    subject = str(request.data.get("subject", "")).strip()
    message = str(request.data.get("message", "")).strip()

    # ---------------------------------------------------------
    # VALIDATION
    # ---------------------------------------------------------

    if not name or not email or not message:
        return Response(
            {
                "success": False,
                "message": "Name, email and message are required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if "@" not in email or "." not in email.split("@")[-1]:
        return Response(
            {
                "success": False,
                "message": "Please provide a valid email address.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not subject:
        subject = f"New INRASTUDIO contact message from {name}"

    # ---------------------------------------------------------
    # EMAIL CONTENT
    # ---------------------------------------------------------

    email_body = f"""You have received a new message from the INRASTUDIO contact form.

Name: {name}
Email: {email}
Subject: {subject}

Message:
{message}

--------------------------------
Sent from the INRASTUDIO contact page.
"""

    try:
        email_message = EmailMessage(
            subject=subject,
            body=email_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[
                "prospereze12345@gmail.com",
            ],
            reply_to=[
                email,
            ],
        )

        email_message.send(fail_silently=False)

        return Response(
            {
                "success": True,
                "message": "Your message has been sent successfully.",
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        print("CONTACT EMAIL ERROR:", str(e))

        return Response(
            {
                "success": False,
                "message": "Unable to send your message right now. Please try again later.",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from apps.accounts.views import SignupView, LoginView, VerifyView, LogoutView, MeView,contact_message

app_name = "accounts"


urlpatterns = [
    path("contact/", contact_message, name="contact-message"),
    path("signup/",        SignupView.as_view(),       name="signup"),
    path("login/",         LoginView.as_view(),        name="login"),
    path("verify/",        VerifyView.as_view(),        name="verify"),
    path("logout/",        LogoutView.as_view(),        name="logout"),
    path("me/",            MeView.as_view(),            name="me"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),

]

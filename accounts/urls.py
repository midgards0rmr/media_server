from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.views import (
    AccountHomeView,
    MeAPIView,
    RegisterAPIView,
    RegisterView,
    UserLoginView,
    UserLogoutView,
)

app_name = "accounts"

urlpatterns = [
    path("login/", UserLoginView.as_view(), name="login"),
    path("logout/", UserLogoutView.as_view(), name="logout"),
    path("register/", RegisterView.as_view(), name="register"),
    path("", AccountHomeView.as_view(), name="home"),
    path("api/register/", RegisterAPIView.as_view(), name="api_register"),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/me/", MeAPIView.as_view(), name="api_me"),
]

from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.forms import UserLoginForm, UserRegisterForm
from accounts.serializers import UserRegisterSerializer, UserSerializer


class RegisterView(CreateView):
    form_class = UserRegisterForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("media_library:mediafile_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


class UserLoginView(LoginView):
    authentication_form = UserLoginForm
    template_name = "accounts/login.html"


class UserLogoutView(LogoutView):
    next_page = reverse_lazy("media_library:mediafile_list")


class AccountHomeView(TemplateView):
    template_name = "accounts/account_home.html"


class RegisterAPIView(generics.CreateAPIView):
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

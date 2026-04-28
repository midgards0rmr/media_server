from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User


class UserRegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "password1", "password2")


class UserLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Логин",
        widget=forms.TextInput(attrs={"autofocus": True}),
    )

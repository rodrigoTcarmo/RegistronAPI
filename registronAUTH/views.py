from django.shortcuts import render
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy

from registronAUTH.forms import PasswordChgForm


# Use django's built-in password change class
class PasswordChange(PasswordChangeView):
    form_class = PasswordChgForm
    success_url = reverse_lazy('password_success')


def password_success(request):
    return render(request, 'users/login.html')

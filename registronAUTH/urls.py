from django.urls import path
from registronAUTH.views import PasswordChange
from . import views
from django.urls import reverse_lazy

urlpatterns = [
    path('password_change/', PasswordChange.as_view(template_name='users/user_update_pwd.html',
                                                        success_url=reverse_lazy('password_success')),
         name='password_change'),

    path('login/', views.password_success, name='password_success')
]

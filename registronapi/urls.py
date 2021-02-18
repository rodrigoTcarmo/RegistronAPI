from django.urls import path
from . import views

urlpatterns = [
    path('main/', views.main, name='main'),
    path('', views.do_login, name='main_page'),
    path('register/', views.register, name='register'),
    path('users/', views.users, name='users'),
    path('login/', views.do_login, name='login'),
    path('logout/', views.do_logout, name='logout'),
    path('user_detail/<user_id>', views.user_detail, name='user_detail'),
    path('user_update/<user_id>', views.user_update, name='user_update'),
    path('user_delete/<user_id>', views.user_delete, name='user_delete'),
    path('forbidden/', views.forbidden, name='forbidden'),
]

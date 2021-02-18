from django.urls import path
from . import views

urlpatterns = [
    path('departments/', views.departments, name='departments'),
    path('create_department/', views.register_depart, name='create_department'),
    path('department_delete/<depart_id>', views.department_delete, name='department_delete'),
]

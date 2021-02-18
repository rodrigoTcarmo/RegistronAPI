from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('registronapi.urls')),
    path('', include('registronAUTH.urls')),
    path('', include('registrondeparts.urls')),
]

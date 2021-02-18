from django.contrib import admin
from registrondeparts.models import Department


class Departments(admin.ModelAdmin):
    list_display = ('id', 'department_name')
    list_display_links = ('id', 'department_name')
    search_fields = ('department_name',)


admin.site.register(Department, Departments)

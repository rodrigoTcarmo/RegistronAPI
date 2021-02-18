# Copyright 2012 Canonical Ltd.
from django.contrib import admin
from django_group_access.models import AccessGroup


class GroupAdmin(admin.ModelAdmin):
    filter_horizontal = ('members',)
    def get_form(self, *args, **kwargs):
        """ Fixes ordering of the members in the form. """
        form = super(GroupAdmin, self).get_form(*args, **kwargs)
        form.base_fields['members'].queryset = form.base_fields['members'].queryset.order_by('username')
        return form

admin.site.register(AccessGroup, GroupAdmin)

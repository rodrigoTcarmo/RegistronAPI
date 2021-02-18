# Copyright 2012 Canonical Ltd.
from django.conf import settings
from django.core.management import call_command
from django.db.models import loading


class SyncingDb(object):

    def syncdb(self):
        self._original_installed_apps = list(settings.INSTALLED_APPS)
        print self.apps
        for app in self.apps:
            settings.INSTALLED_APPS.append(app)
        loading.cache.loaded = False
        call_command('syncdb', interactive=False, migrate=False)

    def restore(self):
        settings.INSTALLED_APPS = self._original_installed_apps
        loading.cache.loaded = False

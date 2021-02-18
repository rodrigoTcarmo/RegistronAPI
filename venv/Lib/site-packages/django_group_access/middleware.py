# Copyright 2012 Canonical Ltd.
try:
    from threading import local
except ImportError:
    from django.utils._threading_local import local

_storage = local()


def get_access_control_user():
    """
    Return the user used for automatic filtering.
    """
    return getattr(_storage, 'access_control_user', None)


def set_access_control_user(user):
    """
    Set the user for subsequent automatic filtering.
    """
    _storage.access_control_user = user


class DjangoGroupAccessMiddleware(object):
    """
    Stores and clears the currently logged in user in
    thread local storage.
    """
    def process_request(self, request):
        set_access_control_user(getattr(request, 'user', None))
        return None

    def process_response(self, request, response):
        set_access_control_user(None)
        return response

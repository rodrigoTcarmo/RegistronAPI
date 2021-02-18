# Copyright 2012 Canonical Ltd.
import types

from django.db.models import manager
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.db.models.fields import FieldDoesNotExist

_registered_models = set([])
_auto_filter_models = set([])
_unrestricted_access_hooks = {}
_initial_querysets = {}
initial_querysets_active = True


def _is_superuser(user):
    return user.is_superuser


def _get_registered_model_for_model(model):
    if model in _registered_models:
        return model
    if model._meta.proxy and model._meta.proxy_for_model in _registered_models:
        return getattr(
            model._meta, 'concrete_model',
            getattr(model._meta, 'proxy_for_model'))


def get_unrestricted_access_hooks(model):
    return _unrestricted_access_hooks[_get_registered_model_for_model(model)]


def get_initial_queryset(model):
    if initial_querysets_active:
        registered_model = _get_registered_model_for_model(model)
        if registered_model is not None:
            return _initial_querysets[registered_model]
    return None


def is_registered_model(model):
    return _get_registered_model_for_model(model) in _registered_models


def is_auto_filtered(model):
    return _get_registered_model_for_model(model) in _auto_filter_models


def register_proxy(proxy_model):
    try:
        owner = proxy_model._meta.proxy_for_model._meta.get_field('owner')
        if owner:
            owner.contribute_to_class(proxy_model, 'owner')
    except FieldDoesNotExist:
        pass


def wrap_with_initial_queryset(func, initial_queryset):
    def get_query_set_wrapper(self, *args, **kwargs):
        queryset = func(*args, **kwargs)

        if initial_querysets_active:
            queryset = queryset & initial_queryset

        return queryset
    return get_query_set_wrapper


def register(
        model, control_relation=False, unrestricted_manager=False,
        auto_filter=True, owner=True, unrestricted_access_hooks=[],
        queryset=None):
    """
    Register a model with the access control code.
    """
    from django_group_access.models import (
        get_group_model, process_auto_share_groups,
        DjangoGroupAccessForeignKey, DjangoGroupAccessManyToManyField)

    if is_registered_model(model):
        return
    _registered_models.add(model)

    _unrestricted_access_hooks[model] = [_is_superuser] + unrestricted_access_hooks
    model._access_initial_queryset = queryset

    if auto_filter:
        _auto_filter_models.add(model)

    reverse = '%s_owner' % str(model).split("'")[1].split('.')[-1].lower()

    if owner:
        DjangoGroupAccessForeignKey(
            User, null=True, blank=True,
            related_name=reverse).contribute_to_class(
                model, 'owner')

    if unrestricted_manager:
        un_manager = manager.Manager()
        un_manager.contribute_to_class(model, unrestricted_manager)
        un_manager._access_control_meta = {'user': None, 'unrestricted': True}

    if queryset is not None:
        # used with related managers
        setattr(model, '_dga_initial_queryset', queryset)
        # decorate the manager's get_query_set method so it's filtered
        # with the initial queryset
        if hasattr(model.objects, 'get_queryset'):
            # django 1.6
            model.objects.get_queryset = types.MethodType(
                wrap_with_initial_queryset(
                    model.objects.get_queryset, queryset),
                model.objects)
        else:
            model.objects.get_query_set = types.MethodType(
                wrap_with_initial_queryset(
                    model.objects.get_query_set, queryset),
                model.objects)

    if control_relation:
        model.access_control_relation = control_relation
        # access groups are inferred from which access groups
        # have access to the related records, so no need to
        # add the attribute to the class.
        return
    DjangoGroupAccessManyToManyField(
        get_group_model(), blank=True, null=True).contribute_to_class(
            model, 'access_groups')
    post_save.connect(process_auto_share_groups, model)

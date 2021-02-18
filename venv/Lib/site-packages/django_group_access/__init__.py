# Copyright 2012 Canonical Ltd.
__all__ = ['register', 'register_proxy']

import traceback
import types

from django.db.models import query, manager
from django.db.models.fields import related
from django.db.models.sql import where

from django_group_access import registration
from django_group_access.models import AccessManagerMixin, QuerySetMixin

register = registration.register
register_proxy = registration.register_proxy

"""
Django creates managers in a whole bunch of places, sometimes
defining the class dynamically inside a closure, which makes
decorating every manager creation a tricky job. So we add a mixin
to the base Manager class so that we're guaranteed to have the
access control code available no matter which Manager we're using.
"""
# add access control methods to the base Manager class
if AccessManagerMixin not in manager.Manager.__bases__:
    manager.Manager.__bases__ += (AccessManagerMixin, )
# add access control methods to the base QuerySet class
if QuerySetMixin not in query.QuerySet.__bases__:
    query.QuerySet.__bases__ += (QuerySetMixin, )


def wrap_db_method(func, used_in_unique_check=False):
    """
    When the queryset is going to go to the database, apply
    the access control filters unless we're currently doing
    uniqueness checks.
    """
    def db_wrapper(self, *args, **kwargs):
        apply_access_control = True
        if used_in_unique_check:
            # if we're performing unique checks, we must not
            # filter for access control.
            apply_access_control = not bool(
                [t for t in traceback.extract_stack()
                if t[2] == '_perform_unique_checks'])

        # django 1.6 has a class that handles subqueries which we
        # need to deal with slightly differently
        is_subquery = hasattr(self, 'query_object')

        # if this queryset has already been filtered for access
        # control, let's not do it again.
        if apply_access_control:
            if is_subquery:
                if getattr(self.query_object, '_access_has_been_filtered', False):
                    apply_access_control = False
            elif getattr(self, '_access_has_been_filtered', False):
                apply_access_control = False

        if apply_access_control:
            if is_subquery:
                queryset = self.query_object._filter_for_access_control()
                self.query_object = queryset
            else:
                queryset = self._filter_for_access_control()
            queryset._access_has_been_filtered = True
        else:
            if is_subquery:
                queryset = self.query_object
            else:
                queryset = self
        if is_subquery:
            return func(self, *args, **kwargs)
        else:
            return func(queryset, *args, **kwargs)
    return db_wrapper

query.QuerySet.get = wrap_db_method(query.QuerySet.get)
query.QuerySet.latest = wrap_db_method(query.QuerySet.latest)
query.QuerySet.aggregate = wrap_db_method(query.QuerySet.aggregate)
query.QuerySet.iterator = wrap_db_method(query.QuerySet.iterator)
query.QuerySet.count = wrap_db_method(query.QuerySet.count)
query.QuerySet.in_bulk = wrap_db_method(query.QuerySet.in_bulk)
query.QuerySet.__getitem__ = wrap_db_method(query.QuerySet.__getitem__)
query.QuerySet._as_sql = wrap_db_method(query.QuerySet._as_sql)

# django 1.6 subquery class
if hasattr(where, 'SubqueryConstraint'):
    where.SubqueryConstraint.as_sql = wrap_db_method(where.SubqueryConstraint.as_sql)

# exists is used to do uniqueness checks when validating models.
query.QuerySet.exists = wrap_db_method(
    query.QuerySet.exists, used_in_unique_check=True)


def wrap_get_query_set(func):
    """
    Propagate metadata from model instances in the manager
    to the queryset and apply access controls where needed.
    """
    def get_query_set_wrapper(self, *args, **kwargs):
        queryset = func(self, *args, **kwargs)

        metadata = False
        if hasattr(self, 'instance'):
            # some related managers have the original instance, we can get
            # the metadata from the instance.
            metadata = getattr(self.instance, '_access_control_meta', False)
        else:
            # some are loaded with the metadata directly.
            metadata = getattr(self, '_access_control_meta', False)

        if metadata:
            queryset._access_control_meta = metadata
            queryset._access_control_filtered = True
        return queryset
    return get_query_set_wrapper


if hasattr(manager.Manager, 'get_queryset'):
    # django 1.6
    manager.Manager.get_queryset = wrap_get_query_set(
        manager.Manager.get_queryset)
else:
    # previous versions
    manager.Manager.get_query_set = wrap_get_query_set(
        manager.Manager.get_query_set)


def wrap_query_set_iterator(func):
    """
    Sits between the iterator and the loop, propagating the access
    control meta data.
    """
    def iterator_wrapper(self, *args, **kwargs):
        for obj in func(self, *args, **kwargs):
            if hasattr(self, '_access_control_meta'):
                obj._access_control_meta = self._access_control_meta
            yield obj
    return iterator_wrapper

query.QuerySet.iterator = wrap_query_set_iterator(query.QuerySet.iterator)


def wrap_query_set_clone(func):
    """
    If the access control meta data exists, make sure it
    gets cloned too.
    """
    def clone_queryset(self, *args, **kwargs):
        clone = func(self, *args, **kwargs)
        if hasattr(self, '_access_control_meta'):
            clone._access_control_meta = self._access_control_meta

        # if this queryset has been run through accessible_by_user, its clone
        # will have that filter too, so copy the flag over.
        if hasattr(self, '_access_control_filtering'):
            clone._access_control_filtering = self._access_control_filtering
        return clone
    return clone_queryset

query.QuerySet._clone = wrap_query_set_clone(query.QuerySet._clone)


def wrap_getitem(func):
    """
    Propagating access control metadata from querysets to models when
    a model is accessed as if the queryset were a list.
    """
    def getitem_wrapper(self, k):
        item = func(self, k)
        if hasattr(self, '_access_control_meta'):
            if isinstance(item, list):
                for obj in item:
                    obj._access_control_meta = self._access_control_meta
            else:
                item._access_control_meta = self._access_control_meta
        return item
    return getitem_wrapper

query.QuerySet.__getitem__ = wrap_getitem(query.QuerySet.__getitem__)


def wrap_related_manager_get_query_set(func):
    """
    Extra decorator for related manager's get_query_set which
    enforces intial querysets.
    """
    def get_query_set_wrapper(self, *args, **kwargs):
        queryset = func(*args, **kwargs)
        if hasattr(self.model, '_dga_initial_queryset'):
            if registration.initial_querysets_active:
                queryset = queryset & self.model._dga_initial_queryset
        return queryset
    return get_query_set_wrapper


def wrap_descriptor_get(func, do_wrap_get_query_set=False):
    """
    Getting a model or a manager from a related field descriptor
    will have the access control metadata propagated to it
    from the instance it is on.
    """
    def get_wrapper(self, instance, instance_type=None):
        obj = func(self, instance, instance_type)
        if obj is None:
            return obj
        if hasattr(instance, '_access_control_meta'):
            obj._access_control_meta = instance._access_control_meta

        if do_wrap_get_query_set and hasattr(obj, 'get_query_set'):
            if obj.get_query_set.im_func.__name__ != 'get_query_set_wrapper':
                # only wrap it once (previous to django 1.6)
                obj.get_query_set = types.MethodType(
                    wrap_related_manager_get_query_set(
                        obj.get_query_set), obj)

        if do_wrap_get_query_set and hasattr(obj, 'get_queryset'):
            if obj.get_queryset.im_func.__name__ != 'get_query_set_wrapper':
                # only wrap it once (django 1.6)
                obj.get_queryset = types.MethodType(
                    wrap_related_manager_get_query_set(
                        obj.get_queryset), obj)
        return obj
    return get_wrapper

related.ReverseSingleRelatedObjectDescriptor.__get__ = wrap_descriptor_get(
    related.ReverseSingleRelatedObjectDescriptor.__get__)
related.ManyRelatedObjectsDescriptor.__get__ = wrap_descriptor_get(
    related.ManyRelatedObjectsDescriptor.__get__)
related.ForeignRelatedObjectsDescriptor.__get__ = wrap_descriptor_get(
    related.ForeignRelatedObjectsDescriptor.__get__, True)

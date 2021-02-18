# Copyright 2012 Canonical Ltd.
import itertools
import unittest
import datetime

from django.test import TestCase
from django.conf import settings
from django.core.management import call_command
from django.db import models
from django.db.models import loading
from django.db.models.manager import Manager
from django.contrib.auth.models import AnonymousUser, User

from django_group_access import middleware, wrap_getitem
from django_group_access import registration
from django_group_access.models import (
    get_group_model, process_auto_share_groups, populate_sharing,
    model_has_field)
from django_group_access.sandbox.models import (
    AccessRestrictedModel,
    AccessRestrictedProxy,
    AccessRestrictedParent,
    Build,
    Machine,
    PreFilteredModel,
    PreFilteredParent,
    Project,
    Release,
    Unrestricted,
    UniqueModel,
    UniqueForm,
    UnownedParent,
    UnownedChild,
    ParentWithNoId,
    ChildWithNoId,
)


def get_members(group):
    """
    Returns queryset of group members. Used so that the tests
    don't have to think about the different ways of getting
    group members depending on the configured group model.
    """
    if hasattr(group, 'members'):
        return group.members.all()
    if hasattr(group, 'user_set'):
        return group.user_set.all()


def add_user(group, user):
    """
    Adds a user to a group instance. Automatically deals with
    the different attribute names for group membership.
    """
    if hasattr(group, 'members'):
        group.members.add(user)
    if hasattr(group, 'user_set'):
        group.user_set.add(user)


class UnsupportedSignalTests(TestCase):
    """
    Test that the functions used in the sharing signals don't crash
    when the group model doesn't support the functionality.
    """
    @unittest.skipIf(
        hasattr(get_group_model(), 'auto_share_groups'),
        'Group model does not have auto sharing capabilities.')
    def test_process_auto_share_groups_skips_if_not_applicable(self):
        """
        Running the process_auto_share_groups function with a
        group model that does not support it does not give
        any errors.
        """
        process_auto_share_groups(None, None, None)

    @unittest.skipIf(
        hasattr(get_group_model(), 'can_share_with'),
        'Group model does not have sharing permission capabilities.')
    def test_populate_sharing_skips_if_not_applicable(self):
        """
        Running the populate_sharing function with a
        group model that does not support it does not give
        any errors.
        """
        populate_sharing(None, None, None)


class SyncingTestCase(TestCase):
    """
    Makes sure the sandbox app is ready to use.
    """
    apps = ('django_group_access.sandbox',)

    def _pre_setup(self):
        # Add the models to the db.
        self._original_installed_apps = list(settings.INSTALLED_APPS)
        apps = list(settings.INSTALLED_APPS)
        for app in self.apps:
            apps.append(app)
        settings.INSTALLED_APPS = apps
        loading.cache.loaded = False
        self.group_model = get_group_model()
        call_command('syncdb', interactive=False, verbosity=0, migrate=False)
        # Call the original method that does the fixtures etc.
        super(SyncingTestCase, self)._pre_setup()

    def _post_teardown(self):
        # Call the original method.
        super(SyncingTestCase, self)._post_teardown()
        # Restore the settings.
        settings.INSTALLED_APPS = self._original_installed_apps
        loading.cache.loaded = False

    def _load_users(self, prefix, group):
        """
        Load users into a group, with a prefix on their username.
        """
        for i in range(3):
            user = User.objects.create(
                username='%s%d' % (prefix, i),
                email='%s%d@example.com' % (prefix, i))
            add_user(group, user)
            add_user(self.everyone, user)

    def _load_owned_models(self, group):
        """
        Create owned models for users in a group.
        """
        users = get_members(group).order_by('username')

        # parent class for these resources
        parent = AccessRestrictedParent.objects.create(
            name='%s parent record' % group.name)

        # one model per user, two for the first user
        for (idx, user) in enumerate(users):
            model = AccessRestrictedModel.objects.create(
                owner=user, name='%s record %d' % (group.name, idx),
                parent=parent)
            model.access_groups.add(group)

        user = users[0]
        model = AccessRestrictedModel.objects.create(
            owner=user, name='%s record extra' % group.name,
            parent=parent)


class AccessRelationTests(SyncingTestCase):
    """
    Test that the access relations determine access based
    on other related models.
    """
    def setUp(self):
        super(AccessRelationTests, self).setUp()
        self.owner = _create_user()
        self.project = Project(owner=self.owner, name='project')
        self.project.save()
        self.build = Build(
            owner=self.owner, name='build', project=self.project)
        self.build.save()
        self.release = Release(
            owner=self.owner, name='release', build=self.build)
        self.release.save()
        self.group = self._create_access_group_with_one_member()
        self.project.access_groups.add(self.group)
        self.project.save()
        self.user_with_access = get_members(self.group)[0]
        self.user_without_access = _create_user()

    def _create_access_group_with_one_member(self):
        group = self.group_model.objects.create(name='oem')
        add_user(group, _create_user())
        return group

    def test_direct_reference(self):
        """
        A model that has its access relation pointing at
        a directly related model will have its accessibility determined
        by if the user has access to the related model.
        """
        query_method = Build.objects.accessible_by_user

        self.assertEqual('project', Build.access_control_relation)
        self.assertEqual(
            [self.build.name], [b.name for b in query_method(self.owner)])
        self.assertEqual(
            [self.build.name],
            [b.name for b in query_method(self.user_with_access)])
        self.assertEqual(
            [], [b for b in query_method(self.user_without_access)])

    def test_indirect_reference(self):
        """
        A model that has its access relation pointing at
        a model that is not a direct relation of itself
        (perhaps relation__othermodel) will have its accessibility
        determined by if the user has access to the related model.
        """
        # Release has no foreign key to Project, but it has one to Build
        # and it can use that to tell us to do the access group checks on
        # Project.
        query_method = Release.objects.accessible_by_user

        self.assertEqual('build__project', Release.access_control_relation)
        self.assertEqual(
            [self.release.name], [r.name for r in query_method(self.owner)])
        self.assertEqual(
            [self.release.name],
            [r.name for r in query_method(self.user_with_access)])
        self.assertEqual(
            [], [r for r in query_method(self.user_without_access)])

    def test_visible_if_no_related_records(self):
        """
        A model with an access relation that has no records will be shown.
        """
        AccessRestrictedParent.objects.create(name='blah44')
        records = AccessRestrictedParent.objects.accessible_by_user(
            self.user_without_access)
        self.assertEqual(records.count(), 1)
        self.assertEqual(records[0].name, 'blah44')

    def test_not_visible_if_no_related_records(self):
        """
        A model with an access relation that has no records will not be shown.
        if DGA_NO_RELATED_RECORD_VISIBILITY is False
        """
        old_setting = getattr(
            settings, 'DGA_NO_RELATED_RECORD_VISIBILITY',
            True)
        settings.DGA_NO_RELATED_RECORD_VISIBILITY = False

        AccessRestrictedParent.objects.create(name='blah44')
        records = AccessRestrictedParent.objects.accessible_by_user(
            self.user_without_access)
        self.assertEqual(records.count(), 0)

        settings.DGA_NO_RELATED_RECORD_VISIBILITY = old_setting

    def test_not_visible_if_all_related_records_are_hidden_from_user(self):
        """
        If all the related records are not available to the user, the parent
        record is also not visible.
        """
        parent = AccessRestrictedParent.objects.create(name='blah_parent')
        child = AccessRestrictedModel.objects.create(parent=parent)
        child.access_groups.add(self.group)

        records = AccessRestrictedParent.objects.accessible_by_user(
            self.user_without_access)
        self.assertEqual(set(records), set([]))

    def test_visible_if_related_records_only_have_owner_set(self):
        """
        If access groups are not used and access is only managed by
        setting the owner, the records should still show.
        """
        user = self.user_without_access
        parent = AccessRestrictedParent.objects.create(name='blah_parent')
        AccessRestrictedModel.objects.create(parent=parent, owner=user)
        records = AccessRestrictedParent.objects.accessible_by_user(user)
        self.assertEqual(set([parent]), set(records))

    def test_access_checks_with_no_owners_at_all(self):
        """
        If child and parent models do not have the owner column at all,
        the access controls are still applied.
        """
        parent = UnownedParent.objects.create(name='blah_parent')
        UnownedChild.objects.create(name='child', parent=parent)
        parent.access_groups.add(self.group)

        records = UnownedChild.objects.accessible_by_user(
            self.user_without_access)
        self.assertEqual(set(records), set([]))


class AccessTest(SyncingTestCase):
    """
    Test that access restrictions are applied.
    """
    everyone = None
    restricted_group_a = None
    restricted_group_b = None

    def setUp(self):
        self.everyone = self.group_model.objects.create(name='everyone')

        self.public_group = self.group_model.objects.create(name='public')
        self.restricted_group_a = self.group_model.objects.create(name='the cabal')
        self.restricted_group_b = self.group_model.objects.create(name='the stonecutters')

        self._load_users('public', self.public_group)
        self._load_users('cabal', self.restricted_group_a)
        self._load_users('stonecutter', self.restricted_group_b)

        self._load_owned_models(self.public_group)
        self._load_owned_models(self.restricted_group_a)
        self._load_owned_models(self.restricted_group_b)

        User.objects.create(
            username='nogroupuser', email='nogroup@example.com')
        self.superuser = User.objects.create(
            username='superuser', email='super@example.com')
        self.superuser.is_superuser = True
        self.superuser.save()
        self.mike = User.objects.create(
            username='mike', email='mike@example.com')

    def test_get_own_resources(self):
        """
        A user has access to their owned records.
        """
        user = get_members(
            self.restricted_group_a).order_by('username')[0]
        mine = AccessRestrictedModel.objects.get_for_owner(user)
        self.assertEqual(mine.count(), 2)
        self.assertEqual(mine[0].name, 'the cabal record 0')
        self.assertEqual(mine[1].name, 'the cabal record extra')

    def test_accessible_parent_records(self):
        """
        A user can access parent records of records that he owns.
        """
        user = get_members(
            self.restricted_group_a).order_by('username')[0]
        parents = AccessRestrictedParent.objects.accessible_by_user(user)
        self.assertEqual(parents.count(), 1)
        self.assertEqual(parents[0].name, 'the cabal parent record')

    def test_can_access_owned_records_if_not_in_a_group(self):
        """
        A user who is not in a group can still access their owned records.
        """
        user = User.objects.create(
            username='groupless', email='groupless@example.com')
        owned = AccessRestrictedModel.objects.create(
            name='a record', owner=user)

        record = AccessRestrictedModel.objects.accessible_by_user(
            user).get(pk=owned.id)
        self.assertEqual(record, owned)

    def test_can_see_individual_records_shared_with_my_group(self):
        """
        Test that individual records become visible when shared with
        a user's group.
        """
        record = AccessRestrictedModel.objects.get(
                    name='the stonecutters record 1')
        group = self.group_model.objects.get(name='the cabal')
        record.access_groups.add(group)
        record.save()
        user = get_members(group)[0]
        available = AccessRestrictedModel.objects.accessible_by_user(user)
        self.assertEqual(available.count(), 5)
        self.assertEqual(available[0].name, 'the cabal record 0')
        self.assertEqual(available[1].name, 'the cabal record 1')
        self.assertEqual(available[2].name, 'the cabal record 2')
        self.assertEqual(available[3].name, 'the cabal record extra')
        self.assertEqual(available[4].name, 'the stonecutters record 1')

    def test_superusers_see_all(self):
        """
        Superusers see all records, regardless of group membership.
        """
        available = AccessRestrictedModel.objects.accessible_by_user(
            self.superuser)
        self.assertEqual(available.count(), 12)
        available = AccessRestrictedParent.objects.accessible_by_user(
            self.superuser)
        self.assertEqual(available.count(), 3)

    def test_unrestricted_access_hooks_are_called(self):
        """
        A model can be registered with an array of functions that
        check if the resultsets should return all data.
        AccessRestrictedModel has been registered with a function
        that returns True if the user's username is 'mike'
        """
        available = AccessRestrictedModel.objects.accessible_by_user(
            self.mike)
        self.assertEqual(available.count(), 12)

    def test_unrestricted_access_hooks_for_control_relation(self):
        """
        Models registered with a control_relation should use the
        unrestricted_access_hooks from the model the control_relation
        points at.
        """
        available = AccessRestrictedParent.objects.accessible_by_user(
            self.mike)
        self.assertEqual(available.count(), 3)

    def test_can_see_records_with_no_controlling_access_records(self):
        """
        If a models is defined as having a control relation, but the
        control relation has no records to determine access, it is
        accessible.
        """
        user = _create_user()
        record = AccessRestrictedParent.objects.create(
            name='no related records')
        available = AccessRestrictedParent.objects.accessible_by_user(user)
        self.assertEqual(available.count(), 1)
        self.assertEqual(available[0], record)

    def test_proxy_models_use_concrete_model_rules(self):
        """
        If a model is a proxy for another model, the original model's
        access control rules are used.
        """
        group = self.group_model.objects.get(name='the cabal')
        user = get_members(group)[0]
        record = AccessRestrictedModel.objects.get(
                    name='the stonecutters record 1')
        record.owner = user
        record.save()
        available = AccessRestrictedProxy.objects.accessible_by_user(user)

        self.assertEqual(available.count(), 5)
        self.assertEqual(available[0].name, 'the cabal record 0')
        self.assertEqual(available[1].name, 'the cabal record 1')
        self.assertEqual(available[2].name, 'the cabal record 2')
        self.assertEqual(available[3].name, 'the cabal record extra')
        self.assertEqual(available[4].name, 'the stonecutters record 1')


class AccessGroupCapabilitiesTest(SyncingTestCase):
    """
    Test for the automatic sharing capabilities that
    django_group_access.models.AccessGroup provides.
    """
    everyone = None
    public_group = None
    restricted_group_a = None
    restricted_group_b = None
    supergroup = None

    def setUp(self):
        self.everyone = self.group_model.objects.create(name='everyone')

        self.public_group = self.group_model.objects.create(name='public')
        self.restricted_group_a = self.group_model.objects.create(name='the cabal')
        self.restricted_group_b = self.group_model.objects.create(name='the stonecutters')

        self.restricted_group_b.auto_share_groups.add(self.restricted_group_b)
        self.restricted_group_a.auto_share_groups.add(self.restricted_group_a)
        self.public_group.auto_share_groups.add(self.everyone)
        self.public_group.auto_share_groups.add(self.public_group)

        self._load_users('public', self.public_group)
        self._load_users('cabal', self.restricted_group_a)
        self._load_users('stonecutter', self.restricted_group_b)

        self._load_owned_models(self.public_group)
        self._load_owned_models(self.restricted_group_a)
        self._load_owned_models(self.restricted_group_b)

        self.supergroup = self.group_model.objects.create(name='supergroup', supergroup=True)
        add_user(self.supergroup, _create_user())

        su = User.objects.create(
                username='supergroupuser', email='supergroup@example.com')
        add_user(self.supergroup, su)

        User.objects.create(
            username='nogroupuser', email='nogroup@example.com')
        self.superuser = User.objects.create(
            username='superuser', email='super@example.com')
        self.superuser.is_superuser = True
        self.superuser.save()

    @unittest.skipIf(
        not hasattr(get_group_model(), 'auto_share_groups'),
        'Group model does not have auto sharing capabilities.')
    def test_can_be_shared_group_is_added_to_other_sharing_lists(self):
        """
        A group that can be shared with is automatically added to other
        group's sharing lists when it is created.
        """
        self.group_model.objects.all().delete()
        group_a = self.group_model(name='A', can_be_shared_with=False)
        group_a.save()
        group_b = self.group_model(name='B', can_be_shared_with=False)
        group_b.save()

        self.assertEqual(str(group_a.can_share_with.all()), str([group_a]))
        self.assertEqual(str(group_b.can_share_with.all()), str([group_b]))

        group_a.can_be_shared_with = True
        group_a.save()

        self.assertEqual(str(group_a.can_share_with.all()), str([group_a]))
        self.assertEqual(
            str(group_b.can_share_with.all()), str([group_a, group_b]))

        group_a.can_be_shared_with = False
        group_a.save()

        self.assertEqual(str(group_a.can_share_with.all()), str([group_a]))
        self.assertEqual(str(group_b.can_share_with.all()), str([group_b]))

    @unittest.skipIf(
        not hasattr(get_group_model(), 'auto_share_groups'),
        'Group model does not have auto sharing capabilities.')
    def test_records_shared_automatically(self):
        """
        Saved records should be shared with the auto_share_groups on the groups
        the creating owner is a member of.
        """
        u = get_members(self.restricted_group_a).order_by('username')[0]

        # should return all of the records owned by someone in the user's group
        # plus all records automatically shared
        available = AccessRestrictedModel.objects.accessible_by_user(user=u)
        self.assertEqual(available.count(), 8)
        self.assertEqual(available[0].name, 'public record 0')
        self.assertEqual(available[1].name, 'public record 1')
        self.assertEqual(available[2].name, 'public record 2')
        self.assertEqual(available[3].name, 'public record extra')
        self.assertEqual(available[4].name, 'the cabal record 0')
        self.assertEqual(available[5].name, 'the cabal record 1')
        self.assertEqual(available[6].name, 'the cabal record 2')
        self.assertEqual(available[7].name, 'the cabal record extra')

        record = AccessRestrictedModel.objects.accessible_by_user(u)\
                .get(name='public record 2')
        self.assertTrue(record.name, 'public record 2')

        try:
            record = AccessRestrictedModel.objects.accessible_by_user(u)\
                    .get(name='the stonecutters record 1')
            self.fail(
                "Shouldn't be able to access other non public group record")
        except AccessRestrictedModel.DoesNotExist:
            pass

    @unittest.skipIf(
        not model_has_field(get_group_model(), 'supergroup'),
        'Group model does not have supergroup capabilities.')
    def test_members_of_supergroups_see_all(self):
        """
        Members of supergroups see all records.
        """
        supergroup_member = get_members(self.supergroup)[0]
        available = AccessRestrictedModel.objects.accessible_by_user(
            supergroup_member)
        self.assertEqual(available.count(), 12)
        available = AccessRestrictedParent.objects.accessible_by_user(
            supergroup_member)
        self.assertEqual(available.count(), 3)


class MetaInformationPropagationTest(SyncingTestCase):
    """
    Test that the meta information about the access control
    filtering is passed around the models, managers,
    and querysets correctly.
    """
    def setUp(self):
        self.group1 = self.group_model.objects.create(name='group1')
        self.group2 = self.group_model.objects.create(name='group2')
        self.user = _create_user()
        other_user = _create_user()
        unrestricted = Unrestricted.objects.create(
            name='project1 unrestricted')
        self.project1 = Project.objects.create(
            name='project1', owner=self.user,
            unrestricted=unrestricted)
        self.machine1 = Machine.objects.create(
            name='machine1', owner=self.user)
        self.machine2 = Machine.objects.create(
            name='machine2', owner=other_user)
        self.project1.machines.add(self.machine1)
        self.project1.machines.add(self.machine2)
        Build.objects.create(name='build1', project=self.project1)
        self.machine1.access_groups.add(self.group1)
        self.machine2.access_groups.add(self.group2)

    def test_queryset_initial_set(self):
        """
        The meta information is set when the first queryset is generated.
        """
        queryset = Project.objects.accessible_by_user(self.user).all()
        self.assertEqual(queryset._access_control_meta['user'], self.user)
        self.assertFalse(queryset._access_control_meta['unrestricted'], False)

    def test_queryset_set_as_unrestricted(self):
        """
        The unrestricted attribute of the metadata is set to True when
        the queryset is cloned through .unrestricted()
        """
        queryset = Project.objects.accessible_by_user(self.user).all()
        unrestricted_queryset = queryset.unrestricted()
        self.assertEqual(
            unrestricted_queryset._access_control_meta['user'], None)
        self.assertTrue(
            unrestricted_queryset._access_control_meta['unrestricted'])
        self.assertEqual(
            queryset._access_control_meta['user'], self.user)
        self.assertFalse(queryset._access_control_meta['unrestricted'])

    def test_queryset_clone(self):
        """
        The meta information is copied when subsequent querysets are made.
        """
        queryset = Project.objects.accessible_by_user(self.user).all()
        new_queryset = queryset.filter(name='stuff')
        self.assertEqual(
            new_queryset._access_control_meta,
            queryset._access_control_meta)

    def test_lists_get_metadata(self):
        """
        Turning a queryset into a list will put the metadata on each
        item in the list.
        """
        projects = Project.objects.accessible_by_user(self.user)
        project_list = list(projects)
        for project in project_list:
            self.assertEqual(
                project._access_control_meta, projects._access_control_meta)

    def test_get(self):
        """
        Meta information should appear on the model returned from .get()
        """
        queryset = Project.objects.accessible_by_user(self.user).all()
        model = queryset.get(pk=self.project1.id)
        self.assertEqual(
            model._access_control_meta, queryset._access_control_meta)

    def test_iterator(self):
        """
        Meta information should appear on the models when the queryset
        is iterated over.
        """
        queryset = Project.objects.accessible_by_user(self.user).all()
        for model in queryset:
            self.assertEqual(
                model._access_control_meta, queryset._access_control_meta)

    def test_model_gets_metadata_from_queryset(self):
        """
        Models are loaded with the access control metadata when they
        come from an access control filtered queryset.
        """
        queryset = Project.objects.accessible_by_user(self.user).all()
        model = queryset[0]
        self.assertEqual(
            queryset._access_control_meta, model._access_control_meta)

    def test_foreignkey_model_gets_metadata(self):
        """
        Models related through a foreign key have the meta data set.
        """
        queryset = Project.objects.accessible_by_user(self.user).all()
        model = queryset[0]
        self.assertEqual(
            model._access_control_meta,
            model.unrestricted._access_control_meta)

    def test_many_to_many_related_queryset_gets_metadata(self):
        """
        ManyToMany managers have the meta data set from the instance.
        """
        queryset = Project.objects.accessible_by_user(self.user).all()
        model = queryset[0]
        queryset = model.machines.all()
        self.assertEqual(
            model._access_control_meta,
            queryset._access_control_meta)

    def test_model_from_many_to_many_related_queryset_gets_metadata(self):
        """
        Models retrieved through a ManyToMany manager have the meta data
        set from the instance they came from.
        """
        queryset = Project.objects.accessible_by_user(self.user).all()
        model = queryset[0]
        machine = model.machines.all()[0]
        self.assertEqual(
            machine._access_control_meta,
            queryset._access_control_meta)

    def test_foreign_related_sets_get_metadata(self):
        """
        The managers for foreignkey _sets are loaded with the metadata
        from the instance.
        """
        queryset = Project.objects.accessible_by_user(self.user).all()
        model = queryset[0]
        self.assertEqual(
            model.build_set._access_control_meta,
            model._access_control_meta)

    def test_models_from_foreign_related_sets_get_metadata(self):
        """
        The models accessed through foreignkey _sets are loaded with the
        metadata from the original query.
        """
        queryset = Project.objects.accessible_by_user(self.user).all()
        project = queryset[0]
        build = project.build_set.all()[0]
        self.assertEqual(
            build._access_control_meta,
            queryset._access_control_meta)


class AccessManagerMixinTest(TestCase):
    """
    Test that the code from AccessManager has been injected into
    the base Manager class.
    """
    def test_access_manager_methods_on_manager(self):
        """
        Methods that are defined on the AccessManagerMixin have been
        added to the base Manager class.
        """
        manager = Manager()
        self.assertTrue(hasattr(manager, 'get_for_owner'))
        self.assertTrue(hasattr(manager, 'accessible_by_user'))


class RelatedRecordFilteringTest(SyncingTestCase):
    def setUp(self):
        self.group1 = self.group_model.objects.create(name='group1')
        self.group2 = self.group_model.objects.create(name='group2')
        self.user = _create_user()
        other_user = _create_user()
        add_user(self.group1, self.user)
        add_user(self.group2, other_user)
        self.parent1 = AccessRestrictedParent.objects.create(name='parent1')
        self.parent2 = AccessRestrictedParent.objects.create(name='parent2')
        self.child1 = AccessRestrictedModel.objects.create(
            parent=self.parent1, owner=self.user, name='child1')
        self.child2 = AccessRestrictedModel.objects.create(
            parent=self.parent1, owner=other_user, name='child2')
        self.child3 = AccessRestrictedModel.objects.create(
            parent=self.parent2, owner=self.user, name='child3')
        self.child4 = AccessRestrictedModel.objects.create(
            parent=self.parent2, owner=other_user, name='child4')
        self.child1.access_groups.add(self.group1)
        self.child2.access_groups.add(self.group2)
        self.child3.access_groups.add(self.group1)
        self.child4.access_groups.add(self.group2)

    def test_related_set_filtered_for_user(self):
        """
        When using accessible_by_user to retrieve a record,
        the related records for access controlled models are
        also filtered by that user.
        """
        parent = AccessRestrictedParent.objects.accessible_by_user(
            self.user).get(pk=self.parent1.id)
        self.assertEqual(
            set(parent.accessrestrictedmodel_set.all()), set([self.child1]))

    def test_filter_persisted_as_relationships_followed(self):
        """
        When following relationships between models, the
        access restrictions still apply.
        """
        parent = AccessRestrictedParent.objects.accessible_by_user(
            self.user).get(pk=self.parent1.id)
        restricted_model = parent.accessrestrictedmodel_set.all()[0]
        parent = restricted_model.parent
        self.assertEqual(
            set(parent.accessrestrictedmodel_set.all()), set([self.child1]))


class ManyToManyRelatedRecordFilteringTest(SyncingTestCase):
    def setUp(self):
        self.group1 = self.group_model.objects.create(name='group1')
        self.group2 = self.group_model.objects.create(name='group2')
        self.user = _create_user()
        other_user = _create_user()
        self.project1 = Project.objects.create(
            name='project1', owner=self.user)
        self.machine1 = Machine.objects.create(
            name='machine1', owner=self.user)
        self.machine2 = Machine.objects.create(
            name='machine2', owner=other_user)
        self.project1.machines.add(self.machine1)
        self.project1.machines.add(self.machine2)
        self.machine1.access_groups.add(self.group1)
        self.machine2.access_groups.add(self.group2)

    def test_many_to_many_related_set_filtered_for_user(self):
        """
        When using accessible_by_user to retrieve a record,
        the related records for access controlled models are
        also filtered by that user.
        """
        project = Project.objects.accessible_by_user(self.user)[0]
        self.assertEqual(
            set(project.machines.all()), set([self.machine1]))

    def test_many_to_many_related_set_filtered_for_user_using_get(self):
        """
        When using accessible_by_user to retrieve a record,
        the related records for access controlled models are
        also filtered by that user.
        """
        project = Project.objects.accessible_by_user(
            self.user).get(pk=self.project1.id)
        self.assertEqual(
            set(project.machines.all()), set([self.machine1]))

    def test_filter_persisted_as_relationships_followed(self):
        """
        When following relationships between models, the
        access restrictions still apply.
        """
        project = Project.objects.accessible_by_user(
            self.user).get(pk=self.project1.id)
        machine = project.machines.all()[0]
        project = machine.project_set.all()[0]
        self.assertEqual(
            set(project.machines.all()), set([self.machine1]))


class RegistrationTest(TestCase):
    """
    Tests the model registration.
    """
    def setUp(self):
        self.old_models = registration._registered_models.copy()
        self.old_filter_models = registration._auto_filter_models.copy()

    def tearDown(self):
        registration._registered_models = self.old_models.copy()
        registration.auto_filter_models = self.old_filter_models.copy()

    def test_unregistered_model_is_not_marked_as_registered(self):
        """
        Calling registration.is_registered_model for an unregistered
        model returns False.
        """
        class UnregisteredModel(models.Model):
            pass
        self.assertFalse(registration.is_registered_model(UnregisteredModel))

    def test_register_adds_model_to_list_of_registered_models(self):
        """
        Registering a model adds it to the list of registered models.
        """
        class RegistrationTestModel(models.Model):
            pass
        registration.register(RegistrationTestModel)
        self.assertTrue(
            registration.is_registered_model(RegistrationTestModel))

    def test_register_adds_access_groups_to_model(self):
        """
        Registering a model adds the access group relation.
        """
        class AccessGroupRelationTestModel(models.Model):
            pass
        registration.register(AccessGroupRelationTestModel)
        self.assertTrue(isinstance(
            AccessGroupRelationTestModel.access_groups,
            models.fields.related.ReverseManyRelatedObjectsDescriptor))

    def test_register_adds_owner_to_model(self):
        """
        Registered a model adds the owner field.
        """
        class AddOwnerTestModel(models.Model):
            pass
        registration.register(AddOwnerTestModel)
        self.assertTrue(isinstance(
            AddOwnerTestModel.owner,
            models.fields.related.ReverseSingleRelatedObjectDescriptor))

    def test_register_does_not_add_owner_to_model(self):
        """
        Registered a model does not the owner field of registered with
        owner=False.
        """
        class DontAddOwnerTestModel(models.Model):
            pass
        registration.register(DontAddOwnerTestModel, owner=False)
        self.assertFalse(hasattr(DontAddOwnerTestModel, 'owner'))

    def test_model_with_control_relation_does_not_get_access_groups(self):
        """
        Registering a model that uses a control relation for access control
        will not get the access_groups property, but still has owner, and
        also has the control_relation property.
        """
        class ControlRelationControlledTestModel(models.Model):
            pass
        registration.register(
            ControlRelationControlledTestModel, control_relation='other_model')
        self.assertTrue(hasattr(ControlRelationControlledTestModel, 'owner'))
        self.assertFalse(
            hasattr(ControlRelationControlledTestModel, 'access_groups'))
        self.assertEqual(
            ControlRelationControlledTestModel.access_control_relation,
            'other_model')

    def test_register_model_with_unrestricted_manager(self):
        """
        Nominating an unrestricted manager will create the manager on the
        nominated attribute and set _access_control_meta['unrestrcted']
        to true and _access_control_meta['user'] to None.
        """
        class UnrestrictedManagerTestModel(models.Model):
            pass
        registration.register(
            UnrestrictedManagerTestModel,
            unrestricted_manager='objects_unrestricted')
        manager = UnrestrictedManagerTestModel.objects_unrestricted
        self.assertTrue(manager._access_control_meta['unrestricted'])
        self.assertEqual(manager._access_control_meta['user'], None)

    def test_register_model_adds_to_the_auto_filter_list(self):
        """
        Registering a model adds it to the list of models that
        would be automatically filtered.
        """
        class AutoFilterRegistrationTestModel(models.Model):
            pass
        registration.register(AutoFilterRegistrationTestModel)
        self.assertTrue(
            registration.is_auto_filtered(AutoFilterRegistrationTestModel))

    def test_register_model_exclude_from_the_auto_filter_list(self):
        """
        Registering a model with auto_filter=False does not add it to
        the list of models that would be automatically filtered.
        """
        class DoNotAutoFilterRegistrationTestModel(models.Model):
            pass
        registration.register(
            DoNotAutoFilterRegistrationTestModel, auto_filter=False)
        self.assertFalse(
            registration.is_auto_filtered(
                DoNotAutoFilterRegistrationTestModel))

    def test_related_name_on_owner(self):
        """
        Related name on owner should be include the model class name
        to prevent related_name clashes.
        """
        class RelatedNameTestModel(models.Model):
            pass
        registration.register(RelatedNameTestModel)
        self.assertEqual(
            RelatedNameTestModel.owner.field.rel.related_name,
            'relatednametestmodel_owner')


class UnrestrictedAccessTest(SyncingTestCase):
    """
    Test that a queryset which has had accessible_by_user used
    in it can have the effects of accessible_by_user reversed by
    calling .unrestricted()
    """
    def setUp(self):
        self.group1 = self.group_model.objects.create(name='group1')
        self.group2 = self.group_model.objects.create(name='group2')
        self.user = _create_user()
        other_user = _create_user()
        self.project1 = Project.objects.create(
            name='project1', owner=self.user)
        self.project2 = Project.objects.create(
            name='project2', owner=other_user)
        self.machine1 = Machine.objects.create(
            name='machine1', owner=self.user)
        self.machine2 = Machine.objects.create(
            name='machine2', owner=other_user)
        self.project1.machines.add(self.machine1)
        self.project1.machines.add(self.machine2)
        self.machine1.access_groups.add(self.group1)
        self.machine2.access_groups.add(self.group2)

    def test_unrestricted_returned_queryset_with_no_access_control(self):
        """
        Calling .unrestricted() will return a queryset which is a
        clone of the original but without any access restrictions imposed.
        """
        projects = Project.objects.accessible_by_user(self.user).all()
        all_projects = projects.unrestricted()
        self.assertEqual(all_projects.count(), 2)
        self.assertEqual(projects.count(), 1)


class DbMethodsHaveRestrictionsAppliedTest(SyncingTestCase):
    """
    Tests each method on queryset that retrives records from
    the database has the restrictions applied when the queryset
    has been filtered with accessible_by_user.
    """
    def setUp(self):
        self.group1 = self.group_model.objects.create(name='group1')
        self.group2 = self.group_model.objects.create(name='group2')
        self.user = _create_user()
        self.other_user = _create_user()
        self.project1 = Project.objects.create(
            name='project1', owner=self.user)
        self.project2 = Project.objects.create(
            name='project2', owner=self.other_user)
        self.machine1 = Machine.objects.create(
            name='machine1', owner=self.user)
        self.machine2 = Machine.objects.create(
            name='machine2', owner=self.other_user)
        self.project1.machines.add(self.machine1)
        self.project1.machines.add(self.machine2)
        self.machine1.access_groups.add(self.group1)
        self.machine2.access_groups.add(self.group2)

    def test_get(self):
        project = Project.objects.accessible_by_user(
            self.user).get(pk=self.project1.id)
        self.assertEqual(project.id, self.project1.id)
        try:
            project = Project.objects.accessible_by_user(
                self.user).get(pk=self.project2.id)
            self.fail(
                'Was able to get a project that user did not have access to')
        except Project.DoesNotExist:
            pass

    def test_iterate(self):
        projects = list(
            Project.objects.accessible_by_user(self.user).all())
        self.assertEqual(len(projects), 1)

    def test_aggregate(self):
        self.assertEqual(
            Project.objects.accessible_by_user(
                self.user).aggregate(models.Max('id')),
            {'id__max': 1})

    def test_count(self):
        self.assertEqual(
            Project.objects.accessible_by_user(self.user).count(), 1)

    def test_exists(self):
        """
        Ask if records exist that we're not allowed to see, should return
        False.
        """
        self.assertFalse(
            Project.objects.accessible_by_user(
                self.user).filter(owner=self.other_user).exists())

    def test_latest(self):
        self.assertEqual(
            Project.objects.accessible_by_user(
                self.user).latest(field_name='id'),
            self.project1)

    def test_in_bulk(self):
        self.assertEqual(
            Project.objects.accessible_by_user(
                self.user).in_bulk([self.project1.id, self.project2.id]),
            {1: self.project1})


class RefactorBugsTest(SyncingTestCase):
    """
    Tests for various ways the code was broken during the refactor to
    support .unrestricted() on querysets.
    """
    def setUp(self):
        self.group1 = self.group_model.objects.create(name='group1')
        self.group2 = self.group_model.objects.create(name='group2')
        self.user = _create_user()
        self.other_user = _create_user()
        self.project1 = Project.objects.create(
            name='project1', owner=self.user)
        self.project2 = Project.objects.create(
            name='project2', owner=self.other_user)
        self.machine1 = Machine.objects.create(
            name='machine1', owner=self.user)
        self.machine2 = Machine.objects.create(
            name='machine2', owner=self.other_user)
        self.project1.machines.add(self.machine1)
        self.project1.machines.add(self.machine2)
        self.machine1.access_groups.add(self.group1)
        self.machine2.access_groups.add(self.group2)

    def test_repr_in_iteration_loop(self):
        """
        Converting models to a string inside a loop
        should not cause a nasty recursion error.
        """
        for project in Project.objects.accessible_by_user(self.user):
            self.assertTrue(bool('%s' % project))

    def test_multiple_count_calls_are_accurate(self):
        """
        Multiple calls to .count() all return the correct value.
        """
        projects = Project.objects.accessible_by_user(self.user)
        self.assertEqual(projects.count(), 1)
        self.assertEqual(projects.count(), 1)
        self.assertEqual(projects.count(), 1)

    def test_get_back_foreignkey_with_no_record(self):
        """
        Get back a nullable foreignkey which is not set, should return None.
        """
        project = Project.objects.accessible_by_user(
            self.user).get(pk=self.project1.id)
        other_model = project.unrestricted
        self.assertEqual(other_model, None)

    def test_getitem_wrapper_handles_lists(self):
        """
        QuerySet.__getitem__ can return lists of objects
        which need metadata propagating to them.
        """
        class MockObject(object):
            pass

        def mock_getitem(self, key):
            return [MockObject(), MockObject()]

        func = wrap_getitem(mock_getitem)
        mock_self = MockObject()
        mock_self._access_control_meta = {'key': 42}
        result = func(mock_self, 42)
        self.assertEqual(len(result), 2)
        for obj in result:
            self.assertEqual(
                obj._access_control_meta, mock_self._access_control_meta)


class AutomaticFilteringTest(SyncingTestCase):
    """
    Test that the automatic filtering and middleware methods.
    """
    def setUp(self):

        class MockRequest(object):
            pass

        self.group1 = self.group_model.objects.create(name='group1')
        self.group2 = self.group_model.objects.create(name='group2')
        self.user = _create_user()
        self.other_user = _create_user()
        self.project1 = Project.objects.create(
            name='project1', owner=self.user)
        self.project2 = Project.objects.create(
            name='project2', owner=self.other_user)
        self.machine1 = Machine.objects.create(
            name='machine1', owner=self.user)
        self.machine2 = Machine.objects.create(
            name='machine2', owner=self.other_user)
        self.project1.machines.add(self.machine1)
        self.project1.machines.add(self.machine2)
        self.machine1.access_groups.add(self.group1)
        self.machine2.access_groups.add(self.group2)
        self.project1.access_groups.add(self.group1)
        self.project2.access_groups.add(self.group2)
        build1 = Build.objects.create(
            name='build1', owner=self.user, project=self.project1)
        Build.objects.create(
            name='build2', owner=self.other_user, project=self.project1)
        self.release = Release.objects.create(name='release1', build=build1)
        self.MockRequest = MockRequest

    def tearDown(self):
        if hasattr(middleware._storage, 'access_control_user'):
            del(middleware._storage.access_control_user)

    def test_middleware_process_request(self):
        """
        Test that the middleware sets the user in thread local storage.
        """
        processor = middleware.DjangoGroupAccessMiddleware()
        request = self.MockRequest()
        request.user = self.user
        result = processor.process_request(request)
        self.assertEqual(middleware.get_access_control_user(), self.user)
        self.assertEqual(result, None)

    def test_middleware_process_response(self):
        """
        Test that the middleware sets the user in thread local storage.
        """
        processor = middleware.DjangoGroupAccessMiddleware()
        request = self.MockRequest()
        request.user = self.user
        processor.process_request(request)
        response = processor.process_response(request, 'My Response')
        self.assertEqual(middleware.get_access_control_user(), None)
        self.assertEqual(response, 'My Response')

    def test_access_controls_applied_automatically(self):
        """
        When a user is registered with the access control middleware,
        access control rules are applied automatically.
        """
        processor = middleware.DjangoGroupAccessMiddleware()
        request = self.MockRequest()
        request.user = self.user
        processor.process_request(request)
        projects = Project.objects.all()
        self.assertEqual(projects.count(), 1)
        self.assertEqual(projects[0], self.project1)

        project = projects[0]
        self.assertEqual(project.machines.count(), 1)
        self.assertEqual(project.machines.all()[0], self.machine1)

    def test_automatically_filtered_querysets_can_be_unrestricted(self):
        """
        When a queryset is filtered automatically, calling unrestricted()
        will stop that happening.
        """
        processor = middleware.DjangoGroupAccessMiddleware()
        request = self.MockRequest()
        request.user = self.user
        processor.process_request(request)
        projects = Project.objects.all()
        projects = projects.unrestricted()
        self.assertEqual(projects.count(), 2)
        self.assertEqual(set(projects), set([self.project1, self.project2]))

    def test_unrestricted_manager_is_unrestricted(self):
        """
        When a request is being automatically filtered, unrestricted
        managers are still unrestricted.
        """
        processor = middleware.DjangoGroupAccessMiddleware()
        request = self.MockRequest()
        request.user = self.user
        processor.process_request(request)
        projects = Project.objects_unrestricted.all()
        self.assertEqual(projects.count(), 2)

    def test_nominate_model_not_to_be_automatically_filtered(self):
        """
        Models can be nominated to not be automatically filtered.
        """
        processor = middleware.DjangoGroupAccessMiddleware()
        request = self.MockRequest()
        request.user = self.user
        processor.process_request(request)
        builds = Build.objects.all()
        self.assertEqual(builds.count(), 2)

    def test_anonymous_user_sees_nothing(self):
        """
        Anonymous users should have no records visible with
        DGA_UNSHARED_RECORDS_ARE_PUBLIC unset or False
        """
        old_setting = getattr(
            settings, 'DGA_UNSHARED_RECORDS_ARE_PUBLIC',
            False)
        settings.DGA_UNSHARED_RECORDS_ARE_PUBLIC = False
        Project.objects.create(name='not shared')
        processor = middleware.DjangoGroupAccessMiddleware()
        request = self.MockRequest()
        request.user = AnonymousUser()
        processor.process_request(request)
        projects = Project.objects.all()
        self.assertEqual(projects.count(), 0)
        settings.DGA_UNSHARED_RECORDS_ARE_PUBLIC = old_setting

    def test_anonymous_user_sees_records_that_have_not_been_restricted(self):
        """
        If the DGA_UNSHARED_RECORDS_ARE_PUBLIC
        setting is True, anonymous users see all records that have not
        been explicitly shared with any access groups.
        """
        old_setting = getattr(
            settings, 'DGA_UNSHARED_RECORDS_ARE_PUBLIC',
            False)
        settings.DGA_UNSHARED_RECORDS_ARE_PUBLIC = True
        Project.objects.create(name='not shared')
        processor = middleware.DjangoGroupAccessMiddleware()
        request = self.MockRequest()
        request.user = AnonymousUser()
        processor.process_request(request)
        projects = Project.objects.all()
        self.assertEqual(projects.count(), 1)
        self.assertEqual(projects[0].name, 'not shared')
        settings.DGA_UNSHARED_RECORDS_ARE_PUBLIC = old_setting

    def test_anonymous_user_sees_unshared_controlled_through_relation(self):
        """
        If the DGA_UNSHARED_RECORDS_ARE_PUBLIC
        setting is True, anonymous users see all records that have not
        been explicitly shared with any access groups.
        This test is to check models restricted by a control_relation work
        with this setting.
        """
        old_setting = getattr(
            settings, 'DGA_UNSHARED_RECORDS_ARE_PUBLIC',
            False)
        settings.DGA_UNSHARED_RECORDS_ARE_PUBLIC = True
        project = Project.objects.create(name='not shared')
        build = Build.objects.create(project=project)
        release = Release.objects.create(build=build)
        processor = middleware.DjangoGroupAccessMiddleware()
        request = self.MockRequest()
        request.user = AnonymousUser()
        processor.process_request(request)
        releases = Release.objects.all()
        self.assertEqual(releases.count(), 1)
        self.assertEqual(releases[0], release)
        settings.DGA_UNSHARED_RECORDS_ARE_PUBLIC = old_setting

    def test_authenticaed_user_sees_unshared_public_records(self):
        """
        If the DGA_UNSHARED_RECORDS_ARE_PUBLIC
        setting is True, authenticated users see all records that have not
        been explicitly shared with any access groups.
        """
        old_setting = getattr(
            settings, 'DGA_UNSHARED_RECORDS_ARE_PUBLIC',
            False)
        settings.DGA_UNSHARED_RECORDS_ARE_PUBLIC = True
        project = Project.objects.create(name='not shared')
        build = Build.objects.create(project=project)
        release = Release.objects.create(build=build)
        processor = middleware.DjangoGroupAccessMiddleware()
        request = self.MockRequest()
        request.user = self.user
        processor.process_request(request)
        releases = Release.objects.all()
        self.assertEqual(releases.count(), 2)
        self.assertEqual(set(releases), set([release, self.release]))
        settings.DGA_UNSHARED_RECORDS_ARE_PUBLIC = old_setting

    def test_authenticated_user_sees_unshared_records(self):
        """
        If the DGA_UNSHARED_RECORDS_ARE_PUBLIC
        setting is True, authenticated users see all records that have not
        been explicitly shared with any access groups.
        """
        old_setting = getattr(
            settings, 'DGA_UNSHARED_RECORDS_ARE_PUBLIC',
            False)
        settings.DGA_UNSHARED_RECORDS_ARE_PUBLIC = True
        project = Project.objects.create(name='not shared')
        processor = middleware.DjangoGroupAccessMiddleware()
        request = self.MockRequest()
        request.user = self.user
        processor.process_request(request)
        projects = Project.objects.all()
        self.assertEqual(projects.count(), 2)
        self.assertEqual(set(projects), set([project, self.project1]))
        settings.DGA_UNSHARED_RECORDS_ARE_PUBLIC = old_setting

    def test_user_storage_is_local_to_current_thread(self):
        """
        Test that the user stored is local to the current thread.
        """
        import threading

        class StorageTestThread(threading.Thread):
            def __init__(self, user, *args, **kwargs):
                self.stored_user = None
                self.user = user
                super(StorageTestThread, self).__init__(*args, **kwargs)

            def run(self):
                class MockRequest(object):
                    pass
                processor = middleware.DjangoGroupAccessMiddleware()
                request = MockRequest()
                request.user = self.user
                processor.process_request(request)
                self.stored_user = middleware.get_access_control_user()

        storage_test_thread_1 = StorageTestThread(self.user)
        storage_test_thread_1.start()
        storage_test_thread_2 = StorageTestThread(self.other_user)
        storage_test_thread_2.start()
        while (
            storage_test_thread_1.stored_user is None or
            storage_test_thread_2.stored_user is None):
            pass

        # thread 1 had our test user
        self.assertEqual(storage_test_thread_1.stored_user, self.user)
        # thread 2 had the other user
        self.assertEqual(storage_test_thread_2.stored_user, self.other_user)
        # our local test thread has no user
        self.assertEqual(middleware.get_access_control_user(), None)

    def test_middleware_set_access_control_user(self):
        """
        set_access_control_user should take a User object and set that user as
        the user for subsequent access control requests.
        """
        middleware.set_access_control_user(self.user)
        self.assertEqual(middleware.get_access_control_user(), self.user)


class UniqueContraintsInModelForms(SyncingTestCase):
    """
    Test that unique constraints are handled when using
    a ModelForm.
    """
    def setUp(self):
        class MockRequest(object):
            pass
        self.MockRequest = MockRequest
        self.user = _create_user()
        group1 = self.group_model.objects.create(name='group1')
        group2 = self.group_model.objects.create(name='group2')
        other_user = _create_user()
        add_user(group1, self.user)
        add_user(group2, other_user)
        # self.user cannot see this record
        record = UniqueModel.objects.create(name='my name')
        record.access_groups.add(group2)

    def test_all_records_used_to_check_unique_fields(self):
        """
        When saving a ModelForm while automatic filtering is
        active, all records are used when checking unique fields.
        """
        processor = middleware.DjangoGroupAccessMiddleware()
        request = self.MockRequest()
        request.user = self.user
        processor.process_request(request)

        # assert the test data is as expected
        self.assertEqual(set([]), set(UniqueModel.objects.filter()))

        data = {'name': 'my name'}
        form = UniqueForm(data)
        self.assertFalse(
            form.is_valid(),
            'Form should not be valid if all records in the db '
            'were used to check uniqueness.')


class SubqueryTest(SyncingTestCase):
    def test_querysets_used_in_subqueries(self):
        """
        An access restricted queryset used inside another queryset
        should have the access controls applied.
        """
        user = User.objects.create(username='user')
        group = self.group_model.objects.create(name='group')
        project = Project.objects.create(name='project')
        project.access_groups.add(group)
        subqueryset = Project.objects.all().accessible_by_user(user)

        # there should be no access groups associated with the list
        # of projects in the subqueryset
        groups = self.group_model.objects.filter(project__in=subqueryset)
        self.assertEqual(set(groups), set([]))


class InitialQuerysetTest(SyncingTestCase):
    def test_queryset_is_used_for_filtering(self):
        """
        The queryset supplied when registering a model is used
        to filter the records available to that model.
        """
        PreFilteredModel.objects.create(name='hidden')
        expected = PreFilteredModel.objects.create(name='visible')
        self.assertEqual(set([expected]), set(PreFilteredModel.objects.all()))

    def test_queryset_is_used_for_related_managers(self):
        """
        The querset supplied when registering a model is used to
        filter the records when the model is accessed through a
        related set.
        """
        parent = PreFilteredParent.objects.create(name='parent')
        PreFilteredModel.objects.create(name='hidden', parent=parent)
        expected = PreFilteredModel.objects.create(
            name='visible', parent=parent)
        self.assertEqual(
            set([expected]), set(parent.prefilteredmodel_set.all()))


class ModelWithNoIdTest(SyncingTestCase):

    def setUp(self):
        self.group = self.group_model.objects.create(name='group')
        self.user = _create_user()
        add_user(self.group, self.user)

    def test_query_for_model_with_no_id(self):
        """
        We can query for models that use a different field for their primary
        key.
        """
        parent = ParentWithNoId.objects.create(name='testing')
        parent.access_groups.add(self.group)
        child = ChildWithNoId.objects.create(name='test child', parent=parent)
        self.assertEqual([child],
            list(ChildWithNoId.objects.accessible_by_user(self.user)))


counter = itertools.count()


def _create_user():
    random_string = 'asdfg%d' % counter.next()
    user = User.objects.create(
        username=random_string, email='%s@example.com' % random_string)
    return user

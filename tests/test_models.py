from django.test import TestCase
from django.contrib.auth.models import User
from registrondeparts.models import Department


class ModelsTestCase(TestCase):
    def create_profile_test(self):
        # Creating a fake user
        """RUNNING TEST"""
        new_user = User.objects.create_user(username='TEST', email='TEST@TESTE.COM', password='TEST@2000')
        new_user.save()

        # Creting fake department and full name
        new_user.profile.department = 'IT'
        new_user.profile.full_name = 'JOHN WICK'
        new_user.save()

        # Get fake info for comparison
        record = User.objects.get(pk=1)

        self.assertEqual(record, new_user) # Tests OK!

    def delete_user_test(self):
        new_user = User.objects.create_user(username='TEST', email='TEST@TESTE.COM', password='TEST@2000')
        new_user.save()

        # Creting fake department and full name
        new_user.profile.department = 'IT'
        new_user.profile.full_name = 'JOHN WICK'
        new_user.save()

        user_delete = User.objects.get(pk=1)
        delet_test = user_delete.delete()

        self.assertTrue(delet_test)

    def update_profile_test(self):
        # Test the update function
        """RUNNING TEST"""
        new_user = User.objects.create_user(username='TEST', email='TEST@TEST.COM', password='TEST@2000')
        new_user.save()
        new_user.profile.department = 'IT'
        new_user.profile.full_name = 'JOHN WICK'
        new_user.save()

        new_email = 'UPDATE_TEST@TEST.COM'
        new_full_name = 'UPDATE JOHN WICK'
        new_department = 'FINANCE'

        if new_email:
            new_user.email = new_email
            new_user.save()

        if new_full_name:
            new_user.profile.full_name = new_full_name
            new_user.save()

        if new_department:
            new_user.profile.department = new_department
            new_user.save()

        update_record = User.objects.get(pk=1)

        self.assertEqual(new_user, update_record)

    def create_department_test(self):
        depart_name = 'DEPARTMENT TEST'
        Department.objects.get_or_create(department_name=depart_name)

        record = Department.objects.get(pk=1)

        self.assertEqual(depart_name, record)
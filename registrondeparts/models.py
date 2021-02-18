from __future__ import unicode_literals

from django.db import models


# Using a model to create new departments
class Department(models.Model):

    department_name = models.CharField(max_length=80)

    def __str__(self):
        return self.department_name


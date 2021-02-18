from __future__ import unicode_literals

from django.db import models
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.contrib.auth.models import User


class Profile(models.Model):
    # Here we create a OneToOneField, to use django model to create new users
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # Here we create new field (project requirement)
    department = models.CharField(max_length=80)
    full_name = models.CharField(max_length=150)

    def __str__(self):
        return self.full_name


# A couple of signals to save the users on the database
@receiver(post_save, sender=User)
def update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def salvar_perfil(sender, instance, created, **kwargs):
    try:
        instance.profile.save()
    except Exception:
        pass

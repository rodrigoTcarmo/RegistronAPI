# Generated by Django 3.1.6 on 2021-02-13 21:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registronapi', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='username',
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='department',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='user',
            name='full_name',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='user',
            name='password',
            field=models.CharField(max_length=100),
        ),
    ]
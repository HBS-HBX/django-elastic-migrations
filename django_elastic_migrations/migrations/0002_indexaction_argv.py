# -*- coding: utf-8 -*-
# Generated by Django 1.9.8 on 2018-05-31 10:09
from __future__ import print_function
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('django_elastic_migrations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='indexaction',
            name='argv',
            field=models.CharField(blank=True, max_length=1000),
        ),
    ]

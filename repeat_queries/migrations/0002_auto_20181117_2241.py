# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2018-11-17 22:41
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('repeat_queries', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='sqlquery',
            old_name='time_taken',
            new_name='duration',
        ),
        migrations.RenameField(
            model_name='sqlquery',
            old_name='end_time',
            new_name='stop_time',
        ),
    ]

# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2018-11-17 17:21
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Request',
            fields=[
                ('id', models.CharField(default=uuid.uuid4, max_length=36, primary_key=True, serialize=False)),
                ('path', models.CharField(db_index=True, max_length=190)),
                ('query_params', models.TextField(blank=True, default='')),
                ('raw_body', models.TextField(blank=True, default='')),
                ('body', models.TextField(blank=True, default='')),
                ('method', models.CharField(max_length=10)),
                ('start_time', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('view_name', models.CharField(blank=True, db_index=True, default='', max_length=190, null=True)),
                ('end_time', models.DateTimeField(blank=True, null=True)),
                ('time_taken', models.FloatField(blank=True, null=True)),
                ('encoded_headers', models.TextField(blank=True, default='')),
                ('meta_time', models.FloatField(blank=True, null=True)),
                ('meta_num_queries', models.IntegerField(blank=True, null=True)),
                ('meta_time_spent_queries', models.FloatField(blank=True, null=True)),
                ('pyprofile', models.TextField(blank=True, default='')),
                ('num_sql_queries', models.IntegerField(default=0)),
            ],
        ),
        migrations.CreateModel(
            name='SQLQuery',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('query', models.TextField()),
                ('start_time', models.DateTimeField(blank=True, default=django.utils.timezone.now, null=True)),
                ('end_time', models.DateTimeField(blank=True, null=True)),
                ('time_taken', models.FloatField(blank=True, null=True)),
                ('traceback', models.TextField()),
                ('request', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='queries', to='repeat_queries.Request')),
            ],
        ),
    ]

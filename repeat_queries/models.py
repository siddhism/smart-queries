# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from django.db import transaction
from collections import Counter
import json
import base64
import random
import re

from django.core.files.storage import get_storage_class
from django.db.models import (
    DateTimeField, TextField, CharField, ForeignKey, IntegerField,
    BooleanField, F, ManyToManyField, OneToOneField, FloatField,
    FileField
)
from django.utils import timezone
from uuid import uuid4
import sqlparse
from django.utils.safestring import mark_safe


# Seperated out so can use in tests w/o models
def _time_taken(start_time, end_time):
    d = end_time - start_time
    return d.seconds * 1000 + d.microseconds / 1000


def time_taken(self):
    return _time_taken(self.start_time, self.stop_time)


class CaseInsensitiveDictionary(dict):
    def __getitem__(self, key):
        return super(CaseInsensitiveDictionary, self).__getitem__(key.lower())

    def __setitem__(self, key, value):
        super(CaseInsensitiveDictionary, self).__setitem__(key.lower(), value)

    def update(self, other=None, **kwargs):
        for k, v in other.items():
            self[k] = v
        for k, v in kwargs.items():
            self[k] = v

    def __init__(self, d):
        super(CaseInsensitiveDictionary, self).__init__()
        for k, v in d.items():
            self[k] = v


# Create your models here.
class Request(models.Model):
    id = models.CharField(max_length=36, default=uuid4, primary_key=True)
    path = models.CharField(max_length=190, db_index=True)
    query_params = models.TextField(blank=True, default='')
    raw_body = models.TextField(blank=True, default='')
    body = models.TextField(blank=True, default='')
    method = models.CharField(max_length=10)
    start_time = models.DateTimeField(default=timezone.now, db_index=True)
    view_name = models.CharField(
        max_length=190, db_index=True, blank=True,
        default='', null=True
    )
    end_time = models.DateTimeField(null=True, blank=True)
    time_taken = models.FloatField(blank=True, null=True)
    encoded_headers = models.TextField(blank=True, default='')  # stores json
    meta_time = models.FloatField(null=True, blank=True)
    meta_num_queries = models.IntegerField(null=True, blank=True)
    meta_time_spent_queries = models.FloatField(null=True, blank=True)
    pyprofile = models.TextField(blank=True, default='')

    def __str__(self):
        return self.path

    def _shorten(self, string):
        return '%s...%s' % (string[:94], string[len(string) - 93:])

    @property
    def total_meta_time(self):
        return (self.meta_time or 0) + (self.meta_time_spent_queries or 0)

    @property
    def profile_table(self):
        for n, columns in enumerate(parse_profile(self.pyprofile)):
            location = columns[-1]
            if n and '{' not in location and '<' not in location:
                r = re.compile('(?P<src>.*\.py)\:(?P<num>[0-9]+).*')
                m = r.search(location)
                group = m.groupdict()
                src = group['src']
                num = group['num']
                name = 'c%d' % n
                fmt = '<a name={name} href="?pos={n}&file_path={src}&line_num={num}#{name}">{location}</a>'
                rep = fmt.format(**dict(group, **locals()))
                yield columns[:-1] + [mark_safe(rep)]
            else:
                yield columns

    # defined in atomic transaction within SQLQuery save()/delete() as well
    # as in bulk_create of SQLQueryManager
    # TODO: This is probably a bad way to do this, .count() will prob do?
    num_sql_queries = IntegerField(default=0)  # TODO replace with count()

    @property
    def time_spent_on_sql_queries(self):
        """
        TODO: Perhaps there is a nicer way to do this with Django aggregates?
        My initial thought was to perform:
        SQLQuery.objects.filter.aggregate(Sum(F('end_time')) - Sum(F('start_time')))
        However this feature isnt available yet, however there has been talk
        for use of F objects within aggregates for four years
        here: https://code.djangoproject.com/ticket/14030. It looks
        like this will go in soon at which point this should be changed.
        """
        return sum(x.time_taken for x in SQLQuery.objects.filter(request=self))

    @property
    def headers(self):
        if self.encoded_headers:
            raw = json.loads(self.encoded_headers)
        else:
            raw = {}

        return CaseInsensitiveDictionary(raw)

    @property
    def content_type(self):
        return self.headers.get('content-type', None)

    def save(self, *args, **kwargs):
        # sometimes django requests return the body as 'None'
        if self.raw_body is None:
            self.raw_body = ''

        if self.body is None:
            self.body = ''

        if self.end_time and self.start_time:
            interval = self.end_time - self.start_time
            self.time_taken = interval.total_seconds() * 1000

        # We can't save if either path or view_name exceed 190 characters
        if self.path and len(self.path) > 190:
            self.path = self._shorten(self.path)

        if self.view_name and len(self.view_name) > 190:
            self.view_name = self._shorten(self.view_name)

        super(Request, self).save(*args, **kwargs)
        # Request.garbage_collect(force=False)


class SQLQueryManager(models.Manager):
    def bulk_create(self, *args, **kwargs):
        """ensure that num_sql_queries remains consistent. Bulk create does not call
        the model save() method and hence we must add this logic here too"""
        if len(args):
            objs = args[0]
        else:
            objs = kwargs.get('objs')

        with transaction.atomic():
            request_counter = Counter([x.request_id for x in objs])
            requests = Request.objects.filter(pk__in=request_counter.keys())
            # TODO: Not that there is ever more than one request (but there could be eventually)
            # but perhaps there is a cleaner way of apply the increment from the counter without iterating
            # and saving individually? e.g. bulk update but with diff. increments. Couldn't come up with this
            # off hand.
            for r in requests:
                r.num_sql_queries = F('num_sql_queries') + request_counter[r.pk]
                r.save()
            return super(SQLQueryManager, self).bulk_create(*args, **kwargs)


class SQLQuery(models.Model):
    query = TextField()
    start_time = DateTimeField(null=True, blank=True, default=timezone.now)
    stop_time = DateTimeField(null=True, blank=True)
    duration = FloatField(blank=True, null=True)
    request = ForeignKey(
        Request, related_name='queries', null=True,
        blank=True, db_index=True, on_delete=models.CASCADE,
    )
    traceback = TextField()
    duplicate_count = IntegerField(blank=True, null=True)
    objects = SQLQueryManager()

    # TODO docstring
    @property
    def traceback_ln_only(self):
        return '\n'.join(self.traceback.split('\n')[::2])

    @property
    def formatted_query(self):
        return sqlparse.format(self.query, reindent=True, keyword_case='upper')

    # TODO: Surely a better way to handle this? May return false positives
    @property
    def num_joins(self):
        return self.query.lower().count('join ')

    @property
    def tables_involved(self):
        """
        A really another rudimentary way to work out tables involved in a
        query.
        TODO: Can probably parse the SQL using sqlparse etc and pull out table
        info that way?
        """
        components = [x.strip() for x in self.query.split()]
        tables = []

        for idx, component in enumerate(components):
            # TODO: If django uses aliases on column names they will be falsely
            # identified as tables...
            if component.lower() == 'from' or component.lower() == 'join' or component.lower() == 'as':
                try:
                    _next = components[idx + 1]
                    if not _next.startswith('('):  # Subquery
                        stripped = _next.strip().strip(',')

                        if stripped:
                            tables.append(stripped)
                except IndexError:  # Reach the end
                    pass
        return tables

    @transaction.atomic()
    def save(self, *args, **kwargs):

        if self.stop_time and self.start_time:
            interval = self.stop_time - self.start_time
            self.time_taken = interval.total_seconds() * 1000

        if not self.pk:
            if self.request:
                self.request.num_sql_queries += 1
                self.request.save(update_fields=['num_sql_queries'])

        super(SQLQuery, self).save(*args, **kwargs)

    @transaction.atomic()
    def delete(self, *args, **kwargs):
        self.request.num_sql_queries -= 1
        self.request.save()
        super(SQLQuery, self).delete(*args, **kwargs)

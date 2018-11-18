# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin
from repeat_queries.models import SQLQuery, Request


class SQLQueryAdmin(admin.ModelAdmin):
    list_display = ['query', 'similar_count', 'duplicate_count', 'duration', 'request']
    list_filter = ['request']
    pass


class RequestAdmin(admin.ModelAdmin):
    pass


admin.site.register(Request, RequestAdmin)
admin.site.register(SQLQuery, SQLQueryAdmin)

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin
from django.core.urlresolvers import reverse
from repeat_queries.models import SQLQuery, Request


class SQLQueryAdmin(admin.ModelAdmin):
    list_display = ['query', 'similar_count', 'duplicate_count', 'duration', 'request']
    list_filter = ['request']
    pass


class RequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'path', 'time_taken', 'view_report']

    def view_report(self, obj):
        tag = '<a href="%s">%s</a>'%(reverse('request_sql', kwargs={'request_id': obj.id}), 'View Report of Request')
        return tag

    view_report.allow_tags = True


admin.site.register(Request, RequestAdmin)
admin.site.register(SQLQuery, SQLQueryAdmin)

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.shortcuts import render

from django.views.generic import View
from repeat_queries.models import Request, SQLQuery


class SQLView(View):

    def get(self, request, *_, **kwargs):
        request_id = kwargs.get('request_id')
        context = {
            'request': request,
        }
        if request_id:
            rp_request = Request.objects.get(id=request_id)
            query_set = SQLQuery.objects.filter(request=rp_request).order_by('-start_time')
            for q in query_set:
                q.start_time_relative = q.start_time - rp_request.start_time
            context['rp_request'] = rp_request
            context['queries'] = query_set
        if not request_id:
            raise KeyError('no profile_id or request_id')
        return render(request, 'sql.html', context)

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.utils import timezone
from django.views.generic.list import ListView
from django.http import HttpResponse

from blog.models import Post


class PostListView(ListView):

    model = Post

    def get_context_data(self, **kwargs):
        context = super(PostListView, self).get_context_data(**kwargs)
        context['qs'] = Post.objects.all()
        context['now'] = timezone.now()
        return context

    def get_queryset(self, **kwargs):
        qs = super(PostListView, self).get_queryset(**kwargs)
        return qs


def post_list(request, *args, **kwargs):
    object_list = Post.objects.all()
    return HttpResponse(object_list)

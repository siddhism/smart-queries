# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.utils import timezone
from django.views.generic.list import ListView

from blog.models import Post


class PostListView(ListView):

    model = Post
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super(PostListView, self).get_context_data(**kwargs)
        context['qs'] = Post.objects.all()
        context['now'] = timezone.now()
        return context


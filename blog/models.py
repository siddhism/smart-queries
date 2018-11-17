# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models


class Author(models.Model):
    """
    Author model
    """
    name = models.CharField(max_length=100)
    short_description = models.CharField(max_length=400)
    long_description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Author'


class Post(models.Model):
    """
    Description: Model Description
    """
    title = models.CharField(max_length=1000)
    description = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(Author)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'post'

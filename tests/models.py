# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from django.utils.encoding import python_2_unicode_compatible


@python_2_unicode_compatible
class Movie(models.Model):
    title = models.CharField(max_length=500)
    year = models.IntegerField()
    runtime = models.IntegerField()
    genre = models.CharField(max_length=500)
    director = models.CharField(max_length=500)
    writer = models.CharField(max_length=500)
    actors = models.TextField()
    plot = models.TextField()
    production = models.CharField(max_length=500)
    last_modified = models.DateTimeField(auto_now=True, null=True)

    def __str__(self):
        return "<Movie id='{id}' title='{title}>".format(id=self.pk, title=self.title)

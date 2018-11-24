# -*- coding: utf-8 -*-
from __future__ import (absolute_import, division, print_function, unicode_literals)

from django.db import models


class Movie(models.Model):
    title = models.CharField(max_length=500, unique=True)
    year = models.IntegerField()
    runtime = models.IntegerField()
    genre = models.CharField(max_length=500)
    director = models.CharField(max_length=500)
    writer = models.CharField(max_length=500)
    actors = models.TextField()
    plot = models.TextField()
    production = models.CharField(max_length=500)
    last_modified = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        app_label = 'tests'

    def __str__(self):
        return "<Movie id='{id}' title='{title}>".format(id=self.pk, title=self.title)

    @classmethod
    def save_movie_from_omdb_query(cls, query):
        data = query.get_data()
        if not data:
            raise ValueError("There was no data returned from OMDB query {}".format(str(query)))

        title = data.get('title', '')[:500]
        if not title:
            raise ValueError("The title field is required; did not receive any title. Data returned was ")

        year = data['year']
        runtime = data['runtime']
        movie, created = Movie.objects.get_or_create(title=title, year=year, runtime=runtime)
        movie_kwargs = {
            'genre': data['genre'][:500],
            'director': data['director'][:500],
            'writer': data['writer'][:500],
            'actors': data['actors'],
            'plot': data['plot'],
            'production': data['production'][:500],
        }
        for attr, val in movie_kwargs.items():
            setattr(movie, attr, val)
        movie.save()

        return movie, created

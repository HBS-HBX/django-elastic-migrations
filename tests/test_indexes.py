#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for the `django-elastic-migrations` models module.
"""

from __future__ import (absolute_import, division, print_function, unicode_literals)

from elasticsearch import TransportError
from elasticsearch_dsl.exceptions import IllegalOperation

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.utils.test_utils import DEMTestCase
from tests.es_config import ES_CLIENT
from tests.search import MovieSearchIndex, MovieSearchDoc
from tests.models import Movie


class TestMovie(DEMTestCase):
    """
    Tests of the Index model.
    """

    fixtures = ['tests/tests_initial.json']

    def test_update_index(self):
        num_docs = MovieSearchIndex.get_num_docs()
        self.assertEqual(num_docs, 0)

        base_name = MovieSearchIndex.get_base_name()
        DEMIndexManager.update_index(base_name)

        num_docs = MovieSearchIndex.get_num_docs()
        self.assertEqual(num_docs, 2)

        movie_title = "Melancholia"
        movie = Movie.objects.get(title=movie_title)
        results = MovieSearchDoc.get_search(movie_title).execute()
        first_result = results[0]
        self.assertEqual(str(movie.id), first_result.meta.id)

    def test_save_index_elasticsearch_dsl_lt_62(self):
        """
        Added for #9 type error DEMIndex save
        Tests that DEMIndex.save(using=using) works in 6.1 and 6.2 versions of DEM
        """
        try:
            # if elasticsearch_dsl <= 6.2, using is not a parameter but shouldn't throw exception
            MovieSearchIndex.save(using=ES_CLIENT)
        except (TransportError, IllegalOperation):
            # the indexes already exist
            pass

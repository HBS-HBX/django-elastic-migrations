#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for the `django-elastic-migrations` indexes module.
"""

from __future__ import (absolute_import, division, print_function, unicode_literals)

from elasticsearch import TransportError
from elasticsearch_dsl.exceptions import IllegalOperation

from django_elastic_migrations.utils.test_utils import DEMTestCase
from tests.es_config import ES_CLIENT
from tests.search import MovieSearchIndex


class TestDEMIndex(DEMTestCase):
    """
    Tests of the Index model.
    """

    fixtures = ['tests/tests_initial.json']

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

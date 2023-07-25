#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for the `django-elastic-migrations` indexes module.
"""

from __future__ import (absolute_import, division, print_function, unicode_literals)

import unittest
from unittest import skip
from unittest.mock import patch

from django.conf import settings
from elasticsearch import TransportError
from elasticsearch_dsl.exceptions import IllegalOperation
from django_elastic_migrations import DEMIndex
from django_elastic_migrations.indexes import DEMDocument, DEMIndexMeta, DEMIndexManager
from django_elastic_migrations.utils.test_utils import DEMTestCaseMixin
from django.test import TestCase
from tests.es_config import ES_CLIENT
from tests.search import MovieSearchIndex, GenericDocument


class TestDEMIndex(DEMTestCaseMixin, TestCase):
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


class TestDEMIndexNoFixtures(DEMTestCaseMixin, TestCase):
    """
    Tests of the Index model that don't require fixtures.
    """

    def tearDown(self):
        DEMIndexManager.test_pre_teardown()
        super(DEMTestCaseMixin, self).tearDown()
        doc_counts = DEMIndexManager.list_es_doc_counts()
        self.assertEqual(len(doc_counts), 0)

    @skip
    def test_index_exists_and_index_create(self):
        """
        Tests that the index exists
        adapted from elaticserach-dsl-py example
        https://github.com/elastic/elasticsearch-dsl-py/blob/v7.4.1/examples/completion.py
        Example ``Document`` with completion suggester.

        In the ``Person`` class we index the person's name to allow auto completing in
        any order ("first last", "middle last first", ...). For the weight we use a
        value from the ``popularity`` field which is a long.

        To make the suggestions work in different languages we added a custom analyzer
        that does ascii folding.
        """
        from itertools import permutations

        from elasticsearch_dsl import connections, Document, Completion, Text, Long, \
            Keyword, analyzer, token_filter

        # custom analyzer for names
        ascii_fold = analyzer(
            'ascii_fold',
            # we don't want to split O'Brian or Toulouse-Lautrec
            tokenizer='whitespace',
            filter=[
                'lowercase',
                token_filter('ascii_fold', 'asciifolding')
            ]
        )

        with patch.object(DEMIndexMeta, 'construct_index', side_effect=DEMIndexMeta.construct_index) as mock_dem_construct_index:

            class Person(DEMDocument):
                name = Text(fields={'keyword': Keyword()})
                popularity = Long()

                # completion field with a custom analyzer
                suggest = Completion(analyzer=ascii_fold)

                def clean(self):
                    """
                    Automatically construct the suggestion input and weight by taking all
                    possible permutation of Person's name as ``input`` and taking their
                    popularity as ``weight``.
                    """
                    self.suggest = {
                        'input': [' '.join(p) for p in permutations(self.name.split())],
                        'weight': self.popularity
                    }

                class Index:
                    name = 'person-suggest'
                    settings = {
                        'number_of_shards': 1,
                        'number_of_replicas': 0
                    }

            mock_dem_construct_index.assert_called_once()

        # initiate the default connection to elasticsearch
        connections.create_connection()

        self.assertIsNotNone(Person.get_dem_index())
        self.assertFalse(Person.get_dem_index().exists())

        # create the empty index
        Person.init()

        self.assertTrue(Person.get_dem_index().exists())
        self.assertEqual(Person.get_dem_index().get_es_index_doc_count(), 0)

        HENRI = 'Henri de Toulouse-Lautrec'
        JARA = 'Jára Cimrman'
        popularities = {
            HENRI: 42,
            JARA: 124,
        }

        # index some sample data
        for id, (name, popularity) in enumerate([
            (HENRI, popularities[HENRI]),
            (JARA, popularities[JARA]),
        ]):
            Person(_id=id, name=name, popularity=popularity).save()

        # refresh index manually to make changes live
        Person._index.refresh()

        self.assertEqual(Person.get_dem_index().get_es_index_doc_count(), 2)

        expected_suggestion = {
            'já': JARA,
            'Jara Cimr': JARA,
            'tou': HENRI,
            'de hen': HENRI,
        }

        # run some suggestions
        for entered_text, expected_suggestion in expected_suggestion.items():
            s = Person.search()
            s = s.suggest('auto_complete', entered_text, completion={'field': 'suggest'})
            response = s.execute()

            # print out all the options we got
            for option in response.suggest.auto_complete[0].options:
                self.assertEqual(option._source.name, expected_suggestion)
                self.assertEqual(option._score, popularities[expected_suggestion])
                print('%10s: %25s (%d)' % (entered_text, option._source.name, option._score))

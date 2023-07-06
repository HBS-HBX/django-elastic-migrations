from __future__ import (absolute_import, division, print_function, unicode_literals)

import logging
import re
from datetime import datetime, timedelta
from random import random, sample
from typing import NamedTuple, List, Iterable, Tuple
from unittest import skip
from unittest.mock import patch

from django.contrib.humanize.templatetags.humanize import ordinal
from django.core.management import call_command
from django.template.defaultfilters import pluralize
from django.test import TestCase, TransactionTestCase
from elasticsearch import RequestError
from texttable import Texttable

from django_elastic_migrations import DEMIndexManager, es_client
from django_elastic_migrations.indexes import DEMIndex
from django_elastic_migrations.management.commands.es_list import EsListRow
from django_elastic_migrations.models import Index, IndexVersion, IndexAction
from django_elastic_migrations.utils.test_utils import DEMTestCaseMixin
from tests.es_config import ES_CLIENT
from tests.models import Movie
from tests.search import MovieSearchIndex, MovieSearchDoc, get_new_search_index, alternate_textfield, DefaultNewSearchDocTypeMixin

log = logging.getLogger(__file__)


def days_ago(d):
    return datetime.now() - timedelta(days=d)


"""
Data model for making a row of the table for ./manage.py es_list --es-only
"""
EsOnlyRow = NamedTuple('EsOnlyRow', [('name', str), ('count', int)])


def get_es_list_row(index_version: IndexVersion, created: int = 1, active: int = 1, docs: int = 0, tag: str = "") -> EsListRow:
    return EsListRow(index_version.index.name, index_version.name, created, active, docs, tag)


def get_blank_es_list_row(index_base_name: str) -> EsListRow:
    return EsListRow(index_base_name, "", created=0, active=0, docs=0, tag="Current (not created)")


def get_es_list_table(rows: Iterable[EsListRow]) -> str:
    """
    Returns the expected table for ./manage.py es_list
    """
    table = Texttable(max_width=85)
    table.header(["Index Base Name", "Index Version Name", "Created", "Active", "Docs", "Tag"])
    table.set_cols_width([20, 35, 7, 6, 5, 9])
    for row in rows:
        table.add_row(row)
    return table.draw()


def get_es_only_row(name: str, count: int = 0) -> EsOnlyRow:
    return EsOnlyRow(name, count)


def get_es_only_table(rows: List[EsOnlyRow]) -> str:
    """
    Returns the expected table for ./manage.py es_list --es-only
    """
    table = Texttable(max_width=85)
    table.header(["Name", "Count"])
    for row in rows:
        table.add_row(row)
    return table.draw()


# noinspection PyUnresolvedReferences
class CommonDEMTestUtilsMixin(object):

    def check_basic_setup_and_get_models(self, index_name='movies', expected_num_versions=1, pre_message="At test setup") -> \
            Tuple[Index, IndexVersion, DEMIndex]:
        dem_index = DEMIndexManager.get_dem_index(index_name)

        index_model = dem_index.get_index_model()

        version_model = dem_index.get_version_model()
        expected_msg = "The {} index should have an active version.".format(index_name)
        self.assertIsNotNone(version_model, expected_msg)

        self.check_num_available_versions(index_model, pre_message, expected_num_versions)

        expected_msg = "The {} index should already exist in elasticsearch.".format(version_model.name)
        self.assertTrue(version_model.exists_in_es(), expected_msg)

        return index_model, version_model, dem_index

    def check_num_available_versions(self, index_model, pre_message, expected_num_available):
        """
        :param index_model: Index model to check for number of available messages
        :type index_model: django_elastic_migrations.models.Index
        :param pre_message: Message to insert at beginning of expected message if assertion fails
        :type pre_message: basestring
        :param expected_num_available: The number of available IndexVersions expected of the Index model
        :type expected_num_available: int
        """
        available_versions = index_model.get_available_versions()
        num_available = available_versions.count()
        expected_msg = (
            "{pre_message} "
            "the {index_name} index should have {expected_num} index versions available, "
            "but instead, there {was_were} {actual_num}".format(
                pre_message=pre_message,
                index_name=index_model.name,
                was_were="were" if num_available > 1 else "was",
                expected_num=expected_num_available,
                actual_num=num_available
            )
        )
        self.assertEqual(available_versions.count(), expected_num_available, expected_msg)
        return available_versions

    def check_last_index_actions(
            self, index_model, pre_message, num_to_get=1,
            expected_status=IndexAction.STATUS_COMPLETE, expected_actions=None):
        """
        Retrieve the last n IndexActions for the given Index
        optionally assert the status and action for the retrieved IndexActions
        :param index_model: the Index model to retrieve actions for
        :type index_model: django_elastic_migrations.models.Index
        :param pre_message: description of the action that just was executed
        :type pre_message: str
        :param num_to_get: the number of most recent actions to retrieve
        :type num_to_get: int
        :param expected_status: the expected status of the IndexAction to assert; by default STATUS_COMPLETE
        :type expected_status: django_elastic_migrations.models.IndexAction.STATUSES_ALL
        :param expected_actions: list of action types to assert, in order from oldest to newest
        :type expected_actions:  [django_elastic_migrations.models.IndexAction.ACTIONS_ALL]
        :return: IndexActions for the Index
        :rtype: [django_elastic_migrations.models.IndexAction]
        """
        index_actions = index_model.indexaction_set.all().order_by('-pk')[:num_to_get]
        num_available = index_actions.count()
        expected_msg = (
            "{pre_message} "
            "the {index_name} index should have had {expected_num} {index_action_plural} available, "
            "but instead, there {was_were} {actual_num}".format(
                pre_message=pre_message,
                index_name=index_model.name,
                expected_num=num_to_get,
                index_action_plural="IndexAction{}".format(pluralize(num_to_get)),
                was_were=pluralize(num_available, "was,were"),
                actual_num=num_available
            )
        )
        self.assertEqual(index_actions.count(), num_to_get, expected_msg)

        # we ordered them in reverse cron to get most recent actions; put them back in cron order
        index_actions = list(index_actions)
        index_actions.reverse()

        if expected_status or expected_actions:
            for num, index_action in enumerate(index_actions, 1):
                expected_msg = (
                    "{pre_message} "
                    "the {index_name}'s {ordinal} IndexAction was expected "
                    "to have status `{expected_status}`, "
                    "but instead, it had status `{actual_status}`. ".format(
                        pre_message=pre_message,
                        index_name=index_model.name,
                        ordinal=ordinal(num),
                        expected_status=expected_status,
                        actual_status=index_action.status,
                    )
                )
                self.assertEqual(index_action.status, expected_status, expected_msg)

                if expected_actions:
                    expected_action = expected_actions[num - 1]
                    expected_msg = (
                        "{pre_message} "
                        "the {index_name}'s {ordinal} IndexAction was expected "
                        "to be {expected_action}, \n"
                        "but instead, it was {actual_action}. ".format(
                            pre_message=pre_message,
                            index_name=index_model.name,
                            ordinal=ordinal(num),
                            expected_action=expected_action,
                            actual_action=index_action.action,
                        )
                    )
                    self.assertEqual(index_action.action, expected_action, expected_msg)
        return index_actions

    @patch('django_elastic_migrations.management.commands.es_list.log')
    def check_es_list(self, mock_logger, expected_table, scenario_message, es_only=False, args=None):
        if args is None:
            args = []
        call_command('es_list', es_only=es_only, *args)
        actual_table = mock_logger.info.mock_calls[1][1][0]
        max_diff_backup = self.maxDiff
        self.maxDiff = None
        self.assertEqual(expected_table, actual_table, "\n%s" % scenario_message)
        self.maxDiff = max_diff_backup


class TestEsUpdateManagementCommand(CommonDEMTestUtilsMixin, DEMTestCaseMixin, TestCase):
    """
    Tests ./manage.py es_update
    """

    fixtures = ['tests/tests_initial.json']

    def test_basic_invocation(self):
        index_model, _, _ = self.check_basic_setup_and_get_models()

        # ensure that the active version is one of those queried with MovieSearchDoc.search()
        self.assertIn(index_model.active_version.name, MovieSearchDoc.search()._index)
        # ensure that the active version is the only one queried in MovieSearchDoc.search()
        self.assertEqual(len(MovieSearchDoc.search()._index), 1)

        num_docs = MovieSearchIndex.get_num_docs()
        self.assertEqual(num_docs, 0)

        call_command('es_update', MovieSearchIndex.get_base_name())

        num_docs = MovieSearchIndex.get_num_docs()
        self.assertEqual(num_docs, 2)

        movie_title = "Melancholia"
        movie = Movie.objects.get(title=movie_title)
        results = MovieSearchDoc.get_search(movie_title).execute()
        first_result = results[0]
        self.assertEqual(str(movie.id), first_result.meta.id)

    def test_newer_flag(self):
        """
        Test that when two versions of the "movies" index are available,
        and the older one is activated, `./manage.py es_update movies --newer`
        indexes into the newer, unactivated version
        """
        index_model, version_model, dem_index = self.check_basic_setup_and_get_models()

        # create two newer versions of the movies index
        call_command(*"es_create movies --force".split())
        call_command(*"es_create movies --force".split())
        avail_versions = self.check_num_available_versions(
            index_model, "After 2x './manage.py es_create movies --force',", 3)

        command = "es_update movies --newer"
        call_command(*command.split())
        after_phrase = "After `{}`,".format(command)
        last_actions = self.check_last_index_actions(
            index_model, after_phrase, 5,
            expected_actions=[
                # the parent update index action
                IndexAction.ACTION_UPDATE_INDEX,

                # 1st newer index update index action
                IndexAction.ACTION_UPDATE_INDEX,
                IndexAction.ACTION_PARTIAL_UPDATE_INDEX,

                # 2nd newer index update index actions
                IndexAction.ACTION_UPDATE_INDEX,
                IndexAction.ACTION_PARTIAL_UPDATE_INDEX,
            ]
        )

        first_action = last_actions[0]
        first_action_version = first_action.index_version
        self.assertIsNone(first_action_version,
                          "{} expected parent UpdateIndexAction to be None, "
                          "but was {}".format(after_phrase, str(first_action_version)))
        self.assertEqual(first_action.docs_affected, 4,
                         "{} expected the parent UpdateIndexAction to have "
                         "4 docs affected, but was {}".format(after_phrase, first_action.docs_affected))

        actual_num_docs = dem_index.get_num_docs()
        self.assertEqual(actual_num_docs, 0,
                         "{after_phrase} "
                         "The original IndexVersion {index_name} was expected "
                         "to have 0 docs, instead, it had {actual_num}".format(
                             after_phrase=after_phrase,
                             index_name=version_model.name,
                             actual_num=actual_num_docs
                         ))

        for i in [1, 3]:
            action = last_actions[i]
            self.assertEqual(action.docs_affected, 2)

            new_version_model = last_actions[i].index_version
            new_dem_index = DEMIndexManager.get_dem_index(
                new_version_model.name, exact_mode=True)
            actual_num_docs = new_dem_index.get_num_docs()
            self.assertEqual(actual_num_docs, 2,
                             "{after_phrase} "
                             "{index_name} was expected to have "
                             "2 docs, instead, it had {actual_num}".format(
                                 after_phrase=after_phrase,
                                 index_name=new_version_model,
                                 actual_num=actual_num_docs
                             ))

    def test_start_flag(self):
        self.check_basic_setup_and_get_models()

        num_docs = MovieSearchIndex.get_num_docs()
        self.assertEqual(num_docs, 0)

        Movie.objects.all().update(last_modified=days_ago(3))
        call_command('es_update', 'movies', '--start={}'.format(days_ago(2).isoformat()))
        num_docs = MovieSearchIndex.get_num_docs()
        # we had last modified set to three days ago, and we only updated last two days,
        # so we should not have any.
        self.assertEqual(num_docs, 0)

        Movie.objects.all().update(last_modified=days_ago(1))
        call_command('es_update', 'movies', '--start={}'.format(days_ago(2).isoformat()))
        num_docs = MovieSearchIndex.get_num_docs()
        # we had last modified set to one days ago, and we only updated last two days,
        # so we should have two
        self.assertEqual(num_docs, 2)


@skip("AttributeError: Can't pickle local object 'threadwrapper.<locals>.wrapper'")
class TestEsUpdateWorkersManagementCommand(CommonDEMTestUtilsMixin, DEMTestCaseMixin, TransactionTestCase):
    """
    Tests `./manage.py es_update --workers`, which uses multiprocessing.
    Uses TransactionTestCase instead of TestCase because TestCase wraps the test in an atomic() block,
    and multiprocessing requires disconnecting the database connection, which is obviously
    not something you can do within an atomic() block.
    """

    fixtures = ['tests/100films.json']

    def test_workers_and_batch_size_flags(self):

        index_model, _, _ = self.check_basic_setup_and_get_models()

        # ensure that the active version is one of those queried with MovieSearchDoc.search()
        self.assertIn(index_model.active_version.name, MovieSearchDoc.search()._index)
        # ensure that the active version is the only one queried in MovieSearchDoc.search()
        self.assertEqual(len(MovieSearchDoc.search()._index), 1)

        num_docs_indexed = MovieSearchIndex.get_num_docs()
        expected_docs = "Expected the movies index to have zero docs to start, instead, it had {}".format(num_docs_indexed)
        self.assertEqual(num_docs_indexed, 0, expected_docs)

        expected_num_movies = 100
        movie_ids = list(Movie.objects.all().values_list('id', flat=True))
        num_movies = len(movie_ids)
        self.assertEqual(num_movies, expected_num_movies)

        es_update_cmd = "es_update movies --workers --batch-size=10 --verbosity=3"
        call_command(*es_update_cmd.split())

        num_docs_indexed = MovieSearchIndex.get_num_docs()
        self.assertEqual(num_docs_indexed, 100)

        # pick 10 movies out at random and search for title, writer, and director
        # assert that our result is one of the choices returned from elasticsearch
        failed_msg = "searched for {title}'s {field} ({value}), but the movie wasn't in search results: '{results}'"
        for movie in Movie.objects.filter(id__in=sample(movie_ids, 10)):
            for field in ['title', 'writer', 'director']:
                value = getattr(movie, field)
                if value:
                    value_without_parens = re.sub(r'\([^)]*\)', '', value)
                    search_val = " ".join(value_without_parens.split()[:2])
                    results = MovieSearchDoc.get_search(search_val).execute()
                    msg = failed_msg.format(field=field, value=search_val, title=movie.title, results=str(results))
                    self.assertIn(str(movie.id), [r.meta.id for r in results], msg)

        after_phrase = "After `{}`,".format(es_update_cmd)
        last_actions = self.check_last_index_actions(
            index_model, after_phrase, num_to_get=11,
            expected_actions=[
                # the parent update index action
                IndexAction.ACTION_UPDATE_INDEX,
                # 10 child update index actions
                IndexAction.ACTION_PARTIAL_UPDATE_INDEX,
                IndexAction.ACTION_PARTIAL_UPDATE_INDEX,
                IndexAction.ACTION_PARTIAL_UPDATE_INDEX,
                IndexAction.ACTION_PARTIAL_UPDATE_INDEX,
                IndexAction.ACTION_PARTIAL_UPDATE_INDEX,
                IndexAction.ACTION_PARTIAL_UPDATE_INDEX,
                IndexAction.ACTION_PARTIAL_UPDATE_INDEX,
                IndexAction.ACTION_PARTIAL_UPDATE_INDEX,
                IndexAction.ACTION_PARTIAL_UPDATE_INDEX,
                IndexAction.ACTION_PARTIAL_UPDATE_INDEX,
            ]
        )

        update_index_action = last_actions[0]
        self.assertEqual(update_index_action.docs_affected, 100)

        # check
        expected_logs = [
            "All child tasks are completed successfully",
            "Completed updating index {}:".format(index_model.active_version.name),
            " # successful updates: 100",
            " # failed updates: 0",
            " # total docs attempted to update: 100",
            " # batch size: 10",
            " # batch avg num docs: 10.0",
            " # batch avg runtime: ",
            " # total runtime: ",
            " # docs per second: ",
            " # workers: ",
            " # verbosity: 3",
        ]
        for expected_log in expected_logs:
            self.assertIn(expected_log, update_index_action.log)

        # the rest of this test verifies items about the child actions - the PartialUpdateIndexActions.

        partial_index_update_actions = last_actions[1:]

        expected_logs = [
            "# batch successful updates: 10",
            "# batch failed updates: 0",
            "# batch docs attempted to update: 10",
            "# batch runtime: ",
            "# parent total docs updated: ",
            "# parent total docs expected: 100",
            "# parent total docs remaining: ",
            "# parent estimated runtime remaining: ",
            "# num workers: "
        ]

        for i, partial_action in enumerate(partial_index_update_actions):
            self.assertEqual(partial_action.docs_affected, 10)
            kwargs = partial_action.get_task_kwargs()
            self.assertEqual(kwargs["start_index"], i * 10)
            self.assertEqual(kwargs["end_index"], min((i + 1) * 10, 100))

            if random() < 0.25:
                # spot check 25% of the records for expected log messages
                for expected_log in expected_logs:
                    self.assertIn(expected_log, partial_action.log)


class TestEsDangerousResetManagementCommand(CommonDEMTestUtilsMixin, DEMTestCaseMixin, TestCase):
    """
    Tests ./manage.py es_dangerous_reset
    """

    fixtures = ['tests/tests_initial.json']

    def test_basic_invocation(self):
        index_model = Index.objects.get(name='movies')

        version_model = MovieSearchIndex.get_version_model()
        self.assertIsNotNone(version_model)
        old_version_id = version_model.id

        available_version_ids = index_model.indexversion_set.all().values_list('id', flat=True)
        expected_msg = "At test setup, the movies index should have one available version, was {}".format(len(available_version_ids))
        self.assertGreaterEqual(len(available_version_ids), 1, expected_msg)

        pre_available_indexaction_ids = index_model.indexaction_set.all().values_list('id', flat=True)
        num_pre_indexactions = len(pre_available_indexaction_ids)

        # create a new version so we have more than one
        call_command('es_create', 'movies', force=True)
        call_command('es_activate', 'movies')

        version_model = MovieSearchIndex.get_version_model()
        self.assertIsNotNone(version_model)
        new_version_id = version_model.id
        self.assertGreater(new_version_id, old_version_id, "After creation, new version id for the movie search index should have been > old id")
        old_version_id = new_version_id

        # update the index to create a related IndexAction - note, this creates two IndexActions, one for partial update and one for parent update
        call_command('es_update', 'movies')

        available_indexaction_ids = index_model.indexaction_set.all().values_list('id', flat=True)
        expected_num_indexactions = num_pre_indexactions + 4
        self.assertEqual(
            len(available_indexaction_ids), expected_num_indexactions,
            "Creating, activating and updating a new movies index version should record {} IndexActions".format(expected_num_indexactions))

        num_docs = MovieSearchIndex.get_num_docs()
        self.assertEqual(num_docs, 2, "After updating the index, it should have had two documents in elasticsearch")

        hidden_index_name = ".hidden-index"
        try:
            es_client.indices.create(hidden_index_name)
        except RequestError as ex:
            if ex.status_code == 400 and ex.error == "resource_already_exists_exception":
                pass
            else:
                raise ex

        # destroy the indexes as well as the Index, IndexVersion, IndexAction objects
        call_command('es_dangerous_reset')

        # check that es_dangerous_reset didn't touch the hidden indexes in elasticsearch
        self.assertTrue(es_client.indices.exists(index=hidden_index_name), ".hidden-index should still exist after es_dangerous_reset")
        es_client.indices.delete(hidden_index_name)
        self.assertFalse(es_client.indices.exists(index=hidden_index_name), ".hidden-index should NOT still exist after deleting it")

        version_model = MovieSearchIndex.get_version_model()
        self.assertIsNotNone(version_model)
        new_version_id = version_model.id
        self.assertGreater(new_version_id, old_version_id, "After es_dangerous_reset, new version id for movie search index should be > old id")

        index_model = Index.objects.get(name='movies')
        index_version = index_model.active_version

        # one for create and one for activate
        num_index_actions = index_version.indexaction_set.all().count()
        expected_msg = "After es_dangerous_reset, active movies index should have 1 IndexAction, but it had {}".format(1, num_index_actions)
        self.assertEqual(num_index_actions, 1, expected_msg)

        available_version_ids = index_model.indexversion_set.all().values_list('id', flat=True)
        self.assertGreaterEqual(len(available_version_ids), 1, "After es_dangerous_reset, the movies index should have one available version")

        num_docs = MovieSearchIndex.get_num_docs()
        self.assertEqual(num_docs, 0, "After es_dangerous_reset, no documents should be in elasticsearch")


class TestEsCreateManagementCommand(CommonDEMTestUtilsMixin, DEMTestCaseMixin, TestCase):
    """
    Tests ./manage.py es_create
    """

    fixtures = ['tests/tests_initial.json']

    def test_basic_invocation_and_force_flags(self):
        index_model, version_model, _ = self.check_basic_setup_and_get_models()

        call_command('es_create', index_model.name)

        # by default, calling create shouldn't add a new version, since it hasn't changed
        available_version_ids = index_model.get_available_versions().values_list('id', flat=True)
        expected_msg = "After initial es_create, the movies index should still only have one version since it hasn't changed"
        self.assertEqual(len(available_version_ids), 1, expected_msg)

        call_command('es_create', index_model.name, force=True)

        available_version_ids = index_model.get_available_versions().values_list('id', flat=True)
        expected_msg = "After es_create --force, the movies index should have two versions"
        self.assertEqual(len(available_version_ids), 2, expected_msg)

    def test_all_and_force_flags(self):
        movies_index_model, _, _ = self.check_basic_setup_and_get_models("movies")

        new_index_name = "moviez"
        with get_new_search_index(new_index_name):
            moviez_index_model, _, _ = self.check_basic_setup_and_get_models(new_index_name)

            call_command('es_create', all=True)

            for index_model_instance in [movies_index_model, moviez_index_model]:
                available_version_ids = moviez_index_model.indexversion_set.all().values_list('id', flat=True)
                expected_msg = "After es_create --all, the {} index should still have one version".format(index_model_instance.name)
                self.assertEqual(len(available_version_ids), 1, expected_msg)

            call_command('es_create', all=True, force=True)

            for index_model_instance in [movies_index_model, moviez_index_model]:
                available_version_ids = moviez_index_model.indexversion_set.all().values_list('id', flat=True)
                expected_msg = "After es_create --all --force, the {} index should now have two versions".format(index_model_instance.name)
                self.assertEqual(len(available_version_ids), 2, expected_msg)

    def test_es_only_flag(self):
        """
        Test that ./manage.py es_create my_index --es-only checks
        if it does not exist in es, and if it does not exist it creates it
        with the schema in the database.
        """
        new_index_name = "moviez"
        # create a new temporary index we can change inside this test
        with get_new_search_index(new_index_name):
            moviez_index_model, moviez_index_version, moviez_dem_index = self.check_basic_setup_and_get_models(new_index_name)

            movies1_schema = moviez_index_version.get_indented_schema_body()
            log.info("movies index json: {}".format(movies1_schema))

            call_command('es_drop', moviez_index_version.name, exact=True, force=True, es_only=True)

            expected_msg = "the {} index should NOT exist in elasticsearch after es_drop.".format(moviez_index_model.name)
            self.assertFalse(es_client.indices.exists(index=moviez_index_version.name), expected_msg)

            class MovieSearchDocSchemaModified(DefaultNewSearchDocTypeMixin):
                complete_new_field = alternate_textfield

            # change the index again:
            with get_new_search_index(new_index_name, MovieSearchDocSchemaModified, dem_index=moviez_dem_index):
                _, movies_index_version2, movies_dem_index2 = self.check_basic_setup_and_get_models(new_index_name, expected_num_versions=2)

                movies2_schema = movies_index_version2.get_indented_schema_body()
                log.info("movies2 index json: {}".format(movies1_schema))

                self.assertNotEqual(movies1_schema, movies2_schema)

                call_command('es_create', moviez_index_model.name, es_only=True)

                expected_msg = "the {} index SHOULD exist in elasticsearch after es_create --es-only.".format(moviez_index_version.name)
                self.assertTrue(es_client.indices.exists(index=moviez_index_version.name), expected_msg)

                expected_msg = "the {} index SHOULD exist in elasticsearch after es_create --es-only.".format(movies_index_version2.name)
                self.assertTrue(es_client.indices.exists(index=movies_index_version2.name), expected_msg)

                available_versions = moviez_index_model.get_available_versions()
                available_versions_num = available_versions.count()
                expected_msg = "After `es_create {ver_name} --es_only`, the {ver_name} index should have two index versions available, but it had {num}".format(
                    ver_name=moviez_index_model.name, num=available_versions_num)
                self.assertEqual(available_versions_num, 2, expected_msg)


class TestEsDropManagementCommand(CommonDEMTestUtilsMixin, DEMTestCaseMixin, TestCase):
    """
    Tests ./manage.py es_drop
    """

    fixtures = ['tests/tests_initial.json']

    def test_basic_invocation(self):
        index_model, version_model, _ = self.check_basic_setup_and_get_models()

        # since the version is active, we should expect to have to use the force flag
        call_command('es_drop', version_model.name, exact=True, force=True)

        expected_msg = "the {} index should NOT exist in elasticsearch after es_drop.".format(version_model.name)
        self.assertFalse(ES_CLIENT.indices.exists(index=version_model.name), expected_msg)

        available_version_ids = index_model.indexversion_set.all().values_list('id', flat=True)
        self.assertEqual(len(available_version_ids), 1, "After es_drop, the movies index should still have one version")

        deleted_model = IndexVersion.objects.get(id=available_version_ids[0])
        expected_msg = "After es_drop, the soft delete flag on the IndexVersion model id {} should be True".format(deleted_model.id)
        self.assertTrue(deleted_model.is_deleted, expected_msg)

    def test_es_only_flag(self):
        """
        test that ./manage.py es_drop --es-only really only drops the elasticsearch index,
        and does not have an impact on the database's record of what the indexes should be
        """
        index_model, version_model, dem_index = self.check_basic_setup_and_get_models()

        # since the version is active, we should expect to have to use the force flag
        call_command('es_drop', version_model.name, exact=True, force=True, es_only=True)

        expected_msg = "the {} index should NOT exist in elasticsearch after es_drop.".format(version_model.name)
        self.assertFalse(ES_CLIENT.indices.exists(index=version_model.name), expected_msg)

        available_version_ids = index_model.indexversion_set.all().values_list('id', flat=True)
        self.assertEqual(len(available_version_ids), 1, "After es_drop, the movies index should still have one version")

        deleted_model = IndexVersion.objects.get(id=available_version_ids[0])
        expected_msg = "After es_drop, the soft delete flag on the IndexVersion model id {} should be False".format(deleted_model.id)
        self.assertFalse(deleted_model.is_deleted, expected_msg)

    def test_es_only_all_flags(self):
        movies_index_model, _, _ = self.check_basic_setup_and_get_models("movies")

        new_index_name = "moviez"
        with get_new_search_index(new_index_name) as index_info:
            moviez_index, moviez_doctype = index_info
            moviez_index_model, _, _ = self.check_basic_setup_and_get_models(new_index_name)

            call_command('es_update', new_index_name)

            num_docs = moviez_index.get_num_docs()
            expected_msg = "After updating the index, '{}' index should have had two documents in elasticsearch".format(new_index_name)
            self.assertEqual(num_docs, 2, expected_msg)

            # at this point we have two indexes, and the one called moviez has two docs in it

            call_command('es_drop', all=True, force=True, es_only=True)

            # test that none of our indexes are available
            es_indexes = DEMIndexManager.list_es_created_indexes()
            expected_msg = "After calling ./manage.py es_drop --all --force --es-only, es shouldn't have any indexes in it"
            self.assertEqual(len(es_indexes), 0, expected_msg)

            for index_model_instance in [movies_index_model, moviez_index_model]:
                available_version_ids = moviez_index_model.indexversion_set.all().values_list('id', flat=True)
                expected_msg = "After es_drop, the {} index should still have one version".format(index_model_instance.name)
                self.assertEqual(len(available_version_ids), 1, expected_msg)

                deleted_model = IndexVersion.objects.get(id=available_version_ids[0])
                expected_msg = "After es_drop, the soft delete flag on the IndexVersion model id {} should be False".format(deleted_model.id)
                self.assertFalse(deleted_model.is_deleted, expected_msg)


class TestEsListManagementCommand(CommonDEMTestUtilsMixin, DEMTestCaseMixin, TestCase):
    """
    Test that es_list output is formatted as expected
    """

    fixtures = ['tests/tests_initial.json']

    def test_basic_invocation_and_es_only(self):
        index_model, version_model, _ = self.check_basic_setup_and_get_models()

        scenario = "first call to es_list table should show with zero docs"
        es_list_row = get_es_list_row(version_model, created=1, active=1, docs=0)
        expected_table = get_es_list_table([es_list_row])
        self.check_es_list(scenario_message=scenario, expected_table=expected_table)

        call_command('es_update', 'movies')

        scenario = "after updating the index, the Docs column should have 2"
        es_list_row = get_es_list_row(version_model, created=1, active=1, docs=2)
        expected_table = get_es_list_table([es_list_row])
        self.check_es_list(scenario_message=scenario, expected_table=expected_table)

    def test_es_list_es_only(self):
        scenario = "es_list --es_only should only show indexes that do not have a . as the first char"
        hidden_index_name = ".hidden-index"
        try:
            es_client.indices.create(hidden_index_name)
        except RequestError as ex:
            if ex.status_code == 400 and ex.error == "resource_already_exists_exception":
                pass
            else:
                raise ex

        rows = []
        for index_name, index_info in es_client.indices.stats(metric=['docs'])['indices'].items():
            if not index_name.startswith('.'):
                rows.append(get_es_only_row(index_name, count=index_info['total']['docs']['count']))

        expected_table = get_es_only_table(rows)
        self.check_es_list(es_only=True, scenario_message=scenario, expected_table=expected_table)

        es_client.indices.delete(hidden_index_name)
        self.assertFalse(es_client.indices.exists(index=hidden_index_name), ".hidden-index should now be deleted")

    def test_after_es_create_with_specified_index(self):
        _, movies_version_model, _ = self.check_basic_setup_and_get_models()

        new_index_name = "moviez"
        with get_new_search_index(new_index_name):
            _, moviez_version_model, _ = self.check_basic_setup_and_get_models(new_index_name)

            scenario = "After create, there should be movies and moviez indexes in the es_list table"
            two_rows = [get_es_list_row(version) for version in (movies_version_model, moviez_version_model)]
            self.check_es_list(scenario_message=scenario, expected_table=get_es_list_table(two_rows))

            scenario = "When movies and moviez index are available, calling `./manage.py es_list moviez` should only return moviez reusults"
            self.check_es_list(scenario_message=scenario, expected_table=get_es_list_table(two_rows[1:]), args=['moviez'])

    def test_es_list_blank_row(self):
        """
        Checks for the expected output when ./manage.py es_list is called,
        and no index versions have been created for a particular index.
        """
        movies_index_model, _, movies_dem_index = self.check_basic_setup_and_get_models()

        new_index_name = "moviez"
        with get_new_search_index(new_index_name):
            _, moviez_version_model, _ = self.check_basic_setup_and_get_models(new_index_name)

            call_command('es_drop', 'movies', force=True)

            scenario = "after deleting movies index and adding moviez index, former should be blank and latter should be created and active"
            blank_movies_row = get_blank_es_list_row(movies_index_model.name)
            rows = [blank_movies_row, get_es_list_row(moviez_version_model)]
            self.check_es_list(scenario_message=scenario, expected_table=get_es_list_table(rows))

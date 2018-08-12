from __future__ import (absolute_import, division, print_function, unicode_literals)

import logging

from django.core.management import call_command

from django_elastic_migrations import DEMIndexManager, es_client
from django_elastic_migrations.models import Index, IndexVersion
from django_elastic_migrations.utils.test_utils import DEMTestCase
from tests.es_config import ES_CLIENT
from tests.models import Movie
from tests.search import MovieSearchIndex, MovieSearchDoc, get_new_search_index, alternate_textfield, DefaultNewSearchDocTypeMixin

log = logging.getLogger(__file__)


# noinspection PyUnresolvedReferences
class CommonDEMTestUtilsMixin(object):

    def _check_basic_setup_and_get_models(self, index_name='movies', expected_num_versions=1):
        dem_index = DEMIndexManager.get_dem_index(index_name)

        index_model = dem_index.get_index_model()

        version_model = dem_index.get_version_model()
        expected_msg = "The {} index should have an active version.".format(index_name)
        self.assertIsNotNone(version_model, expected_msg)

        available_version_ids = index_model.get_available_versions().values_list('id', flat=True)
        expected_msg = "The '{}' index should have {} available version(s)".format(index_name, expected_num_versions)
        self.assertEqual(len(available_version_ids), expected_num_versions, expected_msg)

        expected_msg = "The {} index should already exist in elasticsearch.".format(version_model.name)
        self.assertTrue(version_model.exists_in_es(), expected_msg)

        return index_model, version_model, dem_index


class TestEsUpdateManagementCommand(CommonDEMTestUtilsMixin, DEMTestCase):
    """
    Tests ./manage.py es_update
    """

    fixtures = ['tests/tests_initial.json']

    def test_basic_invocation(self):
        self._check_basic_setup_and_get_models()

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


class TestEsDangerousResetManagementCommand(DEMTestCase):
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

        # destroy the indexes as well as the Index, IndexVersion, IndexAction objects
        call_command('es_dangerous_reset')

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


class TestEsCreateManagementCommand(CommonDEMTestUtilsMixin, DEMTestCase):
    """
    Tests ./manage.py es_create
    """

    fixtures = ['tests/tests_initial.json']

    def test_basic_invocation_and_force_flags(self):
        index_model, version_model, _ = self._check_basic_setup_and_get_models()

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
        movies_index_model, _, __ = self._check_basic_setup_and_get_models("movies")

        new_index_name = "moviez"
        with get_new_search_index(new_index_name):
            moviez_index_model, _, __ = self._check_basic_setup_and_get_models(new_index_name)

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
            moviez_index_model, moviez_index_version, moviez_dem_index = self._check_basic_setup_and_get_models(new_index_name)

            movies1_schema = moviez_index_version.get_indented_schema_body()
            log.info("movies index json: {}".format(movies1_schema))

            call_command('es_drop', moviez_index_version.name, exact=True, force=True, es_only=True)

            expected_msg = "the {} index should NOT exist in elasticsearch after es_drop.".format(moviez_index_model.name)
            self.assertFalse(es_client.indices.exists(index=moviez_index_version.name), expected_msg)

            class MovieSearchDocSchemaModified(DefaultNewSearchDocTypeMixin):
                complete_new_field = alternate_textfield

            # change the index again:
            with get_new_search_index(new_index_name, MovieSearchDocSchemaModified, dem_index=moviez_dem_index):
                _, movies_index_version2, movies_dem_index2 = self._check_basic_setup_and_get_models(new_index_name, expected_num_versions=2)

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


class TestEsDropManagementCommand(CommonDEMTestUtilsMixin, DEMTestCase):
    """
    Tests ./manage.py es_drop
    """

    fixtures = ['tests/tests_initial.json']

    def test_basic_invocation(self):
        index_model, version_model, _ = self._check_basic_setup_and_get_models()

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
        index_model, version_model, dem_index = self._check_basic_setup_and_get_models()

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
        movies_index_model, _, __ = self._check_basic_setup_and_get_models("movies")

        new_index_name = "moviez"
        with get_new_search_index(new_index_name) as index_info:
            moviez_index, moviez_doctype = index_info
            moviez_index_model, _, __ = self._check_basic_setup_and_get_models(new_index_name)

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

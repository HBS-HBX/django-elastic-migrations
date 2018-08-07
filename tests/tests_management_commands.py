from __future__ import (absolute_import, division, print_function, unicode_literals)

from django.core.management import call_command

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.models import Index, IndexVersion
from django_elastic_migrations.utils.test_utils import DEMTestCase
from tests.es_config import ES_CLIENT
from tests.models import Movie
from tests.search import MovieSearchIndex, MovieSearchDoc, get_new_search_index


class TestEsUpdateManagementCommand(DEMTestCase):
    """
    Tests ./manage.py es_update
    """

    fixtures = ['tests/tests_initial.json']

    def test_basic_invocation(self):
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
        self.assertGreaterEqual(len(available_version_ids), 1, "At test setup, the movies index should have one available version")

        pre_available_indexaction_ids = index_model.indexaction_set.all().values_list('id', flat=True)
        num_pre_indexactions = len(pre_available_indexaction_ids)
        self.assertEqual(num_pre_indexactions, 3, "At test setup, movies index should have 3 IndexActions applied")

        # create a new version so we have more than one
        call_command('es_create', 'movies', force=True)
        call_command('es_activate', 'movies')

        version_model = MovieSearchIndex.get_version_model()
        self.assertIsNotNone(version_model)
        new_version_id = version_model.id
        self.assertGreater(new_version_id, old_version_id, "After creation, new version id for the movie search index should have been > old id")
        old_version_id = new_version_id

        # update the index to create a related IndexAction - note, this creates two IndexActions, one for the partial update and one for the parent update
        call_command('es_update', 'movies')

        available_indexaction_ids = index_model.indexaction_set.all().values_list('id', flat=True)
        expected_num_indexactions = num_pre_indexactions + 4
        self.assertEqual(
            len(available_indexaction_ids), expected_num_indexactions,
            "Creating, activating and updating a new movies index version should record {} IndexActions".format(expected_num_indexactions))

        num_docs = MovieSearchIndex.get_num_docs()
        self.assertEqual(num_docs, 2, "After updating the index, it should have had two documents in elasticsearch")

        # destroy the documents, IndexAction objects, and
        call_command('es_dangerous_reset')

        version_model = MovieSearchIndex.get_version_model()
        self.assertIsNotNone(version_model)
        new_version_id = version_model.id
        self.assertGreater(new_version_id, old_version_id, "After es_dangerous_reset, new version id for movie search index should be > old id")

        index_model = Index.objects.get(name='movies')
        # one for create and one for activate
        self.assertEqual(index_model.indexaction_set.all().count(), 2, "After es_dangerous_reset, movies index should have two associated IndexActions")

        available_version_ids = index_model.indexversion_set.all().values_list('id', flat=True)
        self.assertGreaterEqual(len(available_version_ids), 1, "After es_dangerous_reset, the movies index should have one available version")

        num_docs = MovieSearchIndex.get_num_docs()
        self.assertEqual(num_docs, 0, "After es_dangerous_reset, no documents should be in elasticsearch")


class TestEsDropManagementCommand(DEMTestCase):
    """
    Tests ./manage.py es_drop
    """

    fixtures = ['tests/tests_initial.json']

    def test_basic_invocation(self):
        index_model, version_model = self._check_basic_setup_and_get_models()

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
        index_model, version_model = self._check_basic_setup_and_get_models()

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
        movies_index_model, _ = self._check_basic_setup_and_get_models("movies")

        new_index_name = "moviez"
        movies_2_index, movies_2_doctype = get_new_search_index(new_index_name)
        moviez_index_model, _ = self._check_basic_setup_and_get_models(new_index_name)

        call_command('es_update', new_index_name)

        num_docs = movies_2_index.get_num_docs()
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

    def _check_basic_setup_and_get_models(self, index_name='movies'):
        dem_index = DEMIndexManager.get_dem_index(index_name)

        index_model = Index.objects.get(name=index_name)

        version_model = dem_index.get_version_model()
        self.assertIsNotNone(version_model)

        available_version_ids = index_model.indexversion_set.all().values_list('id', flat=True)
        expected_msg = "At test setup, the '{}' index should have one available version".format(index_name)
        self.assertEqual(len(available_version_ids), 1, expected_msg)

        expected_msg = "the {} index should already exist in elasticsearch.".format(version_model.name)
        self.assertTrue(ES_CLIENT.indices.exists(index=version_model.name), expected_msg)

        return index_model, version_model

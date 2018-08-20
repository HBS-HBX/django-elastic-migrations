from django.test import TestCase

from django_elastic_migrations.utils import django_elastic_migrations_log


class TestDEMLog(TestCase):

    def test_mp_logging_setup(self):
        self.assertFalse(django_elastic_migrations_log.mp_logging_enabled)

        django_elastic_migrations_log.start_multiprocessing_logging()

        self.assertTrue(django_elastic_migrations_log.mp_logging_enabled)

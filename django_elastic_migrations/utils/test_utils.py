from django.test import TestCase

from django_elastic_migrations import DEMIndexManager


class DEMTestCase(TestCase):

    def setUp(self):
        DEMIndexManager.test_pre_setup()
        super(DEMTestCase, self)._pre_setup()

    def tearDown(self):
        DEMIndexManager.test_post_teardown()
        super(DEMTestCase, self).tearDown()

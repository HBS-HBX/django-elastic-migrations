from django_elastic_migrations import DEMIndexManager


class DEMTestCaseMixin(object):
    """
    Mix into TestCase or TransactionTestCase to set up and then later clear out
    temporary elasticsearch indexes for each test
    """

    def setUp(self):
        super(DEMTestCaseMixin, self).setUp()
        DEMIndexManager.test_post_setup()

    def tearDown(self):
        DEMIndexManager.test_pre_teardown()
        super(DEMTestCaseMixin, self).tearDown()

    @classmethod
    def tearDownClass(cls):
        DEMIndexManager.test_post_teardown()
        super().tearDownClass()

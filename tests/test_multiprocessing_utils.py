from multiprocessing import cpu_count
from unittest import skip

from django.test import TestCase

from django_elastic_migrations.utils.multiprocessing_utils import DjangoMultiProcess


def add_1(num):
    return {'job_id': num, 'result': num + 1}


@skip("AttributeError: Can't pickle local object 'threadwrapper.<locals>.wrapper'")
class TestMultiprocessingUtils(TestCase):

    def test_basic_multiprocessing(self):
        """
        Do a basic test of DjangoMultiProcess that doesn't touch the database
        :return:
        :rtype:
        """

        one_to_ten = range(1, 10)

        workers = cpu_count()
        django_multiprocess = DjangoMultiProcess(workers, log_debug_info=3)

        with django_multiprocess:
            django_multiprocess.map(add_1, one_to_ten)

        results = django_multiprocess.results()

        for result_obj in results:
            job_id = result_obj.get('job_id')
            result = result_obj.get('result')
            self.assertEqual(job_id + 1, result)

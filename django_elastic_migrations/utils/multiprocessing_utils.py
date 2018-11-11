# coding=utf-8
# noinspection PyCompatibility
import queue
import time
import traceback
from multiprocessing import Process, cpu_count, Manager

from django import db
from django.conf import settings
from django.core.cache import caches
from django.db import reset_queries
from elasticsearch_dsl import connections

from django_elastic_migrations import get_logger as get_dem_logger
from django_elastic_migrations.utils.django_elastic_migrations_log import start_multiprocessing_logging

logger = get_dem_logger()

"""
Django Multiprocessing Utility Functions ↓
Adapted from Jeremy Robin's "Django Multiprocessing":
https://engineering.talentpair.com/django-multiprocessing-153dbcf51dab
"""

USE_ALL_WORKERS = 999


class Timer(object):
    """
    Simple class for timing code blocks
    """

    def __init__(self):
        self.start_time = time.time()

    def done(self):
        end_time = time.time()
        return int(end_time - self.start_time)


def close_service_connections():
    """
    Close all connections before we spawn our processes
    This function should only be used when writing multithreaded scripts
    where connections need to manually opened and closed so that threads
    don't reuse the same connection
    https://stackoverflow.com/questions/8242837/django-multiprocessing-and-database-connections
    """
    from .. import user_close_service_connections

    if user_close_service_connections:
        user_close_service_connections()
    else:
        warning = (
            "You have not specified DJANGO_ELASTIC_MIGRATIONS_CLOSE_CONNECTIONS \n"
            "function in your Django settings. By default, Django Elastic Migrations \n"
            "will close service connections for the db, elasticsearch, and cache "
            "connections. It's highly recommended to specify this if using "
            "parallel index updating."
        )
        logger.warn(warning)
        # close db connections, they will be recreated automatically
        db.connections.close_all()

        # close ES connection, needs to be manually recreated
        # todo: use es_client connection name
        connections.connections.remove_connection("default")

        # close redis connections, will be recreated automatically
        for k in settings.CACHES.keys():
            caches[k].close()


def recreate_service_connections():
    """
    For the most part all this happens automatically when django starts,
    this func should only be used when writing multithreaded scripts
    where connections need to manually opened and closed
    so that threads don't reuse the same connection
    """
    from .. import user_recreate_service_connections

    if user_recreate_service_connections:
        user_recreate_service_connections()
    else:
        warning = (
            "You have not specified DJANGO_ELASTIC_MIGRATIONS_RECREATE_CONNECTIONS \n"
            "function in your Django settings, so Django Elastic Migrations "
            "will reconnect with the Elasticsearch defaults. It's highly recommended "
            "to specify this in your settings if you are using parallel index updating."
        )
        logger.warn(warning)
        global es_client
        # ES is one that needs to be recreated explicitly
        # TODO: find a way to read the settings from ES_CLIENT and restore them here
        es_client = connections.connections.create_connection()


def threadwrapper(some_function, catch_exceptions=True):
    """
    This wrapper should only be used when a function is being called in
    a multiprocessing context.

    To call it:
    p = Process(target=threadwrapper(func), args=[self.queue, items])
    p.start()
    """

    def wrapper(queue, items):
        """
        :param queue: python multiprocessing queue for results
        :param items: items to process with queue
        :return:
        """
        recreate_service_connections()
        if settings.DEBUG:
            # In django debug mode, queries are cached, which can use up RAM.
            reset_queries()

        for i in items:
            try:
                rv = some_function(i)
            except Exception:
                rv = None

                if catch_exceptions:
                    logger.error("threadwrapper caught an error, continuing - %s" % traceback.format_exc())
                else:
                    raise

            queue.put(rv, block=False)

        close_service_connections()

    return wrapper


class DjangoMultiProcess(object):
    """
    Abstraction for using multiprocessing with Django
    Use as context manager so as to not worry about garbage collection
    Will likely not work when running tests
    """

    queue = None
    job_count = 1
    workers = []

    def __init__(self, num_workers=None, max_workers=None, log_debug_info=False, status_interval=20):

        vcpus = cpu_count()

        if num_workers is None:

            # always use at least one thread
            # leave one cpu remaining for timer updates, etc
            self.num_workers = vcpus - 1
            if self.num_workers < 2:
                self.num_workers = 1

            if max_workers and self.num_workers > max_workers:
                self.num_workers = max_workers

        else:
            self.num_workers = num_workers

        self.log_debug_info = log_debug_info

        self.status_interval = status_interval

        logger.info("Using {} multiprocessing workers out of {} logical CPUs".format(self.num_workers, vcpus))

        # synchronous result queue will be instantiated in self.map()
        self.queue = None

    def __enter__(self):
        start_multiprocessing_logging()
        close_service_connections()
        return self

    def map(self, func, iterable):

        # this synchronous queue is passed to child processes, so they can append results
        self.queue = Manager().Queue()
        self.job_count = len(iterable) or 1

        for worker_idx in range(self.num_workers):

            jobs = []

            for idx, job in enumerate(iterable):
                if idx % self.num_workers == worker_idx:
                    jobs.append(job)

            if self.log_debug_info:
                logger.debug("Working on {} of {} jobs in worker {}".format(len(jobs), len(iterable), worker_idx))

            p = Process(target=threadwrapper(func), args=[self.queue, jobs])
            p.start()
            self.workers.append(p)

        self._wait()

    def _wait(self):
        """
        Wait for all workers to finish
        Wake up periodically to print out how much work is done
        """
        total_time = Timer()

        while [p for p in self.workers if p.is_alive()]:

            proc_timer = Timer()

            for p in self.workers:
                p.join(timeout=self.status_interval)

                interval_secs = proc_timer.done() // 1000

                # if we've exceeded status interval, print out & reset counter
                if self.log_debug_info and interval_secs >= self.status_interval:
                    proc_timer = Timer()

                    total_secs = total_time.done() // 1000

                    percent = (self.queue.qsize() * 100) // self.job_count
                    logger.info("--------- {}% done ({}s elapsed) ---------".format(percent, total_secs))

    def results(self):
        """
        Get the results of calling the functions
        :return: list of results, one from each worker
        """
        rv = []
        try:
            while True:
                rv.append(self.queue.get(block=False))
        except queue.Empty:
            return rv

    def __exit__(self, type, value, traceback):
        # recreate the connections so subsequent actions have them
        recreate_service_connections()

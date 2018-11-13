import logging

from multiprocessing_logging import install_mp_handler

mp_logging_enabled = False


def get_logger(name="django_elastic_migrations"):
    real_logger = logging.getLogger(name)
    for level in ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']:
        setattr(real_logger, level, getattr(logging, level))
    return real_logger


def start_multiprocessing_logging():
    """
    start multiprocessing-logging to make each handler a synchronized queue.
    Called by django_elastic_migrations.utils.multiprocessing_utils.DjangoMultiProcess.__enter__
    See https://github.com/jruere/multiprocessing-logging/blob/master/multiprocessing_logging.py
    TBD: uninstall mp_logging; currently we don't stop and reset mp logging; it's a one-shot for the process.
    :return:
    :rtype: None
    """
    global mp_logging_enabled

    if not mp_logging_enabled:
        mp_logging_enabled = True
        install_mp_handler()

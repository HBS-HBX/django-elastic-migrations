from __future__ import print_function
import logging
from multiprocessing_logging import install_mp_handler


install_mp_handler()


def get_logger(name="django_elastic_migrations"):
    real_logger = logging.getLogger(name)
    for level in ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']:
        setattr(real_logger, level, getattr(logging, level))
    return real_logger

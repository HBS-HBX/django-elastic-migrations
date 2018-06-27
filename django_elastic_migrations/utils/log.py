from __future__ import print_function
import logging


def get_logger(name="django-elastic-migrations"):
    real_logger = logging.getLogger(name)
    for level in ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']:
        setattr(real_logger, level, getattr(logging, level))
    return real_logger

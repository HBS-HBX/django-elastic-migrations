#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=C0111,W6005,W6100
from __future__ import absolute_import, print_function

import os
import re
import sys

from setuptools import setup


def get_version(*file_paths):
    """
    Extract the version string from the file at the given relative path fragments.
    """
    filename = os.path.join(os.path.dirname(__file__), *file_paths)
    version_file = open(filename).read()
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError('Unable to find version string.')


VERSION = get_version('django_elastic_migrations', '__init__.py')

# usage: python setup.py tag pushes a new version tag
if sys.argv[-1] == 'tag':
    print("Tagging the version on github:")
    os.system("git tag -a %s -m 'version %s'" % (VERSION, VERSION))
    os.system("git push origin %s" % VERSION)
    sys.exit()

README = open('README.rst').read()
CHANGELOG = open('CHANGELOG.rst').read()

setup(
    name='django-elastic-migrations',
    version=VERSION,
    description="""Manage Elasticsearch Indexes in Django""",
    long_description=README + '\n\n' + CHANGELOG,
    author='Harvard Business School, HBX Department',
    author_email='pnore@hbs.edu',
    url='https://github.com/HBS-HBX/django-elastic-migrations',
    packages=[
        'django_elastic_migrations',
    ],
    license='MIT',
    include_package_data=True,
    install_requires=[
        # TBD: GH issue #3 includes support for elasticsearch-dsl>=6.2.0
        "Django>=1.8,<2.1", "elasticsearch-dsl>=6.0.0,<6.2.0", "texttable>=1.2.1",
        "multiprocessing-logging>=0.2.6"
    ],
    zip_safe=False,
    keywords='Django Elasticsearch',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Framework :: Django',
        'Framework :: Django :: 1.9',
        'Framework :: Django :: 1.10',
        'Framework :: Django :: 1.11',
        'Framework :: Django :: 2.0',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
    ],
)

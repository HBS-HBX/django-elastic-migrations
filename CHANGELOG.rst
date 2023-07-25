Changelog
---------

0.10.0 (2023-07-12)
^^^^^^^^^^^^^^^^^^
* support elasticsearch-dsl 6.4 - closes `#3 support elasticsearch-dsl-py v6.4`
* fix `#90 Convert to GitHub Actions`
* fix `#96 es_list doesn't list all indexes`
* open up django to anything > 1.10
* rename DEMDocType to DEMDocument, following elasticsearch-dsl-py
  * DEMDocType will be removed in 1.X
* drop support for Python 3.6 and 3.7

0.9.0 (2018-11-27)
^^^^^^^^^^^^^^^^^^
* added postgres to docker-compose and travis, and started using postgres for all tests instead of sqlite
* fix `#30 multiprocessing tests <https://github.com/HBS-HBX/django-elastic-migrations/issues/30>`_
* fix ``tests.search.MovieSearchDoc.get_model_full_text()`` not indexing non-title fields
* fix ``./manage.py es_update -v=3`` not respecting the verbosity flag
* fix ``DEMIndexManager.initialize()`` not updating ``DEMDocType`` to point to new active version after ``es_activate``
* document ``DEMTestCaseMixin`` as the recommended way to support ``django-elastic-migrations`` in tests
* deprecate ``DEMIndexManager.test_pre_setup``; will be removed in future version

0.8.2 (2018-11-20)
^^^^^^^^^^^^^^^^^^
* fix `#59 twine check error in 0.8.1 <https://github.com/HBS-HBX/django-elastic-migrations/issues/59>`_

0.8.1 (2018-11-19)
^^^^^^^^^^^^^^^^^^
* fix `#50 add test coverage for es_list <https://github.com/HBS-HBX/django-elastic-migrations/issues/50>`_
* fix `#58 ignore indexes with a dot in name in es_list --es-only and es_dangerous_reset <https://github.com/HBS-HBX/django-elastic-migrations/issues/58>`_

0.8.0 (2018-11-13)
^^^^^^^^^^^^^^^^^^
* fix `#6 support Django 2 <https://github.com/HBS-HBX/django-elastic-migrations/issues/6>`_
* fix `#43 remove es_deactivate <https://github.com/HBS-HBX/django-elastic-migrations/issues/43>`_
* fix `#44 add django 1.10 and 1.11 to test matrix <https://github.com/HBS-HBX/django-elastic-migrations/issues/44>`_
* fix `#45 remove support for python 2 <https://github.com/HBS-HBX/django-elastic-migrations/issues/45>`_
* In practice, Python 2 may work, but it is removed from the test matrix and won't be updated

0.7.8 (2018-11-13)
^^^^^^^^^^^^^^^^^^
* fix `#7 Convert Readme to rst for pypi <https://github.com/HBS-HBX/django-elastic-migrations/issues/7>`_
* first release on PyPI
* update project dependencies

0.7.7 (2018-09-17)
^^^^^^^^^^^^^^^^^^
* fix `#41 stack trace when indexing in py3 <https://github.com/HBS-HBX/django-elastic-migrations/issues/41>`_

0.7.6 (2018-09-11)
^^^^^^^^^^^^^^^^^^
* fix `#36 es_update --start flag broken <https://github.com/HBS-HBX/django-elastic-migrations/issues/39>`_

0.7.5 (2018-08-20)
^^^^^^^^^^^^^^^^^^
* fix `#35 open multiprocessing log in context handler <https://github.com/HBS-HBX/django-elastic-migrations/issues/35>`_

0.7.4 (2018-08-15)
^^^^^^^^^^^^^^^^^^
* fix `#33 error when nothing to resume using --resume <https://github.com/HBS-HBX/django-elastic-migrations/issues/33>`_

0.7.3 (2018-08-14)
^^^^^^^^^^^^^^^^^^
* fix #31 es_update movies --newer --workers does not store worker information

0.7.2 (2018-08-13)
^^^^^^^^^^^^^^^^^^
* fix #21 wrong batch update total using multiprocessing in 0.7.1
* fix #23 KeyError _index_version_name in es_update --newer
* address #25 use pks for queryset inside workers #29

0.7.1 (2018-08-07)
^^^^^^^^^^^^^^^^^^
* fixed gh #8 es_dangerous_reset --es-only to sync database to ES
* fixed gh #17 make es_dangerous_reset remove dem models
* improved test coverage
* added tests for ``es_create --es-only``
* added ``IndexVersion.hard_delete()`` (not called by default)
* added ``hard_delete`` flag to ``DropIndexAction``
* added ``hard_delete`` flag to ``DEMIndexManager.test_post_teardown()``
* updated ``__str__()`` of ``IndexAction`` to be more descriptive

0.7.0 (2018-08-06)
^^^^^^^^^^^^^^^^^^
* fixed gh #5: "add python 3 support and tests"

0.6.1 (2018-08-03)
^^^^^^^^^^^^^^^^^^
* fixed gh #9: "using elasticsearch-dsl 6.1, TypeError in DEMIndex.save"

0.6.0 (2018-08-01)
^^^^^^^^^^^^^^^^^^
* Added test structure for py2 - GH #2
* Renamed default log handler from ``django-elastic-migrations`` to ``django_elastic_migrations``

0.5.3 (2018-07-23)
^^^^^^^^^^^^^^^^^^
* First basic release
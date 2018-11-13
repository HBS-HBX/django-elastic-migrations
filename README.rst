
Django Elastic Migrations
=========================

`django-elastic-migrations`_ is a Django app for creating, indexing and changing schemas of Elasticsearch indexes.


.. image:: https://travis-ci.com/HBS-HBX/django-elastic-migrations.svg?branch=master
   :target: https://travis-ci.com/HBS-HBX/django-elastic-migrations
   :alt: Build Status


.. image:: https://codecov.io/gh/HBS-HBX/django-elastic-migrations/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/HBS-HBX/django-elastic-migrations
   :alt: codecov

.. _django-elastic-migrations: https://pypi.org/project/django-elastic-migrations/

Overview
--------

Elastic has given us basic python tools for working with its search indexes:

* `elasticsearch-py`_, a python interface to elasticsearch's REST API
* `elasticsearch-dsl-py`_, a Django-esque way of declaring Elasticsearch schemas,
  built upon `elasticsearch-py`_

Django Elastic Migrations adapts these tools into a Django app which also:

* Provides Django management commands for ``list``\ ing indexes, as well as performing
  ``create``, ``update``, ``activate`` and ``drop`` actions on them
* Implements concurrent bulk indexing powered by python ``multiprocessing``
* Gives Django test hooks for Elasticsearch
* Records a history of all actions that change Elasticsearch indexes
* Supports AWS Elasticsearch 6.0, 6.1 (6.2 TBD; see `#3 support elasticsearch-dsl 6.2`_)
* Enables having two or more servers share the same Elasticsearch cluster

.. _elasticsearch-py: https://github.com/elastic/elasticsearch-py
.. _elasticsearch-dsl-py: https://github.com/elastic/elasticsearch-dsl-py
.. _#3 support elasticsearch-dsl 6.2: https://github.com/HBS-HBX/django-elastic-migrations/issues/3


Models
^^^^^^

Django Elastic Migrations provides comes with three Django models:
**Index**, **IndexVersion**, and **IndexAction**:

* 
  **Index** - a logical reference to an Elasticsearch index.
  Each ``Index`` points to multiple ``IndexVersions``, each of which contains
  a snapshot of that ``Index`` schema at a particular time. Each ``Index`` has an
  *active* ``IndexVersion`` to which all actions are directed.

* 
  **IndexVersion** - a snapshot of an Elasticsearch ``Index`` schema at a particular
  point in time. The Elasticsearch index name is the name of the *Index* plus the
  primary key id of the ``IndexVersion`` model, e.g. ``movies-1``. When the schema is
  changed, a new ``IndexVersion`` is added with name ``movies-2``, etc.

* 
  **IndexAction** - a record of a change that impacts an ``Index``, such as updating
  the index or changing which ``IndexVersion`` is active in an ``Index``.

Management Commands
^^^^^^^^^^^^^^^^^^^

Use ``./manage.py es --help`` to see the list of all of these commands.

Read Only Commands
~~~~~~~~~~~~~~~~~~


* ``./manage.py es_list``

  * help: For each *Index*\ , list activation status and doc
    count for each of its *IndexVersions*
  * usage: ``./manage.py es_list``

Action Commands
~~~~~~~~~~~~~~~

These management commands add an Action record in the database,
so that the history of each *Index* is recorded.


* ``./manage.py es_create`` - create a new index.
* ``./manage.py es_activate`` - *activate* a new ``IndexVersion``. all
  updates and reads for that ``Index`` by will then go to that version.
* ``./manage.py es_update`` - update the documents in the index.
* ``./manage.py es_clear`` - remove the documents from an index.
* ``./manage.py es_drop`` - drop an index.
* ``./manage.py es_dangerous_reset`` - erase elasticsearch and reset the
  Django Elastic Migrations models.

For each of these, use ``--help`` to see the details.

Usage
^^^^^

Installation
~~~~~~~~~~~~

#. ``pip install django-elastic-migrations``; see `django-elastic-migrations`_ on PyPI
#. Put a reference to this package in your ``requirements.txt``
#. Ensure that a valid ``elasticsearch-dsl-py`` version is accessible, and configure
   the path to your configured Elasticsearch singleton client in your django settings:
   ``DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT = "tests.es_config.ES_CLIENT"``.
   There should only be one ``ES_CLIENT`` instantiated in your application.
#. Add ``django_elastic_migrations`` to ``INSTALLED_APPS`` in your Django
   settings file
#. Add the following information to your Django settings file:
   ::

      DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT = "path.to.your.singleton.ES_CLIENT"
      # optional, any unique number for your releases to associate with indexes
      DJANGO_ELASTIC_MIGRATIONS_GET_CODEBASE_ID = subprocess.check_output(['git', 'describe', "--tags"]).strip()
      # optional, can be used to have multiple servers share the same 
      # elasticsearch instance without conflicting
      DJANGO_ELASTIC_MIGRATIONS_ENVIRONMENT_PREFIX = "qa1_"

#. Create the ``django_elastic_migrations`` tables by running ``./manage.py migrate``
#. Create an ``DEMIndex``:
   ::

       from django_elastic_migrations.indexes import DEMIndex, DEMDocType
       from .models import Movie
       from elasticsearch_dsl import Text

       MoviesIndex = DEMIndex('movies')


       @MoviesIndex.doc_type
       class MovieSearchDoc(DEMDocType):
           text = TEXT_COMPLEX_ENGLISH_NGRAM_METAPHONE

           @classmethod
           def get_queryset(self, last_updated_datetime=None):
               """
               return a queryset or a sliceable list of items to pass to
               get_reindex_iterator
               """
               qs = Movie.objects.all()
               if last_updated_datetime:
                   qs.filter(last_modified__gt=last_updated_datetime)
               return qs

           @classmethod
           def get_reindex_iterator(self, queryset):
               return [
                   MovieSearchDoc(
                       text="a little sample text").to_dict(
                       include_meta=True) for g in queryset]


#. Add your new index to DJANGO_ELASTIC_MIGRATIONS_INDEXES in settings/common.py

#. Run ``./manage.py es_list`` to see the index as available:
   ::

       ./manage.py es_list

       Available Index Definitions:
       +----------------------+-------------------------------------+---------+--------+-------+-----------+
       |   Index Base Name    |         Index Version Name          | Created | Active | Docs  |    Tag    |
       +======================+=====================================+=========+========+=======+===========+
       | movies               |                                     | 0       | 0      | 0     | Current   |
       |                      |                                     |         |        |       | (not      |
       |                      |                                     |         |        |       | created)  |
       +----------------------+-------------------------------------+---------+--------+-------+-----------+
       Reminder: an index version name looks like 'my_index-4', and its base index name
       looks like 'my_index'. Most Django Elastic Migrations management commands
       take the base name (in which case the activated version is used)
       or the specific index version name.


#. Create the ``movies`` index in elasticsearch with ``./manage.py es_create movies``:
   ::

       $> ./manage.py es_create movies
       The doc type for index 'movies' changed; created a new index version
       'movies-1' in elasticsearch.
       $> ./manage.py es_list

       Available Index Definitions:
       +----------------------+-------------------------------------+---------+--------+-------+-----------+
       |   Index Base Name    |         Index Version Name          | Created | Active | Docs  |    Tag    |
       +======================+=====================================+=========+========+=======+===========+
       | movies               | movies-1                            | 1       | 0      | 0     | 07.11.005 |
       |                      |                                     |         |        |       | -93-gd101 |
       |                      |                                     |         |        |       | a1f       |
       +----------------------+-------------------------------------+---------+--------+-------+-----------+

       Reminder: an index version name looks like 'my_index-4', and its base index name 
       looks like 'my_index'. Most Django Elastic Migrations management commands 
       take the base name (in which case the activated version is used) 
       or the specific index version name.

#. Activate the ``movies-1`` index version, so all updates and reads go to it.
   ::

       ./manage.py es_activate movies
       For index 'movies', activating 'movies-1' because you said so.

#. Assuming you have implemented ``get_reindex_iterator``, you can call
   ``./manage.py es_update`` to update the index.
   ::

      $> ./manage.py es_update movies

      Handling update of index 'movies' using its active index version 'movies-1'
      Checking the last time update was called: 
       - index version: movies-1
       - update date: never 
      Getting Reindex Iterator...
      Completed with indexing movies-1

      $> ./manage.py es_list

      Available Index Definitions:
      +----------------------+-------------------------------------+---------+--------+-------+-----------+
      |   Index Base Name    |         Index Version Name          | Created | Active | Docs  |    Tag    |
      +======================+=====================================+=========+========+=======+===========+
      | movies               | movies-1                            | 1       | 1      | 3     | 07.11.005 |
      |                      |                                     |         |        |       | -93-gd101 |
      |                      |                                     |         |        |       | a1f       |
      +----------------------+-------------------------------------+---------+--------+-------+-----------+

Deployment
^^^^^^^^^^


* Creating and updating a new index schema can happen before you deploy.
  For example, if your app servers are running with the ``movies-1`` index activated, and you
  have a new version of the schema you'd like to pre-index, then log into another
  server and run ``./manage.py es_create movies`` followed by
  ``./manage.py es_update movies --newer``. This will update documents in all ``movies``
  indexes that are newer than the active one.
* After deploying, you can run
  ``./manage.py es_activate movies`` to activate the latest version. Be sure to cycle your
  gunicorn workers to ensure the change is caught by your app servers.
* During deployment, if ``get_reindex_iterator`` is implemented in such a way as to respond
  to the datetime of the last reindex date, then you can call
  ``./manage.py es_update movies --resume``, and it will index *only those documents that have
  changed since the last reindexing*. This way you can do most of the indexing ahead of time,
  and only reindex a portion at the time of the deployment.

Django Testing
^^^^^^^^^^^^^^


#. (optional) update ``DJANGO_ELASTIC_MIGRATIONS_ENVIRONMENT_PREFIX`` in
   your Django settings. The default test prefix is ``test_``.  Every
   test will create its own indexes.
   ::

       if 'test' in sys.argv:
           DJANGO_ELASTIC_MIGRATIONS_ENVIRONMENT_PREFIX = 'test_'

#. Override TestCase - ``test_utilities.py``

   .. code-block::

       from django_elastic_migrations import DEMIndexManager

       class MyTestCase(TestCase):

           def _pre_setup(self):
               DEMIndexManager.test_pre_setup()
               super(MyTestCase, self)._pre_setup()

           def _post_teardown(self):
               DEMIndexManager.test_post_teardown()
               super(MyTestCase, self)._post_teardown()

Excluding from Django's ``dumpdata`` command
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When calling `django's dumpdata command <https://docs.djangoproject.com/en/2.0/ref/django-admin/#dumpdata>`_\,
you likely will want to exclude the database tables used in this app:

::

   from django.core.management import call_command
   params = {
       'database': 'default',
       'exclude': [
           # we don't want to include django_elastic_migrations in dumpdata, 
           # because it's environment specific
           'django_elastic_migrations.index',
           'django_elastic_migrations.indexversion',
           'django_elastic_migrations.indexaction'
       ],
       'indent': 3,
       'output': 'path/to/my/file.json'
   }
   call_command('dumpdata', **params)

An example of this is included with the
`moviegen management command`_.

.. _moviegen management command: https://github.com/HBS-HBX/django-elastic-migrations/blob/master/tests/management/commands/moviegen.py

Tuning Bulk Indexing Parameters
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

By default, ``/.manage.py es_update`` will divide the result of 
``DEMDocType.get_queryset()`` into batches of size ``DocType.BATCH_SIZE``. 
Override this number to change the batch size. 

There are many configurable paramters to Elasticsearch's `bulk updater <https://elasticsearch-py.readthedocs.io/en/master/helpers.html?highlight=bulk#elasticsearch.helpers.streaming_bulk>`_.
To provide a custom value, override ``DEMDocType.get_bulk_indexing_kwargs()``
and return the kwargs you would like to customize.

Development
-----------

This project uses ``make`` to manage the build process. Type ``make help``
to see the available ``make`` targets.

Elasticsearch Docker Compose
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``docker-compose -f local.yml up``

`See docs/docker_setup for more info <./docs/docker_setup.rst>`_

Requirements
^^^^^^^^^^^^
This project uses `pip-tools`_. The ``requirements.txt`` files are generated
and pinned to latest versions with ``make upgrade``:

* run ``make requirements`` to run the pip install.

* run ``make upgrade`` to upgrade the dependencies of the requirements to the latest
  versions. This process also excludes ``django`` and ``elasticsearch-dsl``
  from the ``requirements/test.txt`` so they can be injected with different
  versions by tox during matrix testing.

.. _pip-tools: https://github.com/jazzband/pip-tools


Populating Local ``tests_movies`` Database Table With Data
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It may be helpful for you to populate a local database with Movies test
data to experiment with using ``django-elastic-migrations``. First,
migrate the database:

``./manage.py migrate --run-syncdb --settings=test_settings``

Next, load the basic fixtures:

``./manage.py loaddata tests/100films.json``

You may wish to add more movies to the database. A management command
has been created for this purpose. Get a `Free OMDB API key here <https://www.omdbapi.com/apikey.aspx>`_\ ,
then run a query like this (replace ``MYAPIKEY`` with yours):

.. code-block::

   $> ./manage.py moviegen --title="Inception" --api-key="MYAPIKEY"
   {'actors': 'Leonardo DiCaprio, Joseph Gordon-Levitt, Ellen Page, Tom Hardy',
    'awards': 'Won 4 Oscars. Another 152 wins & 204 nominations.',
    'boxoffice': '$292,568,851',
    'country': 'USA, UK',
    'director': 'Christopher Nolan',
    'dvd': '07 Dec 2010',
    'genre': 'Action, Adventure, Sci-Fi',
    'imdbid': 'tt1375666',
    'imdbrating': '8.8',
    'imdbvotes': '1,721,888',
    'language': 'English, Japanese, French',
    'metascore': '74',
    'plot': 'A thief, who steals corporate secrets through the use of '
            'dream-sharing technology, is given the inverse task of planting an '
            'idea into the mind of a CEO.',
    'poster': 'https://m.media-amazon.com/images/M/MV5BMjAxMzY3NjcxNF5BMl5BanBnXkFtZTcwNTI5OTM0Mw@@._V1_SX300.jpg',
    'production': 'Warner Bros. Pictures',
    'rated': 'PG-13',
    'ratings': [{'Source': 'Internet Movie Database', 'Value': '8.8/10'},
                {'Source': 'Rotten Tomatoes', 'Value': '86%'},
                {'Source': 'Metacritic', 'Value': '74/100'}],
    'released': '16 Jul 2010',
    'response': 'True',
    'runtime': 148,
    'title': 'Inception',
    'type': 'movie',
    'website': 'http://inceptionmovie.warnerbros.com/',
    'writer': 'Christopher Nolan',
    'year': '2010'}

To save the movie to the database, use the ``--save`` flag. Also useful is
the ``--noprint`` option, to suppress json. Also, if you add
``OMDB_API_KEY=MYAPIKEY`` to your environment variables, you don't have
to specify it each time:

.. code-block::

   $ ./manage.py moviegen --title "Closer" --noprint --save
   Saved 1 new movie(s) to the database: Closer

Now that it's been saved to the database, you may want to create a fixture,
so you can get back to this state in the future.

.. code-block::

   $ ./manage.py moviegen --makefixture=tests/myfixture.json
   dumping fixture data to tests/myfixture.json ...
   [...........................................................................]

Later, you can restore this database with the regular ``loaddata`` command:

.. code-block::

   $ ./manage.py loaddata tests/myfixture.json
   Installed 101 object(s) from 1 fixture(s)

There are already 100 films available using ``loaddata`` as follows:

.. code-block::

   $ ./manage.py loaddata tests/100films.json

Running Tests Locally
^^^^^^^^^^^^^^^^^^^^^

Run ``make test``. To run all tests and quality checks locally,
run ``make test-all``.

To just run linting, ``make quality``. Please note that if any of the
linters return a nonzero code, it will give an ``InvocationError`` error
at the end. See `tox's documentation for InvocationError`_ for more information.

We use ``edx_lint`` to compile ``pylintrc``. To update the rules,
change ``pylintrc_tweaks`` and run ``make pylintrc``.

.. _tox's documentation for InvocationError: https://tox.readthedocs.io/en/latest/example/general.html#understanding-invocationerror-exit-codes

Cutting a New Version
^^^^^^^^^^^^^^^^^^^^^

* optional: run ``make update`` to update dependencies
* bump version in `django_elastic_migrations/__init__.py <https://github.com/HBS-HBX/django-elastic-migrations/blob/master/django_elastic_migrations/__init__.py#L13>`_.
* update `CHANGELOG.rst <https://github.com/HBS-HBX/django-elastic-migrations/blob/master/CHANGELOG.rst>`_.
* submit PR bumping the version
* ensure test matrix is passing on travis and merge PR
* pull changes to master
* ``python3 setup.py tag`` to tag the new version
* ``make clean``
* ``python3 setup.py sdist bdist_wheel``
* ``twine upload -r testpypi dist/django-elastic-migrations-*.tar.gz``
* `Check it at https://test.pypi.org/project/django-elastic-migrations/ <https://test.pypi.org/project/django-elastic-migrations/>`_
* ``twine upload -r pypi dist/django-elastic-migrations-*.tar.gz``

# Django Elastic Migrations

Django Elastic Migrations provides a way to control the deployment of
multiple Elasticsearch schemas over time. 

## Overview

Elastic has given us basic tools needed to configure search indexes:

* **[`elasticsearch-py`](https://github.com/elastic/elasticsearch-py)**
  is a python interface to elasticsearch's REST API
* **[`elasticsearch-dsl-py`](https://github.com/elastic/elasticsearch-dsl-py)**
  is a Django-esque way of declaring complex Elasticsearch index schemas
  (which itself uses `elasticsearch-py`).

Technically you can accomplish everything you need with these, but 
applications a.) using more than one index or b.) deploying changes to 
schemas will need a *consistent* way to `create`, `update`, 
`activate` and `drop` and `list` their indexes. In addition, if you use 
[AWS Elasticsearch you cannot stop and apply a new mapping](https://docs.aws.amazon.com/elasticsearch-service/latest/developerguide/aes-supported-es-operations.html) 
to your index.  Basically AWS does not provide the 'stop' api so you must create a new index with a new schema
and then reindex into that schema, and then get your code to start using 
that new index. This process requires a little care.

*Django Elastic Migrations provides:* 
* Django management commands for `list`ing indexes, as well as performing
  `create`, `update`, `activate` and `drop` actions on them
* Records a history of actions performed, and gives an easy way to add 
  new recorded actions
* Supports AWS Elasticsearch 6.0 and above
* Provides a way to multiplex multiple environments into one 
  elasticsearch cluster using environment prefixes. Two or more servers 
  can share the same Elasticsearch cluster without overlapping indexes, 
  even when using the same code. 
* Facilitates clearing out the search database between unit tests. 


### Models
Django Elastic Migrations provides comes with three django models:
**Index**, **IndexVersion**, and **IndexAction**:

- **Index** - a base name, e.g. `course_search` that's the parent of 
  several *IndexVersions*. Not actually an Elasticsearch index.
  Each *Index* has at most one **active** *IndexVersion* to which 
  actions are directed.

- **IndexVersion** - an Elasticsearch index, configured with a schema
  at the time of creation. The Elasticsearch index name is
  the name of the *Index* plus the id of the *IndexVersion*
  model: `course_search-1`. When the schema is changed, a new
  *IndexVersion* is added with name `course_search-2`, etc.

- **IndexAction** - a recorded action that changes an *Index* or its
  children, such as updating the index or changing which *IndexVersion*
  is active in an *Index*.


### Management Commands

Use `./manage.py es --help` to see the list of all of these commands.


#### Read Only Commands

- `./manage.py es_list`
    - help: For each *Index*, list activation status and doc
      count for each of its *IndexVersions*
    - usage: `./manage.py es_list`


#### Action Commands

These management commands add an Action record in the database,
so that the history of each *Index* is recorded.

- `./manage.py es_create` - create a new index.
- `./manage.py es_activate` - "activate" a new index version. all 
  updates and reads for that index by default will go to that version.
- `./manage.py es_update` - update the documents in the index. 
- `./manage.py es_clear` - remove the documents from an index.
- `./manage.py es_drop` - drop an index.

For each of these, use `--help` to see the details.


### Usage

#### Installation
0. Ensure that Elasticsearch 6.0 or later is accessible, and you have 
   configured a singleton client in `path.to.your.es_client`.
1. Put a reference to this package in your `requirements.txt`:
   `-e git://github.com/HBS-HBX/django_elastic_migrations.git#egg=django_elastic_migrations`
   1. if you like, you can pin to a specific relase:
      `-e git://github.com/HBS-HBX/django_elastic_migrations.git@0.5.1#egg=django_elastic_migrations`
2. Add `django_elastic_migrations` to `INSTALLED_APPS` in your Django
   settings file
3. Add the following information to your Django settings file:
   ```
   DJANGO_ELASTIC_MIGRATIONS_ES_CLIENT = "path.to.your.singleton.ES_CLIENT"
   # optional, any unique number for your releases to associate with indexes
   DJANGO_ELASTIC_MIGRATIONS_GET_CODEBASE_ID = subprocess.check_output(['git', 'describe', "--tags"]).strip()
   # optional, can be used to have multiple servers share the same 
   # elasticsearch instance without conflicting
   DJANGO_ELASTIC_MIGRATIONS_ENVIRONMENT_PREFIX = "qa1_"
   ```
4. Create the `django_elastic_migrations` tables by running `./manage.py migrate`
5. Create an `DEMIndex`:
   ```
   from django_elastic_migrations.indexes import DEMIndex, DEMDocType
   from models import GoogleSearch
   from elasticsearch_dsl import Text
   
    GoogleIndex = DEMIndex('google')


    @GoogleIndex.doc_type
    class GoogleSearchDoc(DEMDocType):
        text = TEXT_COMPLEX_ENGLISH_NGRAM_METAPHONE

        @classmethod
        def get_queryset(self, last_updated_datetime=None):
            """
            return a queryset or a sliceable list of items to pass to 
            get_reindex_iterator
            """
            qs = GoogleSearch.objects.all()
            if last_updated_datetime:
                qs.filter(last_modified__gt=last_updated_datetime)
            return qs

        @classmethod
        def get_reindex_iterator(self, queryset):
            return [
                GoogleSearchDoc(
                    text="a little sample text").to_dict(
                    include_meta=True) for g in queryset]   
   ```

6. Add your new index to DJANGO_ELASTIC_MIGRATIONS_INDEXES in settings/common.py

7. Run `./manage.py es_list` to see the index as available:
    ```
    ./manage.py es_list
    
    Available Index Definitions:
    +----------------------+-------------------------------------+---------+--------+-------+-----------+
    |   Index Base Name    |         Index Version Name          | Created | Active | Docs  |    Tag    |
    +======================+=====================================+=========+========+=======+===========+
    | google               |                                     | 0       | 0      | 0     | Current   |
    |                      |                                     |         |        |       | (not      |
    |                      |                                     |         |        |       | created)  |
    +----------------------+-------------------------------------+---------+--------+-------+-----------+
    Reminder: an index version name looks like 'my_index-4', and its base index name 
    looks like 'my_index'. Most Django Elastic Migrations management commands 
    take the base name (in which case the activated version is used) 
    or the specific index version name.
    ```
8. Create the course_search index in elasticsearch with `./manage.py es_create google`:
    ```
    $> ./manage.py es_create google
    The doc type for index 'google' changed; created a new index version 
    'course_search-1' in elasticsearch.
    $> ./manage.py es_list
    
    Available Index Definitions:
    +----------------------+-------------------------------------+---------+--------+-------+-----------+
    |   Index Base Name    |         Index Version Name          | Created | Active | Docs  |    Tag    |
    +======================+=====================================+=========+========+=======+===========+
    | google               | google-1                            | 1       | 0      | 0     | 07.11.005 |
    |                      |                                     |         |        |       | -93-gd101 |
    |                      |                                     |         |        |       | a1f       |
    +----------------------+-------------------------------------+---------+--------+-------+-----------+

    Reminder: an index version name looks like 'my_index-4', and its base index name 
    looks like 'my_index'. Most Django Elastic Migrations management commands 
    take the base name (in which case the activated version is used) 
    or the specific index version name.
    ```
9. Activate the `course_search-1` index version, so all updates and 
   reads go to it.
    ```
    ./manage.py es_activate course_search
    For index 'course_search', activating 'course_search-1' because you said so.
    ```
10. Assuming you have implemented `get_reindex_iterator`, you can call 
   `./manage.py es_update` to update the index.
    ```
    $> ./manage.py es_update course_search
    
    Handling update of index 'course_search' using its active index version 'course_search-1'
    Checking the last time update was called: 
     - index version: course_search-1 
     - update date: never 
    Getting Reindex Iterator...
    Completed with indexing google-1       
    
    $> ./manage.py es_list
    
    Available Index Definitions:
    +----------------------+-------------------------------------+---------+--------+-------+-----------+
    |   Index Base Name    |         Index Version Name          | Created | Active | Docs  |    Tag    |
    +======================+=====================================+=========+========+=======+===========+
    | google               | google-1                            | 1       | 1      | 3     | 07.11.005 |
    |                      |                                     |         |        |       | -93-gd101 |
    |                      |                                     |         |        |       | a1f       |
    +----------------------+-------------------------------------+---------+--------+-------+-----------+
    ```

### Deployment
- Creating and updating indexes can happen long in advance of deployment,
  just use the management commands as above and don't use es_activate
- During deployment, if `get_reindex_iterator` is implemented correctly,
  it will only reindex those documents that have changed *since the last
  reindexing*
- After deployment and before going live, activate the latest index.
- After activating, be sure to cycle your gunicorn workers.


### Integration Testing
1. (optional) update `DJANGO_ELASTIC_MIGRATIONS_ENVIRONMENT_PREFIX` in
   your Django settings. The default test prefix is `test_`.  Every
   test will create its own indexes.
    ```
    if 'test' in sys.argv:
        DJANGO_ELASTIC_MIGRATIONS_ENVIRONMENT_PREFIX = 'test_'
    ```
2. Override TestCase - `test_utilities.py`
    ```
    from django_elastic_migrations import DEMIndexManager

    class MyTestCase(TestCase):
    
        def _pre_setup(self):
            DEMIndexManager.test_pre_setup()
            super(MyTestCase, self)._pre_setup()

        def _post_teardown(self):
            DEMIndexManager.test_post_teardown()
            super(HBXTestCase, self)._post_teardown()
    ```

### Excluding from dumpdata
When calling [django's dumpdata command](https://docs.djangoproject.com/en/2.0/ref/django-admin/#dumpdata),
you likely will want to exclude the database tables used in this app:

```
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
```

### Tuning
By default, `/.manage.py es_update` will divide the result of 
`DEMDocType.get_queryset()` into batches of size `DocType.BATCH_SIZE`. 
Override this number to change the batch size. 

There are many configurable paramters to Elasticsearch's [bulk updater](https://elasticsearch-py.readthedocs.io/en/master/helpers.html?highlight=bulk#elasticsearch.helpers.streaming_bulk).
To provide a custom value, override `DEMDocType.get_bulk_indexing_kwargs()`
and return the kwargs you would like to customize.


## Development

This project uses `make` to manage the build process. Type `make help`
to see the available `make` targets.

### Requirements

Then, `make requirements` runs the pip install. 

This project also uses [`pip-tools`](https://github.com/jazzband/pip-tools).
The `requirements.txt` files are generated and pinned to latest versions 
with `make upgrade`. 

### Updating Egg Info

To update the `egg-info` directory, run `python setup.py egg_info`


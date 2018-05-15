class DjangoElasticMigrationsException(Exception):
    """A generic exception for all others to extend."""
    pass


class IllegalDEMIndexState(DjangoElasticMigrationsException):
    """
    Raised when a DEMIndex is misconfigured
    """


class DEMCannotCreateUnchangedIndexException(DjangoElasticMigrationsException):
    """
    Raised when a request is made to create an index, and the index has not changed.
    """
    pass


class DEMIndexNotFound(DjangoElasticMigrationsException):
    """
    Raised when a reference is made to an DEMIndex subclass that is not found.
    For example, if `./manage.py es_create course_search` is called,
    The following must appear in the django user's code:

        class MyIndex(DEMIndex):
            name = "course_search"`

    importable somewhere.
    """
    pass


class NoActiveIndexVersion(DjangoElasticMigrationsException):
    """
    Raised when updating an index that has no index version
    """


class NoCreatedIndexVersion(DjangoElasticMigrationsException):
    """
    Raised when attempting to activate an index that has no index version
    """


class IndexNamePropertyCannotBeSet(DjangoElasticMigrationsException):
    """
    Raised when attempting to set the self._name property on an
    Elasticsearch Index.
    """


class DEMDocTypeRequiresGetReindexIterator(DjangoElasticMigrationsException):
    """
    Raised when ./manage.py es_update tries to call DEMDocType.get_reindex_iterator()
    on a subclass, but the subclass has not implemented this.
    """
    message = ("To run ./manage.py es_update my_index, my_index needs to "
               "implement get_reindex_iterator")

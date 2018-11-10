from django.core.management import CommandError


class DjangoElasticMigrationsException(Exception):
    """A generic exception for all others to extend."""


class DjangoElasticMigrationsCommandError(CommandError):
    """A generic command error for others to extend."""


class FirstMigrationNotRunError(DjangoElasticMigrationsException):
    """
    Raised if a the system attempts to use Django Elastic Migrations
    without first running the app's initial migration
    """
    message = "Please run ./manage.py migrate before using Django Elastic Migrations."


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
               "implement DEMDocType.get_reindex_iterator(self, last_updated_datetime=None)")


class DEMDocTypeRequiresGetQueryset(DjangoElasticMigrationsException):
    """
    Raised when ./manage.py es_update tries to call DEMDocType.get_queryset()
    on a subclass, but the subclass has not implemented this.
    """
    message = ("To run ./manage.py es_update my_index, my_index needs to "
               "implement DEMDocType.get_queryset()")


class DEMIndexVersionCodebaseMismatchError(DjangoElasticMigrationsException):
    """
    Raised when calling ./manage.py es_update, and the json hash of the
    index in the codebase differs from the json hash of the index version
    that update would be called on.
    """


class CannotDropActiveVersionWithoutForceArg(DjangoElasticMigrationsException):
    """
    Raised when a user requests to drop an index that is activated without force arg
    """
    message = (
        "Please run ./manage.py es_activate to activate another index "
        "before dropping this one, or use the `--force` flag."
    )


class CannotDropAllIndexesWithoutForceArg(DjangoElasticMigrationsCommandError):
    """
    Raised when a user requests to drop all indexes without force arg
    """


class IndexVersionRequired(DjangoElasticMigrationsException):
    """
    Raised when a command requires an index version to be specified.
    """


class CannotDropOlderIndexesWithoutForceArg(DjangoElasticMigrationsCommandError):
    """
    Raised when a user attempts to call `./manage.py es_drop {indexname} --older`
    without the required `--force` argument
    """
    message = (
        "Please run ./manage.py es_drop {indexname} --older --force to delete all "
        "older versions. You were missing the --force argument."
    )

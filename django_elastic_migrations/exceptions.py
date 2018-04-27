
class DjangoElasticMigrations(Exception):
    """A generic exception for all others to extend."""
    pass


class ESIndexNotFound(DjangoElasticMigrations):
    """Raised when a named index is not found."""
    pass

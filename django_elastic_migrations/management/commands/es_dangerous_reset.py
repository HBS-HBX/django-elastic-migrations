from django.core.management import call_command

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand
from django_elastic_migrations.utils.log import get_logger


logger = get_logger()


class Command(ESCommand):
    help = (
        "django-elastic-migrations: dangerously reset all elasticsearch indexes "
        "WITHOUT PROMPT. \n"
        "warning 1: will drop all elasticsearch indexes available \n"
        "warning 2: not tested with environment prefix; do not used with multiplexed cluster! "
    )

    def handle(self, *args, **options):
        msg = "Dangerously resetting all Elasticsearch indexes in ./manage.py es_dangerous_reset!"
        logger.warning(msg)
        # drop known versions of indexes
        call_command('es_drop', all=True, force=True)
        # drop any remaining versions
        call_command('es_drop', all=True, force=True, es_only=True)
        DEMIndexManager.initialize(
            create_versions=True, activate_versions=True)


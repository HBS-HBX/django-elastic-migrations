from django.core.management import call_command

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand
from django_elastic_migrations.models import Index
from django_elastic_migrations.utils.django_elastic_migrations_log import get_logger

logger = get_logger()


class Command(ESCommand):
    help = (
        "django-elastic-migrations: dangerously reset all elasticsearch indexes "
        "WITHOUT PROMPT. \n"
        "warning 1: will drop ALL ELASTICSEARCH INDEXES AVAILABLE \n"
        "warning 2: may ERASE MANAGEMENT COMMAND HISTORY \n"
        "warning 3: not tested with environment prefix; do not in a multiplexed cluster! \n"
        ""
        "When used with --es-only, will instead drop and recreate indexes in elasticsearch \n"
        "from the schemas stored in the django_elastic_migrations_indexversion \n"
        "table in the database."
    )

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser, include_exact=False)
        parser.add_argument(
            '--es-only', action='store_true',
            help='Sync index schemas from the database to elasticsearch'
        )

    def handle(self, *args, **options):
        es_only = options.get('es_only')

        if es_only:
            msg = "Dangerously resetting Elasticsearch indexes from database in ./manage.py es_dangerous_reset --es-only!"
            logger.warning(msg)
        else:
            msg = "Dangerously resetting Elasticsearch indexes in ./manage.py es_dangerous_reset!"
            logger.warning(msg)
            # drop known versions of indexes
            call_command('es_drop', all=True, force=True)

        # drop any remaining versions in elasticsearch
        call_command('es_drop', all=True, force=True, es_only=True)

        if es_only:
            # recreate each index in elasticsearch
            call_command('es_create', all=True, es_only=True)

        else:
            Index.objects.all().delete()
            DEMIndexManager.initialize(create_versions=True, activate_versions=True)

import logging
from django.core.management import call_command

from django_elastic_migrations.management.commands.es import ESCommand

logger = logging.getLogger("django-elastic-migrations")

class Command(ESCommand):
    help = "django-elastic-migrations: dangerously reset all indexes"

    def handle(self, *args, **options):
        msg = "Dangerously resetting all Elasticsearch indexes in ./manage.py es_dangerous_reset!"
        logger.warning(msg)
        print msg
        call_command('es_drop', all=True, force=True)
        call_command('es_create', all=True)
        call_command('es_activate', all=True)

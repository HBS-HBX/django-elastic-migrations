from django.core.management import call_command

from django_elastic_migrations.management.commands.es import ESCommand
from django_elastic_migrations.utils.log import getLogger


logger = getLogger()


class Command(ESCommand):
    help = "django-elastic-migrations: dangerously reset all indexes WITHOUT PROMPT"

    def handle(self, *args, **options):
        msg = "Dangerously resetting all Elasticsearch indexes in ./manage.py es_dangerous_reset!"
        logger.warning(msg)
        call_command('es_drop', all=True, force=True)
        call_command('es_create', all=True)
        call_command('es_activate', all=True)

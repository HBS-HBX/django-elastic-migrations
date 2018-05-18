from django.core.management import call_command

from django_elastic_migrations.management.commands.es import ESCommand


class Command(ESCommand):
    help = "django-elastic-migrations: dangerously reset all indexes"

    def handle(self, *args, **options):
        call_command('es_drop', all=True, force=True)
        call_command('es_create', all=True)
        call_command('es_activate', all=True)

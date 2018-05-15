from django.core.management import call_command

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand


class Command(ESCommand):
    help = "django-elastic-migrations: update an index"

    def add_arguments(self, parser):
        parser.add_argument(
            'index', nargs='+',
            help='Name of an index'
        )
        parser.add_argument(
            "-ls", "--list-available", action='store_true',
            help='List the available named indexes'
        )

    def handle(self, *args, **options):
        if options.get('list_available'):
            call_command('es_list')
            return
        indexes_to_update = options.get('index', [])
        if indexes_to_update:
            for index_name in indexes_to_update:
                DEMIndexManager.update_index(index_name)
        else:
            DEMIndexManager.update_index(None, all=True)

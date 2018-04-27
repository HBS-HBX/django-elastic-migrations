from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = "django-elastic-migrations: base command for search index management"

    def add_arguments(self, parser):
        parser.add_argument(
            'index', nargs='*',
            help='Name of an index'
        )
        parser.add_argument(
            "-ls", "--list-available", action='store_true',
            help='List the available named indexes (same as es_list)'
        )
        parser.add_argument(
            "--create", action='store_true', default=False,
            help='List the available named indexes'
        )

    def handle(self, *args, **options):
        if 'list_available' in options:
            call_command('es_list')


ESCommand = Command

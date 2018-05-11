from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = "django-elastic-migrations: base command for search index management"

    def __init__(self):
        super(Command, self).__init__()
        print ""

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
            help='Create the named index'
        )
        parser.add_argument(
            "--update", action='store_true', default=False,
            help='Update the named index'
        )
        parser.add_argument(
            "--activate", action='store_true', default=False,
            help='Activate the latest version of the named index'
        )

    def handle(self, *args, **options):
        if 'list_available' in options:
            call_command('es_list', *args, **options)
        if 'create' in options:
            call_command('es_create', *args, **options)
        if 'update' in options:
            call_command('es_update', *args, **options)
        if 'activate' in options:
            call_command('activate', *args, **options)


ESCommand = Command

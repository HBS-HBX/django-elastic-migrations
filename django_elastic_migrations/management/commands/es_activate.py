from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand


class Command(ESCommand):
    help = "django-elastic-migrations: activate an index"

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser)
        parser.add_argument(
            '--deactivate', action='store_true',
            help="Deactivate the named version"
        )

    def handle(self, *args, **options):
        indexes, use_version_mode, apply_all = self.get_index_specifying_options(options)
        deactivate = options.get('deactivate', False)

        if apply_all:
            DEMIndexManager.activate_index(
                'all',
                use_version_mode=use_version_mode,
                deactivate=deactivate
            )
        elif indexes:
            for index_name in indexes:
                DEMIndexManager.activate_index(
                    index_name,
                    use_version_mode=use_version_mode,
                    deactivate=deactivate
                )

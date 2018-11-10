from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand


class Command(ESCommand):
    help = "django-elastic-migrations: activate an index"

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser)

    def handle(self, *args, **options):
        indexes, exact_mode, apply_all, _, _ = self.get_index_specifying_options(options)

        if apply_all:
            DEMIndexManager.activate_index(
                'all',
                exact_mode=exact_mode,
            )
        elif indexes:
            for index_name in indexes:
                DEMIndexManager.activate_index(
                    index_name,
                    exact_mode=exact_mode,
                )

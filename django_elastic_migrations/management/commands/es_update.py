from django.core.management import call_command

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand


class Command(ESCommand):
    help = "django-elastic-migrations: update an index"

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser, include_newer=True)

    def handle(self, *args, **options):
        indexes, exact_mode, apply_all, _, newer_mode = self.get_index_specifying_options(options)

        if apply_all:
            DEMIndexManager.update_index(
                'all',
                exact_mode=exact_mode,
                newer_mode=newer_mode
            )
        elif indexes:
            for index_name in indexes:
                DEMIndexManager.update_index(
                    index_name,
                    exact_mode=exact_mode,
                    newer_mode=newer_mode
                )

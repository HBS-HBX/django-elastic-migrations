from django.core.management import call_command

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand


class Command(ESCommand):
    help = "django-elastic-migrations: update an index"

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser, include_newer=True)
        parser.add_argument(
            '--resume', action='store_true',
            help=("Only update documents that have changed since "
                  "the last ./manage.py es_update. NOTE: DEMDocType subclass "
                  "needs to implement this.")
        )

    def handle(self, *args, **options):
        indexes, exact_mode, apply_all, _, newer_mode = self.get_index_specifying_options(options)
        resume_mode = options.get('resume', False)

        if apply_all:
            DEMIndexManager.update_index(
                'all',
                exact_mode=exact_mode,
                newer_mode=newer_mode,
                resume_mode=resume_mode
            )
        elif indexes:
            for index_name in indexes:
                DEMIndexManager.update_index(
                    index_name,
                    exact_mode=exact_mode,
                    newer_mode=newer_mode,
                    resume_mode=resume_mode
                )

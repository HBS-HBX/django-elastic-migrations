from __future__ import print_function

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand
from django_elastic_migrations.utils.multiprocessing_utils import USE_ALL_WORKERS


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
        parser.add_argument(
            '--workers', nargs="?",
            default=0,
            const=USE_ALL_WORKERS,
            help=(
                "Allows for using multiple workers to parallelize indexing. \n"
                "To use all available workers, simply supply --workers. \n"
                "To use a certain number of workers, supply --workers 8. \n"
                "If this option is used, it is recommended to implement and add \n"
                "DJANGO_ELASTIC_MIGRATIONS_CLOSE_CONNECTIONS and "
                "DJANGO_ELASTIC_MIGRATIONS_RECREATE_CONNECTIONS function paths to your Django settings."
            )
        )
        parser.add_argument(
            '--batch_size', nargs='?', default=0, type=int,
            help=(
                "Determines the number of documents to index per batch, used for \n"
                "tuning memory."
                "Manually overrides the BATCH_SIZE specified on the index. \n"
            )
        )

    def handle(self, *args, **options):
        indexes, exact_mode, apply_all, _, newer_mode = self.get_index_specifying_options(options)
        resume_mode = options.get('resume', False)
        workers = options.get('workers')
        batch_size = options.get('batch_size', 0)

        if apply_all:
            DEMIndexManager.update_index(
                'all',
                exact_mode=exact_mode,
                newer_mode=newer_mode,
                resume_mode=resume_mode,
                workers=workers,
                batch_size=batch_size
            )
        elif indexes:
            for index_name in indexes:
                DEMIndexManager.update_index(
                    index_name,
                    exact_mode=exact_mode,
                    newer_mode=newer_mode,
                    resume_mode=resume_mode,
                    workers=workers,
                    batch_size=batch_size
                )

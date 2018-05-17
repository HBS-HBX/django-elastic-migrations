import logging
from django.core.management import CommandError

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand


class Command(ESCommand):
    help = "django-elastic-migrations: drop indexes"

    def add_arguments(self, parser):
        self.get_index_specifying_arguments(parser)
        parser.add_argument(
            '--es-only', action='store_true',
            help="Only drop indexes in elasticsearch (!) "
                 "(probably not what you want, just useful for debugging)"
        )

    def handle(self, *args, **options):
        indexes, use_version_mode, apply_all = self.get_index_specifying_options(
            options, require_one_include_list=['es_only'])
        es_only = options.get('es_only', False)

        if es_only:
            count = 0
            for index_name in indexes:
                print "Dropping index {} from Elasticsearch only".format(index_name)
                DEMIndexManager.delete_es_created_index(index_name, ignore=[400, 404])
                count += 1
            print "Completed dropping {} indexes from Elasticsearch only".format(count)
        elif apply_all:
            DEMIndexManager.drop_index(
                'all',
                use_version_mode=use_version_mode,
            )
        elif indexes:
            for index_name in indexes:
                DEMIndexManager.drop_index(
                    index_name,
                    use_version_mode=use_version_mode
                )

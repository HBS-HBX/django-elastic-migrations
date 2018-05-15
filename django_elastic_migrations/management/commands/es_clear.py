from django.core.management import CommandError

from django_elastic_migrations import DEMIndexManager
from django_elastic_migrations.management.commands.es import ESCommand

MODE_INDEXES = 'index'
MODE_VERSIONS = 'version'


class Command(ESCommand):
    help = "django-elastic-migrations: clear documents from elasticsearch indexes"

    def add_arguments(self, parser):
        # group = parser.add_mutually_exclusive_group(required=True)
        parser.add_argument(
            "-m", "--mode",
            help="Specify whether to operate on indexes or index versions",
            choices=[MODE_INDEXES, MODE_VERSIONS],
            default=MODE_INDEXES
        )
        parser.add_argument(
            'index', nargs='*',
            help=(
                "Depending on --mode, the name of index(es) or index version(s) "
                "to clear. In the case of `--mode {mode_indexes}` (the default), the active version "
                "will be cleared, and indexes without an active version will be "
                "ignored.".format(mode_indexes=MODE_INDEXES)
            )
        )
        parser.add_argument(
            "-a", "--all", action='store_true', default=False,
            help=(
                'Clear all of the active indexes or index versions, depending on '
                'whether `--mode {mode_index}`, or `--mode {mode_version}` is '
                'supplied.'.format(mode_index=MODE_INDEXES, mode_version=MODE_VERSIONS)
            )
        )

    def handle(self, *args, **options):
        mode = options.get('mode', MODE_INDEXES)
        use_version_mode = mode == MODE_VERSIONS
        indexes = options.get('index', [])
        apply_all = options.get('all', False)

        if apply_all:
            DEMIndexManager.clear_index(
                'all',
                use_version_mode=use_version_mode,
            )
        if indexes:
            for index_name in indexes:
                DEMIndexManager.clear_index(
                    index_name,
                    use_version_mode=use_version_mode
                )
        else:
            raise CommandError(
                "At least one {mode} or --all must be specified".format(
                    mode=mode
                ))

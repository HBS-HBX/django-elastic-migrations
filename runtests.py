import os
import sys
import argparse

try:
    from django.conf import settings, global_settings
    from django.test.utils import get_runner

    def get_settings():
        import test_settings
        settings.configure(global_settings, **test_settings.__dict__)

        # in newer versions of django you have to call .setup() directly
        try:
            import django
            setup = django.setup
        except AttributeError:
            pass
        else:
            setup()

        return settings

except ImportError:
    import traceback
    traceback.print_exc()
    msg = "To fix this error, run: pip install -r requirements_test.txt or make sure your virtualenv is activated"
    raise ImportError(msg)


def make_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--elasticsearch',
        nargs='?',
        metavar='localhost:9200',
        const='localhost:9200',
        help="To run integration test against an Elasticsearch server",
    )
    return parser


def run_tests(*test_args):
    args, test_args = make_parser().parse_known_args(test_args)
    if args.elasticsearch:
        os.environ.setdefault('ELASTICSEARCH_URL', args.elasticsearch)

    if not test_args:
        test_args = ['tests']

    settings = get_settings()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()

    failures = test_runner.run_tests(test_args)

    if failures:
        sys.exit(bool(failures))


if __name__ == '__main__':
    run_tests(*sys.argv[1:])
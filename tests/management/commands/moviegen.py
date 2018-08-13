from __future__ import (absolute_import, division, print_function, unicode_literals)

import os

from django.core.management import BaseCommand, call_command

from tests.models import Movie
from tests.omdb_api import OmdbAPIQuery, OmdbAPIError, OmdbAPIMovieNotFoundError


class Command(BaseCommand):
    help = """
    Generate movies for use in test database
    """

    def add_arguments(self, parser):
        parser.add_argument(
            '--title',
            action='append',
            help='Specify one or more movie titles in quotes: --title="Star Wars" --title="Memento"',
        )
        parser.add_argument(
            '--file',
            help='Specify a text file with a title on each line: --file="tests/100films.txt"',
        )
        parser.add_argument(
            '--api-key',
            default=os.environ.get('OMDB_API_KEY', 'Get your own from https://www.omdbapi.com/apikey.aspx'),
            help='Specify one or more movie titles in quotes: --titles "Star Wars" "Memento"',
        )
        parser.add_argument(
            '--noprint',
            action='store_true',
            default=False,
            help='Print results out',
        )
        parser.add_argument(
            '--save',
            action='store_true',
            default=False,
            help='Save resuts to the database in the Movies collection',
        )
        parser.add_argument(
            '--makefixture',
            help='Dump fixture data to a json file',
        )

    def handle(self, *args, **options):
        created_movies = []

        titles = options['title'] or []

        if options['file']:
            with open(options['file'], 'r') as movies_file:
                titles = movies_file.read().splitlines()

        titles_we_already_have = Movie.objects.filter(title__in=titles).values_list('title', flat=True)
        new_titles = list(set(titles) - set(titles_we_already_have))
        for title in new_titles:
            query = OmdbAPIQuery(title=title, api_key=options['api_key'])
            if not options['noprint']:
                query.print_resuts()
            if options['save']:
                try:
                    movie, created = Movie.save_movie_from_omdb_query(query)
                    if created:
                        created_movies.append(movie.title)
                    else:
                        print("{} was already in the database".format(movie.title))
                except OmdbAPIMovieNotFoundError:
                    print("Omdb API Movie Not Found Error: '{}'".format(title))
                    continue
                except OmdbAPIError as oae:
                    print("Omdb API Movie Error while looking up '{}'\n{}".format(title, str(oae)))
                    continue
                except Exception as ex:
                    print("Caught exception while looking up '{}':\n{}".format(title, str(ex)))

        if options['save']:
            if created_movies:
                print("Saved {} new movie(s) to the database: {}".format(len(created_movies), "\n - ".join(created_movies)))
            else:
                print("No movies created.")

        if options['makefixture']:
            fixture_path = options['makefixture']
            print("dumping fixture data to {} ...".format(fixture_path))

            params = {
                'database': 'default',
                'exclude': [
                    'contenttypes', 'auth.Permission',
                    # don't include django_elastic_migrations in dumpdata, since it's environment specific
                    'django_elastic_migrations.index',
                    'django_elastic_migrations.indexversion',
                    'django_elastic_migrations.indexaction'
                ],
                'indent': 3,
                'output': fixture_path
            }
            call_command('dumpdata', **params)

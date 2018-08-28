from django.core.management.base import BaseCommand, CommandError
import imp
import sys

class Command(BaseCommand):
    help = 'Run a script'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('args', nargs='*')

    def handle(self, *args, **options):
        sys.argv = tuple([options['path']] + list(args))
        imp.load_source('__main__', options['path'])

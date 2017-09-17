from django.core.management.base import BaseCommand, CommandError
import imp

class Command(BaseCommand):
    help = 'Run a script'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, *args, **options):
        imp.load_source('_ignore', options['path'])

from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Run a script'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, *args, **options):
        execfile(options['path'])

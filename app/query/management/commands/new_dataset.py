from django.core.management.base import BaseCommand
import subprocess as sp
import shlex


class Command(BaseCommand):
    help = 'Create scaffolding for a new dataset'

    def add_arguments(self, parser):
        parser.add_argument('dataset')

    def handle(self, *args, **options):
        sp.check_call(
            shlex.split('cp -r query/management/commands/dataset_template query/datasets/{}'.format(
                options['dataset'])))

        print(('Dataset {dataset} successfully created at query/datasets/{dataset}'.format(
            dataset=options['dataset'])))

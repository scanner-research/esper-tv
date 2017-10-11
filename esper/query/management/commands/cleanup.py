from django.core.management.base import BaseCommand
from query.base_models import ModelDelegator
import os

models = ModelDelegator(os.environ.get('DATASET'))

class Command(BaseCommand):
    help = 'Remove rows from the database, e.g. python manage.py cleanup Concept'

    def add_arguments(self, parser):
        parser.add_argument('table')
        parser.add_argument('--id', default=None)

    def handle(self, *args, **options):
        model = getattr(models, options['table'])
        id = options['id']
        if id is None:
            model.objects.all().delete()
        else:
            models.objects.filter(id=id).delete()

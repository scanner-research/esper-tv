from esper.prelude import *
from esper.spark import *
import django.apps
import os

models = [m._meta.db_table for m in django.apps.apps.get_models(include_auto_created=True)]

# with Timer('Exporting models'):
#     def export_model(model):
#         try:
#             sp.check_call("/app/scripts/export-table.sh {}".format(model), shell=True)
#         except Exception:
#             import traceback
#             print(model)
#             traceback.print_exc()
#     par_for(export_model, models, workers=8)

with Timer('Ingest into Spark'):
    def transfer_model_spark(model):
        if os.path.exists('/app/data/pg/{}.csv'.format(model)):
            df = spark.load_csv('/app/data/pg/{}.csv'.format(model))
            spark.save(model, df)
    par_for(transfer_model_spark, models, workers=8)

# with Timer('Ingest into BigQuery'):
#     sp.check_call('bq rm -r -f tvnews && bq mk tvnews', shell=True)
#     def transfer_model_bq(model):
#         try:
#             sp.check_call("/app/scripts/transfer-to-bigquery.sh {}".format(model), shell=True)
#         except Exception:
#             import traceback
#             print(model)
#             traceback.print_exc()
#     par_for(transfer_model_bq, models, workers=8)

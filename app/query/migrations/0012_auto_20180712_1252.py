# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2018-07-12 12:52
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('query', '0011_auto_20180625_1157'),
    ]

    operations = [
        migrations.AlterField(
            model_name='faceidentity',
            name='probability',
            field=models.FloatField(db_index=True, default=1.0),
        ),
    ]

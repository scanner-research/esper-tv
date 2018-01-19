# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2018-01-18 14:58
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('query', '0014_tvnews_frame_tags'),
    ]

    operations = [
        migrations.AddField(
            model_name='tvnews_face',
            name='shot',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_query_name='face', to='query.tvnews_Shot'),
        ),
    ]
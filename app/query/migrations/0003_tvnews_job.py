# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2018-05-11 11:22
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('query', '0002_tvnews_face_blurriness'),
    ]

    operations = [
        migrations.CreateModel(
            name='tvnews_Job',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=256)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
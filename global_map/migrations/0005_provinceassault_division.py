# -*- coding: utf-8 -*-
# Generated by Django 1.10.3 on 2016-12-06 17:18
from __future__ import unicode_literals

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('global_map', '0004_provinceassault_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='provinceassault',
            name='division',
            field=django.contrib.postgres.fields.jsonb.JSONField(null=True),
        ),
    ]

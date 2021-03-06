# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.contrib.auth.models import Group


def add_staff_group(apps, schema_editor):
	Group.objects.create(name="Staff")


class Migration(migrations.Migration):

	dependencies = [
		('main', '0001_initial'),
	]

	operations = [
		migrations.RunPython(add_staff_group),
	]

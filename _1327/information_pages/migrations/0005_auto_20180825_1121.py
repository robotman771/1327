# Generated by Django 2.0.8 on 2018-08-25 09:21

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('information_pages', '0004_auto_20180825_1114'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='informationdocument',
            options={'base_manager_name': 'objects', 'permissions': (('view_informationdocument', 'User/Group is allowed to view that document'),), 'verbose_name': 'Information document', 'verbose_name_plural': 'Information documents'},
        ),
    ]

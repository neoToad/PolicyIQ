# Generated manually on 2026-05-30

from django.db import migrations, models

import documents.models


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0004_remove_file_path_make_file_required"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="document",
            name="file_path",
        ),
        migrations.AlterField(
            model_name="document",
            name="file",
            field=models.FileField(upload_to=documents.models._document_upload_path),
        ),
    ]

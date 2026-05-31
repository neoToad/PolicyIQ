# Generated manually on 2026-05-30

from django.db import migrations


def delete_documents_without_files(apps, schema_editor):
    """Delete any documents that have no file — these are orphaned records
    whose original files are no longer on disk after the file_path -> file migration."""
    Document = apps.get_model("documents", "Document")
    for doc in Document.objects.filter(file__isnull=True).iterator():
        # Manually delete related chunks to avoid deferred trigger issues.
        Chunk = apps.get_model("documents", "Chunk")
        Chunk.objects.filter(document=doc).delete()
        doc.delete()


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("documents", "0003_migrate_file_path_to_file"),
    ]

    operations = [
        migrations.RunPython(delete_documents_without_files, migrations.RunPython.noop),
    ]

from __future__ import annotations

from django.db import migrations

BLOCK_TYPES = (
    ("markdown", "Markdown"),
    ("image", "Image"),
    ("callout", "Callout"),
)


def seed_block_types(apps, schema_editor):
    ContentBlockType = apps.get_model("content", "ContentBlockType")
    for key, title in BLOCK_TYPES:
        ContentBlockType.objects.update_or_create(
            key=key,
            defaults={"title": title, "active": True},
        )


def unseed_block_types(apps, schema_editor):
    ContentBlockType = apps.get_model("content", "ContentBlockType")
    ContentBlockType.objects.filter(key__in=[key for key, _ in BLOCK_TYPES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_block_types, unseed_block_types),
    ]
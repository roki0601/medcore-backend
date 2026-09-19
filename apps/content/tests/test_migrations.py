from __future__ import annotations

import importlib

from django.apps import apps as django_apps

from apps.content.models import ContentBlockType


def test_seed_migration_creates_the_mvp_block_types(db):
    ContentBlockType.objects.all().delete()
    module = importlib.import_module(
        "apps.content.migrations.0002_seed_content_block_types"
    )

    module.seed_block_types(django_apps, None)
    module.seed_block_types(django_apps, None)

    assert set(ContentBlockType.objects.values_list("key", flat=True)) == {
        "markdown",
        "image",
        "callout",
    }
    assert ContentBlockType.objects.filter(active=True).count() == 3

from django.db import migrations


def backfill_placeholder_slugs(apps, schema_editor):
    from apps.content.slugs import is_placeholder_slug, latin_base, unique_candidate

    Subject = apps.get_model("content", "Subject")
    Section = apps.get_model("content", "Section")
    Topic = apps.get_model("content", "Topic")

    def rewrite(model, fallback: str) -> None:
        rows = list(model.objects.all().only("id", "title", "slug"))
        taken = {row.slug for row in rows}
        for row in rows:
            if not is_placeholder_slug(row.slug):
                continue
            base = latin_base(row.title, fallback=fallback)
            if base == row.slug:
                continue
            taken.discard(row.slug)
            candidate = unique_candidate(base, taken=taken)
            taken.add(candidate)
            row.slug = candidate
            row.save(update_fields=["slug"])

    rewrite(Subject, "subject")
    rewrite(Section, "section")
    rewrite(Topic, "topic")


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0004_subject_topic_cover"),
    ]

    operations = [
        migrations.RunPython(backfill_placeholder_slugs, migrations.RunPython.noop),
    ]

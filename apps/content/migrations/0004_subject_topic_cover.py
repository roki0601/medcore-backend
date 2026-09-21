from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0003_content_api_entities"),
        ("media", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="subject",
            name="cover",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="subject_covers",
                to="media.mediafile",
            ),
        ),
        migrations.AddField(
            model_name="topic",
            name="cover",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="topic_covers",
                to="media.mediafile",
            ),
        ),
    ]

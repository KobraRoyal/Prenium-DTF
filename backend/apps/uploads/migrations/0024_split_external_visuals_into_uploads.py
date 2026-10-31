from django.db import migrations, models


def split_declared_visuals(apps, schema_editor):
    OrderUpload = apps.get_model("uploads", "OrderUpload")
    grouped = OrderUpload.objects.exclude(external_visual_specs=[]).exclude(
        external_visual_specs={}
    )
    for upload in grouped.iterator():
        specs = upload.external_visual_specs
        if not isinstance(specs, list):
            continue
        visuals = [spec for spec in specs if isinstance(spec, dict)]
        if len(visuals) < 2:
            continue
        declared = len(visuals)
        total = int(upload.external_visual_count or declared)
        extra = max(total - declared, 0)
        first = visuals[0]
        upload.original_filename = str(first.get("file_name") or upload.original_filename)[:255]
        upload.quantity = int(first.get("quantity") or 1)
        upload.support_color_hex = str(first.get("support_color_hex") or "")[:16]
        upload.external_visual_count = 1 + extra
        upload.external_visual_specs = []
        upload.save(
            update_fields=[
                "original_filename",
                "quantity",
                "support_color_hex",
                "external_visual_count",
                "external_visual_specs",
                "updated_at",
            ]
        )
        base_sort = int(upload.sort_order or 0)
        for offset, spec in enumerate(visuals[1:], start=1):
            OrderUpload.objects.create(
                order_id=upload.order_id,
                uploaded_by_id=upload.uploaded_by_id,
                file="",
                external_url=upload.external_url,
                external_visual_count=1,
                external_visual_specs=[],
                original_filename=str(spec.get("file_name") or f"Visuel {offset + 1}")[:255],
                mime_type="",
                size_bytes=0,
                sort_order=base_sort + offset,
                quantity=int(spec.get("quantity") or 1),
                support_color_hex=str(spec.get("support_color_hex") or "")[:16],
            )


class Migration(migrations.Migration):
    dependencies = [
        ("uploads", "0023_orderupload_external_visual_specs"),
    ]

    operations = [
        migrations.AlterField(
            model_name="orderupload",
            name="external_visual_specs",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Ancien regroupement. Chaque visuel d’un lien est maintenant un fichier, "
                    "avec sa propre décision Atelier."
                ),
            ),
        ),
        migrations.RunPython(split_declared_visuals, migrations.RunPython.noop),
    ]

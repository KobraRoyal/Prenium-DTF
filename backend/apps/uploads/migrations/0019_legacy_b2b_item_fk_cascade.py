from django.db import migrations


def _rewrite_b2b_item_fk(*, cursor, table_name: str, constraint_name: str, cascade: bool) -> None:
    cursor.execute("SELECT to_regclass(%s)", [table_name])
    if cursor.fetchone()[0] is None:
        return
    cursor.execute(
        "SELECT 1 FROM pg_constraint WHERE conname = %s",
        [constraint_name],
    )
    if cursor.fetchone() is None:
        return

    on_delete = "ON DELETE CASCADE" if cascade else ""
    cursor.execute(f"ALTER TABLE {table_name} DROP CONSTRAINT {constraint_name}")
    cursor.execute(
        f"""
        ALTER TABLE {table_name}
          ADD CONSTRAINT {constraint_name}
          FOREIGN KEY (b2b_item_id)
          REFERENCES b2b_order_projects_b2borderprojectitem(id)
          {on_delete}
          DEFERRABLE INITIALLY DEFERRED
        """
    )


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        _rewrite_b2b_item_fk(
            cursor=cursor,
            table_name="uploads_assetplacementanalysis",
            constraint_name="uploads_assetplaceme_b2b_item_id_83323b18_fk_b2b_order",
            cascade=True,
        )
        _rewrite_b2b_item_fk(
            cursor=cursor,
            table_name="uploads_assethalftonederivative",
            constraint_name="uploads_assethalfton_b2b_item_id_5ca5a5de_fk_b2b_order",
            cascade=True,
        )


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        _rewrite_b2b_item_fk(
            cursor=cursor,
            table_name="uploads_assetplacementanalysis",
            constraint_name="uploads_assetplaceme_b2b_item_id_83323b18_fk_b2b_order",
            cascade=False,
        )
        _rewrite_b2b_item_fk(
            cursor=cursor,
            table_name="uploads_assethalftonederivative",
            constraint_name="uploads_assethalfton_b2b_item_id_5ca5a5de_fk_b2b_order",
            cascade=False,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("uploads", "0018_assetanalysis_large_preview_compat"),
        ("b2b_order_projects", "0005_b2b_item_crop"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

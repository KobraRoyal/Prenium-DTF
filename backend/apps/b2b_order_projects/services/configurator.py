from django.db import transaction

from apps.b2b_order_projects.services.projects import B2BOrderProjectService
from apps.uploads.services.assets import AssetService


class B2BOrderProjectConfiguratorService:
    def __init__(self):
        self.projects = B2BOrderProjectService()
        self.assets = AssetService()

    @transaction.atomic
    def add_visual(self, *, project, actor, data, uploaded_file, source):
        visual_data = data.copy()
        if not str(visual_data.get("name", "")).strip():
            visual_data["name"] = uploaded_file.name.rsplit(".", 1)[0]
        visual_data["width_mm"] = visual_data.get("width_mm") or "1.00"
        visual_data["height_mm"] = visual_data.get("height_mm") or "1.00"
        item = self.projects.add_item(
            project=project,
            actor=actor,
            data=visual_data,
            source=source,
        )
        version = self.assets.attach_project_item_file(
            project=project,
            item_public_id=item.public_id,
            actor=actor,
            uploaded_file=uploaded_file,
            source=source,
            auto_size_requested=True,
        )
        return item, version

    @transaction.atomic
    def complete_visual(
        self,
        *,
        project,
        item_public_id,
        actor,
        data,
        uploaded_file,
        source,
    ):
        item = self.projects.update_item(
            project=project,
            item_public_id=item_public_id,
            actor=actor,
            data=data,
            source=source,
        )
        version = self.assets.attach_project_item_file(
            project=project,
            item_public_id=item.public_id,
            actor=actor,
            uploaded_file=uploaded_file,
            source=source,
            auto_size_requested=True,
        )
        return item, version

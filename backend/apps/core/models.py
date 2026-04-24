import uuid

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PublicIdModel(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    class Meta:
        abstract = True


class BaseModel(PublicIdModel, TimeStampedModel):
    class Meta:
        abstract = True

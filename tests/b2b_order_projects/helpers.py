from io import BytesIO

from apps.customers.models import Customer, CustomerMembership
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageDraw
from reportlab.pdfgen.canvas import Canvas
from rest_framework.test import APIClient


def create_scope(email, name="Client", role=CustomerMembership.Role.MEMBER, enabled=True):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name=name, b2b_order_projects_enabled=enabled)
    CustomerMembership.objects.create(customer=customer, user=user, role=role)
    client = APIClient()
    client.login(email=email, password="pass")
    return user, customer, client


def png_upload(name="logo.png", *, color=(255, 0, 0, 255)):
    output = BytesIO()
    Image.new("RGBA", (120, 80), color).save(output, format="PNG", dpi=(300, 300))
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/png")


def semi_transparent_upload(name="semi-transparent.png", *, color=(255, 0, 0, 180)):
    output = BytesIO()
    Image.new("RGBA", (120, 80), color).save(output, format="PNG", dpi=(300, 300))
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/png")


def thin_detail_upload(name="details-fins.png"):
    output = BytesIO()
    image = Image.new("RGBA", (160, 100), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((15, 45, 145, 48), fill=(10, 10, 10, 255))
    image.save(output, format="PNG", dpi=(300, 300))
    image.close()
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/png")


def pdf_upload(name="document.pdf"):
    output = BytesIO()
    document = Canvas(output, pagesize=(200, 100))
    document.rect(10, 10, 180, 80, fill=1)
    document.showPage()
    document.save()
    return SimpleUploadedFile(name, output.getvalue(), content_type="application/pdf")

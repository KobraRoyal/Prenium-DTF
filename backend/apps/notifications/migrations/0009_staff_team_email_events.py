from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0008_alter_emailtemplate_event"),
    ]

    operations = [
        migrations.AlterField(
            model_name="emailtemplate",
            name="event",
            field=models.CharField(
                choices=[
                    ("order_created", "Commande créée"),
                    ("payment_captured", "Paiement confirmé"),
                    ("order_processing", "Commande en traitement"),
                    ("order_ready_to_ship", "Commande traitée"),
                    ("order_shipped", "Commande expédiée"),
                    ("order_priced", "Commande tarifée"),
                    ("order_awaiting_payment", "Paiement carte à effectuer"),
                    ("file_correction_requested", "Correction fichier demandée"),
                    ("access_request_email_verification", "Vérification demande d'accès"),
                    ("access_request_submitted_internal", "Nouvelle demande d'accès"),
                    ("access_request_approved", "Demande d'accès validée"),
                    ("access_request_rejected", "Demande d'accès refusée"),
                    ("account_activated", "Compte activé"),
                    ("customer_member_invited", "Collaborateur invité"),
                    ("staff_member_invited", "Collaborateur Atelier invité"),
                    ("staff_account_activated", "Accès Atelier activé"),
                    ("password_reset", "Réinitialisation du mot de passe"),
                    ("volume_discount_tier_reached", "Palier de remise atteint"),
                ],
                max_length=48,
                verbose_name="Événement",
            ),
        ),
    ]

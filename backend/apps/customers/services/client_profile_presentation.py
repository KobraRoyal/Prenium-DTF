from __future__ import annotations

from apps.customers.models import Customer, CustomerMembership
from apps.customers.services.client_pricing_overview import CustomerPricingOverviewService
from apps.customers.services.company_profile import CompanyProfileService


class ClientProfilePresentationService:
    """Contexte de lecture du profil client, sans jamais exposer les tarifs hors owner."""

    def __init__(
        self,
        *,
        company_profile: CompanyProfileService | None = None,
        pricing_overview: CustomerPricingOverviewService | None = None,
    ):
        self.company_profile = company_profile or CompanyProfileService()
        self.pricing_overview = pricing_overview or CustomerPricingOverviewService()

    def present(self, *, customer: Customer | None, selected_membership) -> dict[str, object]:
        can_edit_company = bool(
            selected_membership is not None and selected_membership.can_manage_team
        )
        can_view_pricing = bool(
            customer is not None
            and selected_membership is not None
            and selected_membership.role == CustomerMembership.Role.OWNER
        )
        return {
            "can_edit_company": can_edit_company,
            "can_view_pricing": can_view_pricing,
            "company_profile": self.company_profile.present(customer) if customer else None,
            "customer_pricing_overview": (
                self.pricing_overview.present(customer=customer) if can_view_pricing else None
            ),
        }

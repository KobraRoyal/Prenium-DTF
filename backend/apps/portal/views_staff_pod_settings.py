from __future__ import annotations

from django.shortcuts import render
from django.views import View

from apps.pod.services.settings_overview import PodSettingsOverviewService
from apps.portal.views_staff_pod import StaffPodSettingsManagerMixin, _nav

settings_overview_service = PodSettingsOverviewService()


class StaffPodSettingsView(StaffPodSettingsManagerMixin, View):
    template_name = "portal/staff/pod/settings.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            {
                **_nav(),
                "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
                "can_manage_warehouse": request.user.has_perm(
                    "inventory.manage_warehouse"
                ),
                "can_operate_production": request.user.has_perm("pod.operate_pod_production"),
                "settings_overview": settings_overview_service.build(actor=request.user),
            },
        )

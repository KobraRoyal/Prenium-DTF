from apps.b2b_order_projects.models import B2BOrderProject


class B2BOrderProjectTransitionPolicy:
    allowed_transitions = {
        B2BOrderProject.Status.DRAFT: {
            B2BOrderProject.Status.INCOMPLETE,
            B2BOrderProject.Status.READY_TO_SUBMIT,
            B2BOrderProject.Status.CANCELLED,
        },
        B2BOrderProject.Status.INCOMPLETE: {
            B2BOrderProject.Status.READY_TO_SUBMIT,
            B2BOrderProject.Status.CANCELLED,
        },
        B2BOrderProject.Status.READY_TO_SUBMIT: {
            B2BOrderProject.Status.INCOMPLETE,
            B2BOrderProject.Status.SUBMITTED,
            B2BOrderProject.Status.CONVERTED,
            B2BOrderProject.Status.CANCELLED,
        },
        B2BOrderProject.Status.SUBMITTED: {
            B2BOrderProject.Status.UNDER_REVIEW,
            B2BOrderProject.Status.CONVERTED,
        },
        B2BOrderProject.Status.UNDER_REVIEW: {
            B2BOrderProject.Status.CHANGES_REQUESTED,
            B2BOrderProject.Status.PRICE_CONFIRMATION_REQUIRED,
            B2BOrderProject.Status.CONFIRMED,
            B2BOrderProject.Status.BLOCKED,
        },
        B2BOrderProject.Status.CHANGES_REQUESTED: {
            B2BOrderProject.Status.READY_TO_SUBMIT,
            B2BOrderProject.Status.CANCELLED,
        },
        B2BOrderProject.Status.PRICE_CONFIRMATION_REQUIRED: {
            B2BOrderProject.Status.CONFIRMED,
            B2BOrderProject.Status.CANCELLED,
        },
        B2BOrderProject.Status.CONFIRMED: {B2BOrderProject.Status.CONVERTED},
        B2BOrderProject.Status.BLOCKED: {B2BOrderProject.Status.UNDER_REVIEW},
        B2BOrderProject.Status.CONVERTED: set(),
        B2BOrderProject.Status.CANCELLED: set(),
        B2BOrderProject.Status.ANALYZING: {
            B2BOrderProject.Status.ACTION_REQUIRED,
            B2BOrderProject.Status.READY_TO_SUBMIT,
        },
        B2BOrderProject.Status.ACTION_REQUIRED: {
            B2BOrderProject.Status.ANALYZING,
            B2BOrderProject.Status.CANCELLED,
        },
    }

    editable_statuses = {
        B2BOrderProject.Status.DRAFT,
        B2BOrderProject.Status.INCOMPLETE,
        B2BOrderProject.Status.READY_TO_SUBMIT,
        B2BOrderProject.Status.ACTION_REQUIRED,
        B2BOrderProject.Status.CHANGES_REQUESTED,
    }

    client_deletable_statuses = {
        B2BOrderProject.Status.DRAFT,
        B2BOrderProject.Status.INCOMPLETE,
        B2BOrderProject.Status.ANALYZING,
        B2BOrderProject.Status.ACTION_REQUIRED,
        B2BOrderProject.Status.READY_TO_SUBMIT,
        B2BOrderProject.Status.CHANGES_REQUESTED,
        B2BOrderProject.Status.SUBMITTED,
        B2BOrderProject.Status.CANCELLED,
    }

    def can_transition(self, current_status: str, target_status: str) -> bool:
        return target_status in self.allowed_transitions.get(current_status, set())

    def is_editable(self, status: str) -> bool:
        return status in self.editable_statuses

    def can_client_delete(self, project) -> bool:
        if project.converted_order_id or project.status == B2BOrderProject.Status.CONVERTED:
            return False
        return project.status in self.client_deletable_statuses

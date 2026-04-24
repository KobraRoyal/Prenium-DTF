"""Brouillon tunnel prospect en session (clé versionnée)."""

SESSION_KEY = "prospect_tunnel_v1"


def get_draft(request) -> dict:
    raw = request.session.get(SESSION_KEY)
    if not isinstance(raw, dict):
        return {}
    return raw


def set_draft(request, data: dict) -> None:
    request.session[SESSION_KEY] = data
    request.session.modified = True


def update_draft(request, step_key: str, step_data: dict) -> None:
    draft = get_draft(request)
    draft[step_key] = step_data
    set_draft(request, draft)


def clear_draft(request) -> None:
    if SESSION_KEY in request.session:
        del request.session[SESSION_KEY]
        request.session.modified = True


def has_steps(request, *keys: str) -> bool:
    draft = get_draft(request)
    return all(isinstance(draft.get(k), dict) and draft[k] for k in keys)

from fastapi import Request

from friendly_hub.core.errors import HubError

WRITE_GUARD_HEADER = "X-Friendly-Hub-Request"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def require_local_write_guard(request: Request) -> None:
    if request.method not in UNSAFE_METHODS:
        return
    if request.headers.get(WRITE_GUARD_HEADER) == "1":
        return
    raise HubError(
        code="SECURITY.REQUEST.GUARD_REQUIRED",
        message="The Hub blocked an untrusted local write request.",
        action="Return to the Hub window and try the action again.",
        status_code=403,
        severity="warning",
    )

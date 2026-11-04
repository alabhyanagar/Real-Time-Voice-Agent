"""Authorization and risk decisions for registered tools."""
from .schemas import PolicyDecision, ToolContext, ToolRisk


class ToolPolicyError(ValueError):
    """Raised when a tool definition contains an invalid policy."""


def decide(
    *,
    risk_level: ToolRisk,
    requires_confirmation: bool,
    required_scopes: tuple[str, ...],
    allowed_clients: tuple[str, ...],
    context: ToolContext,
    confirmed: bool = False,
) -> PolicyDecision:
    if allowed_clients and context.client_type not in allowed_clients:
        return PolicyDecision(action="deny", reason="Tool is unavailable for this client")
    missing_scopes = tuple(scope for scope in required_scopes if scope not in context.granted_scopes)
    if missing_scopes:
        return PolicyDecision(
            action="deny",
            reason="Required permission scopes are not granted",
            required_scopes=missing_scopes,
        )
    if confirmed:
        return PolicyDecision(action="allow")
    if requires_confirmation or risk_level in {"medium", "high"}:
        return PolicyDecision(action="confirm", reason="Explicit user confirmation is required")
    return PolicyDecision(action="allow")

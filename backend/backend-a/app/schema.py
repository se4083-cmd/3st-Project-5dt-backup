"""Single import for complete model metadata (Core tables use SQLAlchemy 2.x sessions)."""

from app.analytics_models import analytics_publication, analytics_receipts  # noqa: F401
from app.extensions.p1.models import p1_ai_call_attempts, p1_idempotency, p1_tasks  # noqa: F401
from app.extensions.p1.voc_models import voc_requests, voc_reviews, voc_teams  # noqa: F401
from app.model_constraints import idempotency_keys, team_categories, user_team_scopes  # noqa: F401
from app.models import metadata  # noqa: F401
from app.staff_models import automation_control, automation_control_history, queue_routes, staff_permissions  # noqa: F401

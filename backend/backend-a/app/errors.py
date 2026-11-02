class APIError(Exception):
    def __init__(self, status: int, code: str, actor_id=None, target_type=None, target_id=None):
        self.status = status
        self.code = code
        self.actor_id = actor_id
        self.target_type = target_type
        self.target_id = target_id


def denied(actor_id, target_type, target_id, code="RESOURCE_NOT_FOUND"):
    # Ownership is intentionally indistinguishable from a nonexistent ID.
    return APIError(404, code, actor_id, target_type, target_id)

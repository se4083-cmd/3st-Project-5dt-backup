"""Pure OpenAI boundary helpers; no persistence, approval or routing decisions.

Call only with application-owned metadata, never model-generated identifiers.
These helpers are not a complete backend save request or policy eligibility gate.
"""
import hashlib
import re
from datetime import datetime
from uuid import UUID

if __package__:
    from .analysis_errors import AnalysisResponseError
else:
    from analysis_errors import AnalysisResponseError


def backend_category(category):
    if not isinstance(category, str) or category not in {
        "DELIVERY", "RETURN", "REFUND", "PRODUCT", "PAYMENT", "ACCOUNT", "UNKNOWN"
    }:
        raise ValueError("Unsupported OpenAI category")
    return "UNCLASSIFIED" if category == "UNKNOWN" else category


def _text_sha256(value):
    if not isinstance(value, str):
        raise ValueError("Hash input must be an original string")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def policy_body_hash(body):
    return _text_sha256(body)


def draft_content_hash(draft):
    return _text_sha256(draft)


def evidence_refs_from_documents(documents):
    """Extract refs from supplied policy records, checking their exact body hash.

    No UUID issuance, version inference, JSON-string decoding or approval inference.
    Original records remain untouched; eligibility must be checked by the caller.
    """
    if not isinstance(documents, list) or not documents:
        raise ValueError("Nonempty policy document array required")
    refs = []
    seen = set()
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("Policy document must be an object")
        did = document.get("document_id")
        try:
            if not isinstance(did, str):
                raise ValueError()
            identity = UUID(did)
        except (ValueError, AttributeError):
            raise ValueError("Supplied document UUID required") from None
        version = document.get("version")
        digest = document.get("content_hash")
        if type(version) is not int or version < 1:
            raise ValueError("Positive integer policy version required")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Lowercase SHA-256 content_hash required")
        if policy_body_hash(document.get("body")) != digest:
            raise ValueError("Policy body hash mismatch")
        if identity in seen:
            raise ValueError("Duplicate policy document UUID")
        seen.add(identity)
        refs.append({"document_id": did, "version": version, "content_hash": digest})
    return refs


def execution_metadata(response, *, prompt_version):
    """Record actual response model and caller's active prompt version."""
    model = getattr(response, "model", None)
    if not isinstance(model, str) or not model.strip() or model == "NONE":
        raise AnalysisResponseError("Actual response model required")
    if not isinstance(prompt_version, str) or not prompt_version.strip():
        raise AnalysisResponseError("Active prompt version required")
    return {"prompt_version": prompt_version, "model_version": model}


def eligible_evidence_refs(documents, *, category, as_of):
    """Validate supplied knowledge_documents before exposing runtime references.

    P1 candidate approval is not knowledge_documents activation. Caller supplies
    authorized records and an aware timestamp; no retrieval or permission inferred.
    """
    backend_category(category)
    if category == "UNKNOWN":
        raise ValueError("Known policy topic required")
    def timestamp(value):
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValueError("Timezone-aware policy timestamp required")
        return value
    now = timestamp(as_of)
    refs = evidence_refs_from_documents(documents)
    for document in documents:
        topics = document.get("allowed_topics")
        if (document.get("active") is not True
                or document.get("approval_status") != "APPROVED"
                or document.get("data_origin") != "APPLICATION"
                or not isinstance(topics, list) or category not in topics):
            raise ValueError("Policy is not eligible for runtime evidence")
        start = timestamp(document.get("effective_from"))
        end = document.get("effective_to")
        if start > now or (end is not None and timestamp(end) <= now):
            raise ValueError("Policy is outside its effective period")
    return refs

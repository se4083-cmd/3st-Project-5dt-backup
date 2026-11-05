"""Explicit synthetic SDK-shaped client for offline analysis integration.

No network, credentials, real model, database writes or automatic live fallback.
Never select this client in production.
"""

from copy import deepcopy
import json
from types import SimpleNamespace

SCENARIOS = {
    "delivery": {
        "inquiry": "주문한 상품의 배송 상태를 알고 싶어요.",
        "payload": {"category": "DELIVERY", "summary": "주문 상품 배송 상태 확인 요청",
                    "risk_tags": [], "risk_evidence": []},
    },
    "human_request": {
        "inquiry": "배송이 늦어지고 있어요. 상담사와 직접 이야기하고 싶어요.",
        "payload": {"category": "DELIVERY", "summary": "배송 지연에 대한 상담사 직접 연결 요청",
                    "risk_tags": ["HUMAN_REQUEST"],
                    "risk_evidence": [{"tag": "HUMAN_REQUEST",
                                       "quote": "상담사와 직접 이야기하고 싶어요."}]},
    },
    "unknown": {
        "inquiry": "확인해주세요.",
        "payload": {"category": "UNKNOWN", "summary": "대상이 불명확한 확인 요청",
                    "risk_tags": [], "risk_evidence": []},
    },
}


class MockAnalysisClient:
    """Use only with the matching fixture inquiry; never classifies arbitrary text."""

    def __init__(self, scenario="delivery"):
        if scenario not in SCENARIOS:
            raise ValueError("Unknown synthetic scenario")
        self.fixture = deepcopy(SCENARIOS[scenario])
        self.calls = 0
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        if kwargs.get("input") != self.fixture["inquiry"]:
            raise ValueError("Mock client requires its exact synthetic inquiry")
        self.calls += 1
        return SimpleNamespace(status="completed", output=[], model="MOCK_ANALYSIS_ONLY",
                               output_text=json.dumps(self.fixture["payload"], ensure_ascii=False))

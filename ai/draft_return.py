"""OpenAI return-draft entry point, pending the team's published contract.

No policy, retrieval, routing, approval, persistence, or sending is implemented.
The signature is provisional and must not be used as a shared integration contract.
"""


def generate_return_draft(client=None, deployment=None, inquiry=None, analysis=None, context=None):
    """Reserved entry point. Does not call an API or consume supplied data.

    Implementation waits for the policy/RAG contract published by its owner.
    No placeholder policy or successful draft is returned while inputs are absent.
    """
    raise NotImplementedError(
        "반품 안내 초안 생성은 연결 대기 중입니다. "
        "정책/RAG 담당자가 GitHub에 게시한 입력 계약과 승인된 근거를 확인한 뒤 구현합니다."
    )

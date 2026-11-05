"""CS Flow AI: Azure OpenAI 첫 호출 테스트.
실행: 프로젝트의 .venv를 활성화한 PowerShell에서 python test_openai.py
필수 패키지: openai, azure-identity, python-dotenv
인증: 앞서 az login으로 로그인한 계정
설정: 이 파일 옆의 .env 또는 현재 프로세스의 환경 변수
실제 API 호출은 이 파일을 실행할 때 1회 발생합니다.
"""

import os
from pathlib import Path

from azure.identity import AzureCliCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import OpenAI


def load_settings():
    # 실행 위치와 관계없이 Python 파일 옆의 .env를 읽습니다.
    # 이미 지정된 환경 변수는 유지합니다.
    load_dotenv(
        Path(__file__).with_name(".env"),
        override=False,
        encoding="utf-8-sig",
    )
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
    if not endpoint or not deployment:
        raise SystemExit(
            ".env의 AZURE_OPENAI_ENDPOINT와 AZURE_OPENAI_DEPLOYMENT를 확인하세요."
        )
    if not endpoint.startswith("https://"):
        raise SystemExit("AZURE_OPENAI_ENDPOINT는 https://로 시작해야 합니다.")
    return endpoint, deployment


def main():
    endpoint, deployment = load_settings()

    # Azure CLI 로그인 계정으로 인증합니다.
    token_provider = get_bearer_token_provider(
        AzureCliCredential(),
        "https://cognitiveservices.azure.com/.default",
    )

    with OpenAI(
        base_url=f"{endpoint}/openai/v1/",
        api_key=token_provider,
        timeout=60.0,
        max_retries=0,
    ) as client:
        response = client.responses.create(
            model=deployment,  # Azure에서 만든 배포 이름
            instructions=(
                "테스트용 가상 고객 문의를 한국어 한 문장으로 요약하세요. "
                "문의에 없는 정보나 해결 방법은 추가하지 마세요."
            ),
            input=(
                "어제 도착 예정이었던 상품이 아직 오지 않았어요. "
                "배송 조회에는 배송 중이라고만 나옵니다. "
                "언제 받을 수 있는지 확인하고 싶어요."
            ),
            reasoning={"effort": "minimal"},
            max_output_tokens=800,
            store=False,
        )

    print("응답 상태:", response.status)
    if response.output_text:
        print("요약:", response.output_text)
    else:
        print("생성된 답변이 없습니다.")

    if response.incomplete_details is not None:
        print("미완료 사유:", response.incomplete_details.reason)

    if response.usage is not None:
        print("입력 토큰:", response.usage.input_tokens)
        print("출력 토큰:", response.usage.output_tokens)

    if response.status != "completed" or not response.output_text:
        raise SystemExit(1)


if __name__ == "__main__":
    main()


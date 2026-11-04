import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/mock", tags=["Backend B - Mock"])

# 프로젝트 루트 기준으로 로컬 합성 데이터 경로 설정
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "local" / "data"


def load_json(filename: str) -> list[dict]:
    """합성 JSON 파일을 읽어 리스트로 반환한다."""
    file_path = DATA_DIR / filename

    if not file_path.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"Mock data file not found: {filename}",
        )

    try:
        with file_path.open("r", encoding="utf-8") as file:
            records = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load Mock data: {filename}",
        ) from exc

    if not isinstance(records, list):
        raise HTTPException(
            status_code=500,
            detail=f"Expected a JSON array: {filename}",
        )

    return records


def find_one(records: list[dict], key: str, value):
    """지정한 컬럼 값과 일치하는 첫 번째 데이터를 반환한다."""
    return next(
        (record for record in records if record.get(key) == value),
        None,
    )


@router.get("/tickets/{ticket_id}/context")
def get_ticket_context(ticket_id: str):
    """티켓과 연결된 고객, 주문, 상품, 배송 정보를 조회한다."""

    tickets = load_json("tickets.json")
    ticket = find_one(tickets, "ticket_id", ticket_id)

    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ticket not found: {ticket_id}",
        )

    customers = load_json("customers.json")
    orders = load_json("orders.json")
    products = load_json("products.json")
    shipments = load_json("shipments.json")

    customer = find_one(customers, "customer_id", ticket.get("customer_id"))
    order = find_one(orders, "order_id", ticket.get("order_id"))
    product = find_one(products, "product_id", ticket.get("product_id"))

    # 배송 정보는 주문 ID를 기준으로 연결
    shipment = find_one(shipments, "order_id", ticket.get("order_id"))

    return {
        "ticket": ticket,
        "customer": customer,
        "order": order,
        "product": product,
        "shipment": shipment,
    }

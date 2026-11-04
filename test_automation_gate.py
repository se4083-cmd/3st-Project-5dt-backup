from backend.app.automation.automation_gate import evaluate_gate

ticket_ids = [
    "f3fc8c61-5b47-50c9-b0ca-840f40fbc6a7",
    "8e094889-a027-5968-af0d-959bb72fb7fa",
]

for ticket_id in ticket_ids:
    result = evaluate_gate(ticket_id, 1)
    print(ticket_id, result)

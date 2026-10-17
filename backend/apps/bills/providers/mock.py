"""
MOCK VTU provider for development and tests. Delivers nothing real. Behaviour by customer number:
  ends with 0000 -> rejected (never created)     ends with 1111 -> failed after creation
  ends with 2222 -> processing, delivered on the next requery     ends with 3333 -> timeout (unknown)
  anything else  -> delivered (electricity gets a fake 20-digit token)
"""

from django.core.cache import cache

from .base import DELIVERED, FAILED, PROCESSING, REJECTED, UNKNOWN, Result


class MockVtu:
    name = "mock"
    calls: list[tuple[str, str]] = []

    def supports(self, biller, plan) -> bool:
        return True

    def verify_customer(self, biller, plan, customer_id: str) -> dict:
        if customer_id.endswith("0000"):
            return {"name": "", "details": {}}
        return {"name": "MOCK CUSTOMER", "details": {"customer_address": "12 Mock Street"}}

    def _delivered(self, order, request_id) -> Result:
        token = "1234-5678-9012-3456-7890" if order.category == "electricity" else ""
        return Result(
            outcome=DELIVERED,
            reference=f"MOCK-{request_id}",
            token=token,
            units="42.5kWh" if token else "",
            cost=order.amount,
        )

    def purchase(self, order, request_id: str) -> Result:
        MockVtu.calls.append(("purchase", request_id))
        cid = order.customer_id
        if cid.endswith("0000"):
            return Result(outcome=REJECTED, message="mock: rejected")
        if cid.endswith("1111"):
            return Result(outcome=FAILED, reference=f"MOCK-{request_id}", message="mock: failed")
        if cid.endswith("2222"):
            cache.set(f"mockvtu:{request_id}", "pending", 3600)
            return Result(outcome=PROCESSING, reference=f"MOCK-{request_id}")
        if cid.endswith("3333"):
            cache.set(f"mockvtu:{request_id}", "timeout", 3600)
            return Result(outcome=UNKNOWN, message="mock: timed out")
        return self._delivered(order, request_id)

    def requery(self, order, request_id: str) -> Result:
        MockVtu.calls.append(("requery", request_id))
        state = cache.get(f"mockvtu:{request_id}")
        if state == "pending":
            return self._delivered(order, request_id)
        if state == "timeout":
            return Result(outcome="not_found")
        return Result(outcome="not_found")

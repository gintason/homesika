import io

from django.utils import timezone
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.core.money import format_money


def render(order) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A5)
    w, h = A5
    y = h - 20 * mm
    c.setFont("Helvetica-Bold", 16)
    c.drawString(15 * mm, y, "Homesika")
    c.setFont("Helvetica", 10)
    c.drawRightString(w - 15 * mm, y, f"Receipt {order.receipt_number}")
    y -= 12 * mm
    rows = [
        ("Service", order.biller.name),
        ("Plan", order.plan.name if order.plan_id else "-"),
        ("Number", order.customer_id),
        ("Name", order.customer_name or "-"),
        ("Amount", format_money(order.amount, order.currency, plain=True)),
        ("Fee", format_money(order.fee, order.currency, plain=True)),
        ("Total paid", format_money(order.total, order.currency, plain=True)),
        ("Paid on", timezone.localtime(order.paid_at).strftime("%d %b %Y, %H:%M") if order.paid_at else "-"),
        ("Reference", order.reference),
    ]
    if order.token:
        rows += [("Token", order.token), ("Units", order.units or "-")]
    for label, value in rows:
        c.setFont("Helvetica", 9)
        c.drawString(15 * mm, y, label)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50 * mm, y, str(value)[:60])
        y -= 7 * mm
    c.setFont("Helvetica", 8)
    c.drawString(15 * mm, 15 * mm, "Bought through Homesika from a licensed VTU provider. Keep this receipt.")
    c.showPage()
    c.save()
    return buf.getvalue()

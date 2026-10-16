"""Receipt PDFs, rendered on request (nothing stored on disk; Render's disks are ephemeral)."""

import io

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.core.money import format_money

NAVY = colors.HexColor("#0B2B63")
INK = colors.HexColor("#2B333D")
MUTED = colors.HexColor("#5F6B7A")
GOLD = colors.HexColor("#C4A35A")


def _money(minor, ccy):
    # The built-in PDF fonts lack the naira sign; spell the currency out instead.
    return format_money(minor, ccy, plain=True)


def render(payment) -> bytes:
    receipt = payment.receipt
    org, tenant = payment.organization, payment.tenant
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A5)
    w, h = A5
    c.setTitle(f"Receipt {receipt.number}")

    c.setFillColor(NAVY)
    c.rect(0, h - 28 * mm, w, 28 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(12 * mm, h - 14 * mm, org.name[:40])
    c.setFont("Helvetica", 9)
    c.drawString(12 * mm, h - 20 * mm, "Payment receipt · issued via Homesika")
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.2)
    c.line(0, h - 28 * mm, w, h - 28 * mm)

    y = h - 40 * mm
    c.setFillColor(INK)

    def row(label, value, bold=False):
        nonlocal y
        c.setFont("Helvetica", 9)
        c.setFillColor(MUTED)
        c.drawString(12 * mm, y, label)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        c.drawRightString(w - 12 * mm, y, str(value)[:60])
        y -= 7 * mm

    row("Receipt number", receipt.number, bold=True)
    row("Date paid", timezone.localtime(payment.paid_at).strftime("%d %b %Y, %H:%M"))
    row("Received from", tenant.full_name)
    row("Phone", tenant.phone_number)
    row("Method", (payment.channel or payment.gateway).replace("_", " ").title())
    row("Reference", payment.gateway_reference)
    y -= 3 * mm
    c.setStrokeColor(colors.HexColor("#DCE3EC"))
    c.line(12 * mm, y + 4 * mm, w - 12 * mm, y + 4 * mm)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(12 * mm, y, "Applied to")
    y -= 7 * mm
    for alloc in payment.allocations.select_related("charge__unit__property"):
        ch = alloc.charge
        label = f"{ch.description or ch.get_kind_display()} · {ch.unit.label}"
        row(label[:55], _money(alloc.amount, payment.currency))
    if payment.unallocated_amount:
        row("Overpayment (landlord to apply)", _money(payment.unallocated_amount, payment.currency))
    y -= 2 * mm
    c.setFillColor(colors.HexColor("#EEF4FB"))
    c.roundRect(12 * mm, y - 5 * mm, w - 24 * mm, 13 * mm, 3 * mm, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(16 * mm, y, "Total paid")
    c.drawRightString(w - 16 * mm, y, _money(payment.amount, payment.currency))

    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    c.drawString(12 * mm, 12 * mm, "Paid directly to the landlord's account. Homesika does not hold rent.")
    c.drawString(
        12 * mm, 8 * mm, "Questions about this payment? Contact your landlord or support@homesika.com"
    )
    c.showPage()
    c.save()
    return buf.getvalue()

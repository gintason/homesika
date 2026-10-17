"""
ID types for the staff-reviewed ("manual") mode. The default mode, "nin", looks the NIN up through a
licensed provider (apps/artisans/nin.py) and has the ID photo read by AI (apps/artisans/ai_review.py);
the rules that decide are in services.run_id_check.
"""

ID_TYPES = {
    "nin": "National Identification Number (NIN)",
    "drivers_licence": "Driver's licence",
    "voters_card": "Permanent voter's card",
    "passport": "International passport",
}

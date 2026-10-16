from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.core.money import CurrencyField, MoneyField


class Expense(TimeStampedModel):
    """Money the landlord spent on a property (repairs, fees, utilities): for statements and net income."""

    class Category(models.TextChoices):
        REPAIRS = "repairs", _("Repairs and maintenance")
        UTILITIES = "utilities", _("Utilities")
        CLEANING = "cleaning", _("Cleaning and waste")
        SECURITY = "security", _("Security")
        AGENT_FEE = "agent_fee", _("Agent / management fee")
        LEGAL = "legal", _("Legal and professional")
        TAX = "tax", _("Taxes and levies")
        INSURANCE = "insurance", _("Insurance")
        OTHER = "other", _("Other")

    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="expenses")
    property = models.ForeignKey(
        "properties.Property", on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses"
    )
    unit = models.ForeignKey(
        "properties.Unit", on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses"
    )
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.OTHER)
    amount = MoneyField()
    currency = CurrencyField(default="NGN")
    spent_on = models.DateField(db_index=True)
    vendor = models.CharField(max_length=120, blank=True)
    description = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ("-spent_on", "-created_at")
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="expense_amount_positive")]

    def __str__(self):
        return f"{self.get_category_display()} {self.amount} on {self.spent_on}"

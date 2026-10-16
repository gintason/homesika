import { useState, type FormEvent } from "react";

import { Banner, Button, Card, DataTable, StatusBadge, TextField, useToast } from "../../components";
import { strings } from "../../i18n";
import { api } from "../../lib/api";
import { formatDate } from "../../lib/dates";
import { useForm } from "../../lib/form";
import { useIdempotencyKey } from "../../lib/idempotency";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { SettlementAccount } from "../../lib/types";

const t = strings.settings;

/** Settlement (payout) accounts. Anyone with payment.view can see them; only owners (org.manage) change them. */
export function PayoutSettings() {
  const { org, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const idem = useIdempotencyKey();
  const accounts = useOrgQuery<SettlementAccount[]>("/settlement-accounts/");
  const owner = can("org.manage");
  const [busy, setBusy] = useState(false);
  const form = useForm({ bank_name: "", bank_code: "", account_number: "", account_name: "" });
  const v = form.values;
  const hasActive = accounts.data?.some((a) => a.status === "active");

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const req = strings.common.required;
    if (
      !form.validate({
        bank_name: v.bank_name.trim() ? undefined : req,
        bank_code: /^\d{3,10}$/.test(v.bank_code.trim()) ? undefined : t.bankCodeHint,
        account_number: /^\d{10}$/.test(v.account_number) ? undefined : t.accountNumberInvalid,
        account_name: v.account_name.trim() ? undefined : req,
      })
    )
      return;
    const body = {
      bank_name: v.bank_name.trim(),
      bank_code: v.bank_code.trim(),
      account_number: v.account_number,
      account_name: v.account_name.trim(),
    };
    setBusy(true);
    try {
      await api<SettlementAccount[]>(`/orgs/${org.id}/settlement-accounts/`, {
        method: "POST",
        body,
        idempotencyKey: idem.keyFor(body),
      });
      idem.reset();
      await invalidate();
      toast.show(t.payoutSaved);
      form.setValues({ bank_name: "", bank_code: "", account_number: "", account_name: "" });
    } catch (err) {
      form.fromApiError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card title={t.payoutTab}>
        <p className="mb-4 text-base text-ink-600">{t.payoutIntro}</p>
        {accounts.data && !hasActive && <Banner tone="warning" className="mb-4">{t.noPayout}</Banner>}
        <DataTable
          caption={t.payoutTab}
          rows={accounts.data}
          loading={accounts.isLoading}
          error={accounts.error}
          onRetry={() => void accounts.refetch()}
          rowKey={(a) => a.id}
          columns={[
            { key: "bank", header: t.bankName, cell: (a) => a.bank_name },
            { key: "account", header: t.accountNumber, cell: (a) => `•••• ${a.account_last4}` },
            { key: "name", header: t.accountName, cell: (a) => a.account_name },
            { key: "gateway", header: strings.payments.gateway, cell: (a) => a.gateway },
            {
              key: "status",
              header: strings.charges.status,
              cell: (a) => (
                <span className="space-y-1">
                  <StatusBadge status={a.status} />
                  {a.failure_reason && <span className="block text-sm text-danger-700">{a.failure_reason}</span>}
                </span>
              ),
            },
            { key: "date", header: strings.fields.date, cell: (a) => formatDate(a.created_at) },
          ]}
        />
      </Card>
      {owner ? (
        <Card title={t.addPayout} className="max-w-2xl">
          <form onSubmit={submit} noValidate className="space-y-4">
            {form.formError && <Banner tone="error">{form.formError}</Banner>}
            <TextField label={t.bankName} {...form.text("bank_name")} />
            <TextField label={t.bankCode} hint={t.bankCodeHint} inputMode="numeric" maxLength={10} {...form.text("bank_code")} />
            <TextField
              label={t.accountNumber}
              hint={t.accountNumberHint}
              inputMode="numeric"
              maxLength={10}
              {...form.text("account_number")}
              onChange={(e) => form.set("account_number", e.target.value.replace(/\D/g, ""))}
            />
            <TextField label={t.accountName} {...form.text("account_name")} />
            <Button type="submit" loading={busy}>
              {t.addPayout}
            </Button>
          </form>
        </Card>
      ) : (
        <Banner tone="info">{t.payoutOwnerOnly}</Banner>
      )}
    </div>
  );
}

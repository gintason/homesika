import { useState, type FormEvent } from "react";

import { Banner, Button, Card, ConfirmDialog, DataTable, PhoneInput, Select, StatusBadge, optionsFrom, useToast } from "../../components";
import { fmt, strings } from "../../i18n";
import { api, errorText } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useOrg } from "../../lib/org";
import { formatPhone, isValidNigerianPhone, normalisePhone } from "../../lib/phone";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { Membership, Role } from "../../lib/types";

const t = strings.settings;
const ROLES = optionsFrom(strings.orgs.roles);

export function TeamSettings() {
  const { org, can } = useOrg();
  const { user } = useAuth();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const members = useOrgQuery<Membership[]>("/members/");
  const manage = can("members.manage");
  const [phone, setPhone] = useState("");
  const [role, setRole] = useState<Role>("manager");
  const [errors, setErrors] = useState<{ phone?: string; role?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Membership | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);

  const invite = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (!isValidNigerianPhone(phone)) {
      setErrors({ phone: strings.fields.phoneInvalid });
      return;
    }
    setErrors({});
    setBusy(true);
    try {
      await api(`/orgs/${org.id}/members/`, { method: "POST", body: { phone_number: normalisePhone(phone), role } });
      await invalidate();
      toast.show(t.invited);
      setPhone("");
    } catch (err) {
      const e2 = err as { fieldErrors?: Record<string, string> };
      if (e2.fieldErrors?.phone_number || e2.fieldErrors?.role) setErrors({ phone: e2.fieldErrors.phone_number, role: e2.fieldErrors.role });
      else setFormError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const changeRole = async (m: Membership, next: string) => {
    setRowError(null);
    try {
      await api(`/orgs/${org.id}/members/${m.id}/`, { method: "PATCH", body: { role: next } });
      await invalidate();
      toast.show(t.roleChanged);
    } catch (err) {
      setRowError(errorText(err));
    }
  };

  const remove = async () => {
    if (!removing) return;
    setRemoveBusy(true);
    setRemoveError(null);
    try {
      await api(`/orgs/${org.id}/members/${removing.id}/`, { method: "DELETE" });
      await invalidate();
      toast.show(t.removed);
      setRemoving(null);
    } catch (err) {
      setRemoveError(errorText(err));
    } finally {
      setRemoveBusy(false);
    }
  };

  // The members API has no user id, so "me" is recognised by phone number.
  const isMe = (m: Membership) => Boolean(user && m.phone_number === user.phone_number);

  return (
    <div className="space-y-6">
      {manage && (
        <Card title={t.invite} className="max-w-2xl">
          <form onSubmit={invite} noValidate className="space-y-4">
            {formError && <Banner tone="error">{formError}</Banner>}
            <PhoneInput value={phone} onChange={setPhone} error={errors.phone} hint={t.inviteHint} />
            <Select label={t.role} options={ROLES} value={role} onChange={(e) => setRole(e.target.value as Role)} error={errors.role} />
            <Button type="submit" loading={busy}>
              {t.invite}
            </Button>
          </form>
        </Card>
      )}
      <Card title={t.members}>
        {rowError && <Banner tone="error" className="mb-4">{rowError}</Banner>}
        <DataTable
          caption={t.members}
          rows={members.data}
          loading={members.isLoading}
          error={members.error}
          onRetry={() => void members.refetch()}
          rowKey={(m) => m.id}
          empty={{ title: strings.common.none }}
          columns={[
            { key: "name", header: strings.fields.name, cell: (m) => <span className="font-medium">{m.name || "—"}</span> },
            { key: "phone", header: strings.fields.phone, cell: (m) => formatPhone(m.phone_number) },
            {
              key: "role",
              header: t.role,
              cell: (m) =>
                manage && !isMe(m) ? (
                  <Select
                    label={`${t.role}: ${m.name || formatPhone(m.phone_number)}`}
                    hideLabel
                    options={ROLES}
                    value={m.role}
                    onChange={(e) => void changeRole(m, e.target.value)}
                  />
                ) : (
                  strings.orgs.roles[m.role]
                ),
            },
            { key: "status", header: strings.charges.status, cell: (m) => <StatusBadge status={m.status} /> },
            ...(manage
              ? [
                  {
                    key: "actions",
                    header: strings.common.actions,
                    hideHeader: true,
                    cell: (m: Membership) =>
                      isMe(m) ? null : (
                        <Button variant="ghost" onClick={() => setRemoving(m)} aria-label={`${strings.common.remove} ${m.name || formatPhone(m.phone_number)}`}>
                          {strings.common.remove}
                        </Button>
                      ),
                  },
                ]
              : []),
          ]}
        />
      </Card>
      <ConfirmDialog
        open={removing !== null}
        onClose={() => {
          setRemoving(null);
          setRemoveError(null);
        }}
        onConfirm={() => void remove()}
        title={fmt(t.removeTitle, { name: removing?.name || formatPhone(removing?.phone_number) })}
        description={t.removeBody}
        confirmLabel={strings.common.remove}
        destructive
        loading={removeBusy}
        error={removeError}
      />
    </div>
  );
}

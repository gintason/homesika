import { useState } from "react";
import { useParams } from "react-router";

import {
  Badge,
  Button,
  Card,
  Checkbox,
  ConfirmDialog,
  DataTable,
  DescriptionList,
  Dialog,
  MoneyInput,
  PageHeader,
  Select,
  Switch,
  Tabs,
  TextArea,
  TextField,
  optionsFrom,
  useToast,
  type BadgeTone,
} from "../../components";
import { fmt, strings } from "../../i18n";
import { api } from "../../lib/api";
import { formatDate, formatDateTime, todayISO } from "../../lib/dates";
import { useIdempotencyKey } from "../../lib/idempotency";
import { formatMoney, parseMoneyInput } from "../../lib/money";
import { useOrg } from "../../lib/org";
import { formatPhone, isValidNigerianPhone, normalisePhone } from "../../lib/phone";
import { useInvalidateOrg, useOrgQuery, usePaginatedList } from "../../lib/queries";
import type { Announcement, DuesPlan, Estate, EstateMember, EstateMemberStatus, House, RentFrequency } from "../../lib/types";
import { QueryState, actionError } from "../shared";
import { splitHouses } from "./EstatesList";

const t = strings.estates;
const m = t.member;

const MEMBER_TONE: Record<EstateMemberStatus, BadgeTone> = {
  pending: "warning",
  approved: "success",
  suspended: "neutral",
  removed: "neutral",
};

export function EstateDetail() {
  const { estateId = "" } = useParams();
  const q = useOrgQuery<Estate>(`/estates/${estateId}/`);
  return (
    <QueryState data={q.data} isLoading={q.isLoading} error={q.error} refetch={q.refetch}>
      {(estate) => <EstateView estate={estate} />}
    </QueryState>
  );
}

function EstateView({ estate }: { estate: Estate }) {
  const { base, can } = useOrg();
  const [tab, setTab] = useState("residents");
  const manage = can("estate.manage");
  return (
    <>
      <PageHeader back={{ to: `${base}/estates`, label: t.title }} title={estate.name} description={estate.address} />
      <Card className="mb-6">
        <DescriptionList
          items={[
            { label: t.joinCode, value: <JoinCode estate={estate} manage={manage} /> },
            { label: t.residents, value: estate.verified_residents },
            { label: t.pending, value: estate.pending_residents },
            { label: t.houses, value: estate.houses },
          ]}
        />
      </Card>
      <Tabs
        label={estate.name}
        value={tab}
        onChange={setTab}
        items={[
          { id: "residents", label: t.tabs.residents, content: <Residents estate={estate} /> },
          { id: "houses", label: t.tabs.houses, content: <Houses estate={estate} /> },
          { id: "dues", label: t.tabs.dues, content: <Dues estate={estate} /> },
          { id: "announcements", label: t.tabs.announcements, content: <News estate={estate} /> },
          ...(manage ? [{ id: "settings", label: t.tabs.settings, content: <Settings estate={estate} /> }] : []),
        ]}
      />
    </>
  );
}

function JoinCode({ estate, manage }: { estate: Estate; manage: boolean }) {
  const { org } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const regenerate = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/orgs/${org.id}/estates/${estate.id}/regenerate-code/`, { method: "POST" });
      await invalidate();
      toast.show(t.codeChanged);
      setOpen(false);
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <span className="flex flex-wrap items-center gap-3">
      <span className="font-mono text-lg tracking-widest">{estate.join_code}</span>
      <span className="text-sm text-ink-600">{t.joinCodeHint}</span>
      {manage && (
        <Button variant="secondary" onClick={() => setOpen(true)}>
          {t.newCode}
        </Button>
      )}
      <ConfirmDialog
        open={open}
        onClose={() => setOpen(false)}
        onConfirm={() => void regenerate()}
        title={t.newCode}
        description={t.newCodeBody}
        confirmLabel={t.newCode}
        loading={busy}
        error={error}
      />
    </span>
  );
}

// ---- Residents ------------------------------------------------------------------------------------

const FILTERS = ["pending", "approved", "suspended", "all"] as const;
type Act = "approve" | "suspend" | "remove";

function Residents({ estate }: { estate: Estate }) {
  const { org, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>(estate.pending_residents ? "pending" : "approved");
  const list = usePaginatedList<EstateMember>("/estate-members/", {
    estate: estate.id,
    status: filter === "all" ? undefined : filter,
  });
  const houses = useOrgQuery<House[]>(`/estates/${estate.id}/houses/`);
  const [act, setAct] = useState<{ kind: Act; member: EstateMember } | null>(null);
  const [unit, setUnit] = useState("");
  const [reason, setReason] = useState("");
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const manage = can("estate.manage");

  const start = (kind: Act, member: EstateMember) => {
    setUnit(member.unit ?? "");
    setReason("");
    setError(null);
    setAct({ kind, member });
  };

  const run = async () => {
    if (!act) return;
    setBusy(true);
    setError(null);
    try {
      const body = act.kind === "approve" ? { unit: unit || null } : { reason: reason.trim() };
      await api(`/orgs/${org.id}/estate-members/${act.member.id}/${act.kind}/`, { method: "POST", body });
      await invalidate();
      toast.show(act.kind === "approve" ? m.approved : act.kind === "suspend" ? m.suspended : m.removed);
      setAct(null);
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(false);
    }
  };

  const houseOptions = (houses.data ?? []).map((h) => ({ value: h.id, label: h.label }));

  return (
    <div className="space-y-4 pt-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <Select
          containerClassName="w-full max-w-xs"
          label={m.filter}
          value={filter}
          options={FILTERS.map((f) => ({ value: f, label: m.filters[f] }))}
          onChange={(e) => setFilter(e.target.value as (typeof FILTERS)[number])}
        />
        {manage && <Button onClick={() => setAdding(true)}>{m.add}</Button>}
      </div>
      <DataTable
        caption={t.tabs.residents}
        rows={list.rows}
        loading={list.isLoading}
        error={list.error}
        onRetry={list.refetch}
        hasMore={list.hasMore}
        onLoadMore={list.loadMore}
        loadingMore={list.loadingMore}
        rowKey={(r) => r.id}
        empty={{ title: m.empty, body: m.emptyHint }}
        columns={[
          { key: "name", header: m.name, cell: (r) => r.full_name },
          { key: "house", header: m.house, cell: (r) => r.house || "—" },
          { key: "phone", header: m.phone, cell: (r) => formatPhone(r.phone_number) },
          { key: "role", header: m.role, cell: (r) => m.roles[r.role] },
          { key: "status", header: m.status, cell: (r) => <Badge tone={MEMBER_TONE[r.status]}>{m.statuses[r.status]}</Badge> },
          { key: "app", header: m.app, cell: (r) => (r.has_app ? strings.common.yes : strings.common.no) },
          {
            key: "actions",
            header: strings.common.actions,
            cell: (r) =>
              manage ? (
                <span className="flex flex-wrap gap-2">
                  {(r.status === "pending" || r.status === "suspended") && (
                    <Button onClick={() => start("approve", r)}>
                      {m.approve}
                    </Button>
                  )}
                  {r.status === "approved" && (
                    <Button variant="secondary" onClick={() => start("suspend", r)}>
                      {m.suspend}
                    </Button>
                  )}
                  {r.status !== "removed" && (
                    <Button variant="secondary" onClick={() => start("remove", r)}>
                      {m.remove}
                    </Button>
                  )}
                </span>
              ) : null,
          },
        ]}
      />
      <ConfirmDialog
        open={act !== null}
        onClose={() => setAct(null)}
        onConfirm={() => void run()}
        title={act ? fmt(act.kind === "approve" ? m.approveTitle : act.kind === "suspend" ? m.suspendTitle : m.removeTitle, { name: act.member.full_name }) : ""}
        description={act?.kind === "approve" ? m.approveBody : act?.kind === "suspend" ? m.suspendBody : undefined}
        confirmLabel={act ? (act.kind === "approve" ? m.approve : act.kind === "suspend" ? m.suspend : m.remove) : ""}
        destructive={act?.kind === "remove"}
        loading={busy}
        error={error}
        confirmDisabled={act?.kind === "approve" && !unit}
      >
        {act?.kind === "approve" ? (
          <Select
            label={m.chooseHouse}
            hint={act.member.house_label ? fmt(m.typed, { house: act.member.house_label }) : undefined}
            placeholder="—"
            value={unit}
            options={houseOptions}
            onChange={(e) => setUnit(e.target.value)}
          />
        ) : act ? (
          <TextField label={m.reason} optional value={reason} onChange={(e) => setReason(e.target.value)} />
        ) : null}
      </ConfirmDialog>
      <AddResident estate={estate} houses={houseOptions} open={adding} onClose={() => setAdding(false)} />
    </div>
  );
}

function AddResident({
  estate,
  houses,
  open,
  onClose,
}: {
  estate: Estate;
  houses: Array<{ value: string; label: string }>;
  open: boolean;
  onClose: () => void;
}) {
  const { org } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [form, setForm] = useState({ full_name: "", phone_number: "", unit: "", role: "resident" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const e: Record<string, string> = {};
    if (!form.full_name.trim()) e.full_name = strings.common.required;
    if (!isValidNigerianPhone(form.phone_number)) e.phone_number = strings.fields.phoneInvalid;
    if (!form.unit) e.unit = strings.common.required;
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/orgs/${org.id}/estate-members/`, {
        method: "POST",
        body: { ...form, estate: estate.id, phone_number: normalisePhone(form.phone_number) },
      });
      await invalidate();
      toast.show(m.added);
      setForm({ full_name: "", phone_number: "", unit: "", role: "resident" });
      onClose();
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={m.add}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {strings.common.cancel}
          </Button>
          <Button onClick={() => void submit()} loading={busy}>
            {m.add}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <p className="text-sm text-danger-700">{error}</p>}
        <TextField label={m.name} value={form.full_name} error={errors.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        <TextField
          label={m.phone}
          type="tel"
          inputMode="tel"
          value={form.phone_number}
          error={errors.phone_number}
          onChange={(e) => setForm({ ...form, phone_number: e.target.value })}
        />
        <Select label={m.house} placeholder="—" value={form.unit} options={houses} error={errors.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} />
        <Select label={m.role} value={form.role} options={optionsFrom(m.roles)} onChange={(e) => setForm({ ...form, role: e.target.value })} />
      </div>
    </Dialog>
  );
}

// ---- Houses ---------------------------------------------------------------------------------------

function Houses({ estate }: { estate: Estate }) {
  const { org, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const q = useOrgQuery<House[]>(`/estates/${estate.id}/houses/`);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const add = async () => {
    const labels = splitHouses(text);
    if (!labels.length) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ created: number }>(`/orgs/${org.id}/estates/${estate.id}/houses/`, { method: "POST", body: { labels } });
      await invalidate();
      toast.show(fmt(t.housesTab.added, { count: r.created }));
      setText("");
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="grid gap-6 pt-4 lg:grid-cols-3">
      <Card title={t.houses} className="lg:col-span-2">
        {q.data && q.data.length === 0 ? (
          <p className="text-ink-600">{t.housesTab.empty}</p>
        ) : (
          <ul className="flex flex-wrap gap-2" aria-label={t.houses}>
            {(q.data ?? []).map((h) => (
              <li key={h.id} className="rounded-pill bg-surface-muted px-3 py-1 text-sm text-ink-800">
                {h.label}
              </li>
            ))}
          </ul>
        )}
      </Card>
      {can("estate.manage") && (
        <Card title={t.housesTab.add} className="space-y-3">
          {error && <p className="text-sm text-danger-700">{error}</p>}
          <TextArea label={t.housesField} hint={t.housesHint} rows={4} value={text} onChange={(e) => setText(e.target.value)} />
          <Button onClick={() => void add()} loading={busy} disabled={!splitHouses(text).length}>
            {t.housesTab.add}
          </Button>
        </Card>
      )}
    </div>
  );
}

// ---- Dues -----------------------------------------------------------------------------------------

function Dues({ estate }: { estate: Estate }) {
  const { org, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const q = useOrgQuery<{ results: DuesPlan[] }>("/dues-plans/", { estate: estate.id });
  const [form, setForm] = useState({ name: "", amount: "", frequency: "monthly" as RentFrequency, start_date: todayISO().slice(0, 8) + "01" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const d = t.dues;

  const add = async () => {
    const amount = parseMoneyInput(form.amount);
    const e: Record<string, string> = {};
    if (!form.name.trim()) e.name = strings.common.required;
    if (!amount || Number(amount) <= 0) e.amount = strings.common.required;
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/orgs/${org.id}/dues-plans/`, { method: "POST", body: { ...form, amount, estate: estate.id } });
      await invalidate();
      toast.show(d.created);
      setForm({ ...form, name: "", amount: "" });
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (plan: DuesPlan) => {
    try {
      await api(`/orgs/${org.id}/dues-plans/${plan.id}/`, { method: "PATCH", body: { is_active: !plan.is_active } });
      await invalidate();
    } catch (err) {
      toast.show(actionError(err));
    }
  };

  const plans = q.data?.results;
  return (
    <div className="grid gap-6 pt-4 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <DataTable
          caption={t.tabs.dues}
          rows={plans}
          loading={q.isLoading}
          error={q.error}
          onRetry={() => void q.refetch()}
          rowKey={(r) => r.id}
          empty={{ title: d.empty, body: d.emptyHint }}
          columns={[
            { key: "name", header: d.name, cell: (r) => r.name },
            { key: "amount", header: d.amount, cell: (r) => formatMoney(r.amount, r.currency) },
            { key: "freq", header: d.frequency, cell: (r) => d.frequencies[r.frequency] },
            { key: "start", header: d.start, cell: (r) => formatDate(r.start_date) },
            {
              key: "active",
              header: d.active,
              cell: (r) =>
                can("estate.manage") ? (
                  <Button variant="secondary" onClick={() => void toggle(r)}>
                    {r.is_active ? d.pause : d.resume}
                  </Button>
                ) : r.is_active ? (
                  strings.common.yes
                ) : (
                  d.paused
                ),
            },
          ]}
        />
      </div>
      {can("estate.manage") && (
        <Card title={d.add} className="space-y-4">
          {error && <p className="text-sm text-danger-700">{error}</p>}
          <TextField label={d.name} hint={d.nameHint} value={form.name} error={errors.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <MoneyInput label={d.amount} value={form.amount} error={errors.amount} onChange={(v) => setForm({ ...form, amount: v })} />
          <Select
            label={d.frequency}
            value={form.frequency}
            options={optionsFrom(d.frequencies)}
            onChange={(e) => setForm({ ...form, frequency: e.target.value as RentFrequency })}
          />
          <TextField label={d.start} type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
          <Button onClick={() => void add()} loading={busy}>
            {d.add}
          </Button>
        </Card>
      )}
    </div>
  );
}

// ---- Announcements --------------------------------------------------------------------------------

function News({ estate }: { estate: Estate }) {
  const { org, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const idem = useIdempotencyKey();
  const list = usePaginatedList<Announcement>("/announcements/", { estate: estate.id });
  const [form, setForm] = useState({ title: "", body: "", audience: "all", urgent: false });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const n = t.news;

  const send = async () => {
    const e: Record<string, string> = {};
    if (!form.title.trim()) e.title = strings.common.required;
    if (!form.body.trim()) e.body = strings.common.required;
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    try {
      const body = { ...form, estate: estate.id };
      const a = await api<Announcement>(`/orgs/${org.id}/announcements/`, {
        method: "POST",
        body,
        idempotencyKey: idem.keyFor(body),
      });
      idem.reset();
      await invalidate();
      toast.show(fmt(n.sent, { push: a.push_sent, sms: a.sms_sent }));
      setForm({ title: "", body: "", audience: "all", urgent: false });
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-6 pt-4 lg:grid-cols-3">
      <div className="space-y-3 lg:col-span-2">
        {list.rows && list.rows.length === 0 && <p className="text-ink-600">{n.empty}</p>}
        {(list.rows ?? []).map((a) => (
          <Card key={a.id} as="article" title={a.title}>
            <p className="whitespace-pre-wrap text-ink-800">{a.body}</p>
            <p className="mt-3 text-sm text-ink-600">
              {formatDateTime(a.created_at)} · {n.audiences[a.audience]} · {fmt(n.reach, { push: a.push_sent, sms: a.sms_sent })}
            </p>
          </Card>
        ))}
      </div>
      {can("estate.manage") && (
        <Card title={n.send} className="space-y-4">
          {error && <p className="text-sm text-danger-700">{error}</p>}
          <TextField label={n.title} maxLength={120} value={form.title} error={errors.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <TextArea label={n.body} rows={5} maxLength={2000} value={form.body} error={errors.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
          <Select label={n.audience} value={form.audience} options={optionsFrom(n.audiences)} onChange={(e) => setForm({ ...form, audience: e.target.value })} />
          <Checkbox label={n.urgent} hint={n.urgentHint} checked={form.urgent} onChange={(e) => setForm({ ...form, urgent: e.target.checked })} />
          <Button onClick={() => void send()} loading={busy}>
            {n.send}
          </Button>
        </Card>
      )}
    </div>
  );
}

// ---- Settings -------------------------------------------------------------------------------------

function Settings({ estate }: { estate: Estate }) {
  const { org } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [form, setForm] = useState({
    panic_enabled: estate.panic_enabled,
    alert_residents: estate.alert_residents,
    gate_instructions: estate.gate_instructions,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const s = t.settings;
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/orgs/${org.id}/estates/${estate.id}/`, { method: "PATCH", body: form });
      await invalidate();
      toast.show(s.saved);
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title={s.title} className="mt-4 max-w-xl space-y-4">
      {error && <p className="text-sm text-danger-700">{error}</p>}
      <Switch label={s.panic} hint={s.panicHint} checked={form.panic_enabled} onChange={(v) => setForm({ ...form, panic_enabled: v })} />
      <Switch
        label={s.alertResidents}
        hint={s.alertResidentsHint}
        checked={form.alert_residents}
        onChange={(v) => setForm({ ...form, alert_residents: v })}
      />
      <TextField
        label={s.gateInstructions}
        hint={s.gateInstructionsHint}
        maxLength={300}
        value={form.gate_instructions}
        onChange={(e) => setForm({ ...form, gate_instructions: e.target.value })}
      />
      <Button onClick={() => void save()} loading={busy}>
        {strings.common.saveChanges}
      </Button>
    </Card>
  );
}

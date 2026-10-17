import { useState, type FormEvent } from "react";

import { Badge, Banner, Button, Card, DataTable, DescriptionList, EmptyState, LoadingBlock, PageHeader, Select, TextField, useToast, type BadgeTone } from "../../components";
import { fmt, strings } from "../../i18n";
import { ApiError, api } from "../../lib/api";
import { formatDateTime } from "../../lib/dates";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, useOrgQuery, usePaginatedList } from "../../lib/queries";
import type { Estate, GateCheck, GatePassStatus, Paginated } from "../../lib/types";
import { actionError } from "../shared";

const t = strings.gate;
const TONE: Record<GatePassStatus, BadgeTone> = { active: "success", used: "neutral", expired: "neutral", cancelled: "neutral" };

export function GateDesk() {
  const estates = useOrgQuery<Paginated<Estate>>("/estates/");
  const [estateId, setEstateId] = useState<string | null>(null);
  const list = estates.data?.results ?? [];
  const current = estateId ?? list[0]?.id ?? null;
  if (estates.isLoading) return <LoadingBlock />;
  if (!current) {
    return (
      <>
        <PageHeader title={t.title} description={t.intro} />
        <EmptyState title={strings.estates.empty} body={strings.estates.emptyHint} />
      </>
    );
  }
  return (
    <>
      <PageHeader title={t.title} description={t.intro} />
      {list.length > 1 && (
        <Select
          containerClassName="mb-4 w-full max-w-xs"
          label={strings.security.estate}
          value={current}
          options={list.map((e) => ({ value: e.id, label: e.name }))}
          onChange={(e) => setEstateId(e.target.value)}
        />
      )}
      <Gate estateId={current} />
    </>
  );
}

function Gate({ estateId }: { estateId: string }) {
  const { org } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const log = usePaginatedList<GateCheck>("/gate/", { estate: estateId });
  const [code, setCode] = useState("");
  const [pass, setPass] = useState<GateCheck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const check = async (e: FormEvent) => {
    e.preventDefault();
    setBusy("check");
    setError(null);
    setPass(null);
    try {
      setPass(await api<GateCheck>(`/orgs/${org.id}/gate/verify/`, { method: "POST", body: { estate: estateId, code } }));
    } catch (err) {
      setError(err instanceof ApiError && err.status === 404 ? err.message || t.invalid : actionError(err));
    } finally {
      setBusy(null);
    }
  };

  const act = async (kind: "check-in" | "check-out" | "deny") => {
    if (!pass) return;
    setBusy(kind);
    try {
      const body = { note: kind === "deny" ? reason.trim() : "" };
      const res = await api<GateCheck>(`/orgs/${org.id}/gate/${pass.id}/${kind}/`, { method: "POST", body });
      await invalidate();
      toast.show(kind === "check-in" ? t.checkedIn : kind === "check-out" ? t.checkedOut : t.denied);
      if (kind === "check-in") setPass(res);
      else {
        setPass(null);
        setCode("");
      }
    } catch (err) {
      toast.show(actionError(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-4">
        <Card>
          <form onSubmit={(e) => void check(e)} className="space-y-3">
            <TextField
              label={t.code}
              inputMode="numeric"
              autoComplete="off"
              maxLength={7}
              className="font-mono text-2xl tracking-widest"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/[^\d ]/g, ""))}
            />
            <Button type="submit" loading={busy === "check"} disabled={code.replace(/\D/g, "").length !== 6}>
              {t.check}
            </Button>
          </form>
        </Card>
        {error && <Banner tone="error" title={error} />}
        {pass && (
          <Card title={t.valid} className="space-y-4">
            <DescriptionList
              items={[
                { label: t.visitor, value: `${pass.visitor_name} (${t.kinds[pass.kind]})` },
                { label: t.host, value: `${pass.host_name}, ${pass.house}` },
                pass.artisan && {
                  label: t.kinds.artisan,
                  value: (
                    <span className="flex flex-wrap items-center gap-2">
                      {pass.artisan.display_name}
                      <Badge tone={pass.artisan.is_verified ? "success" : "warning"}>
                        {pass.artisan.is_verified ? t.verifiedArtisan : t.unverifiedArtisan}
                      </Badge>
                    </span>
                  ),
                },
                { label: strings.estates.member.status, value: fmt(t.entries, { uses: pass.uses, max: pass.max_uses }) },
                { label: t.until, value: formatDateTime(pass.valid_to) },
                pass.note !== "" && { label: strings.security.note, value: pass.note },
              ]}
            />
            <div className="flex flex-wrap gap-2">
              {pass.status === "active" && (
                <Button onClick={() => void act("check-in")} loading={busy === "check-in"}>
                  {t.checkIn}
                </Button>
              )}
              <Button variant="secondary" onClick={() => void act("check-out")} loading={busy === "check-out"}>
                {t.checkOut}
              </Button>
            </div>
            {pass.status === "active" && (
              <div className="space-y-2">
                <TextField label={t.denyReason} optional value={reason} onChange={(e) => setReason(e.target.value)} />
                <Button variant="secondary" onClick={() => void act("deny")} loading={busy === "deny"}>
                  {t.deny}
                </Button>
              </div>
            )}
          </Card>
        )}
      </div>
      <div className="lg:col-span-2">
        <h2 className="mb-3 font-display text-lg font-semibold text-ink-900">{t.log}</h2>
        <DataTable
          caption={t.log}
          rows={log.rows}
          loading={log.isLoading}
          error={log.error}
          onRetry={log.refetch}
          hasMore={log.hasMore}
          onLoadMore={log.loadMore}
          loadingMore={log.loadingMore}
          rowKey={(r) => r.id}
          empty={{ title: t.empty }}
          columns={[
            { key: "v", header: t.visitor, cell: (r) => `${r.visitor_name} (${t.kinds[r.kind]})` },
            { key: "h", header: t.host, cell: (r) => `${r.host_name}, ${r.house}` },
            { key: "until", header: t.until, cell: (r) => formatDateTime(r.valid_to) },
            { key: "s", header: strings.estates.member.status, cell: (r) => <Badge tone={TONE[r.status]}>{t.statuses[r.status]}</Badge> },
            {
              key: "e",
              header: strings.security.log,
              cell: (r) => r.events.map((e) => `${t.events[e.kind]} ${formatDateTime(e.created_at)}`).join(" · ") || "—",
            },
          ]}
        />
      </div>
    </div>
  );
}

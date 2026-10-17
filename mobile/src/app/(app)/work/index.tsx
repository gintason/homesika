import { useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { artisanApi, type ArtisanJob, type CheckStatus, type MyArtisan } from "@/api";
import { Banner, Button, Card, Checkbox, EmptyState, ListRow, Screen, SkeletonCard, Text } from "@/components";
import { ArtisanStats, PriorityBadge, ToneBadge, VerifiedBadge } from "@/components/repairs";
import { keys, useJobs, useMyArtisan } from "@/hooks/queries";
import { errorText } from "@/lib/api";
import { formatDateTime } from "@/lib/date";

const CHECK_TONE: Record<CheckStatus, "neutral" | "info" | "warning" | "success" | "danger"> = {
  not_started: "neutral",
  processing: "info",
  pending: "warning",
  passed: "success",
  failed: "danger",
};

/** Artisan hub: sign up, or see the Verified checklist, availability and jobs. */
export default function WorkHome() {
  const { t } = useTranslation();
  const me = useMyArtisan();

  if (me.isPending) {
    return (
      <Screen title={t("work.title")} back>
        <SkeletonCard label={t("common.loading")} />
      </Screen>
    );
  }
  if (me.error) {
    return (
      <Screen title={t("work.title")} back>
        <Banner message={`${t("errors.loadFailed")} ${errorText(me.error)}`} onRetry={() => me.refetch()} retryLabel={t("common.retry")} />
      </Screen>
    );
  }
  if (me.data === null) {
    return (
      <Screen title={t("work.title")} back footer={<Button title={t("work.start")} onPress={() => router.push("/work/apply")} />}>
        <EmptyState icon="construct-outline" title={t("work.introTitle")} body={t("work.introBody")} />
        <Card>
          <Text>{t("work.steps")}</Text>
        </Card>
      </Screen>
    );
  }
  return <ArtisanHome profile={me.data} onRefresh={() => me.refetch()} refreshing={me.isRefetching} />;
}

function ArtisanHome({ profile, onRefresh, refreshing }: { profile: MyArtisan; onRefresh: () => void; refreshing: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [showHistory, setShowHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const active = useJobs("active");
  const history = useJobs("history", { enabled: showHistory });
  const jobs = active.data?.pages.flatMap((p) => p.results) ?? [];
  const past = history.data?.pages.flatMap((p) => p.results) ?? [];
  const req = profile.requirements;
  const check = (kind: "id" | "phone" | "address") => profile.checks.find((c) => c.kind === kind)?.status ?? "not_started";
  const blocked = profile.status === "suspended" || profile.status === "removed";

  const toggleAvailable = async (next: boolean) => {
    setSaving(true);
    setError(null);
    try {
      qc.setQueryData(keys.artisan, await artisanApi.update({ is_available: next }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  const vouchStatus = (have: number, need: number): CheckStatus => (have >= need ? "passed" : have > 0 ? "pending" : "not_started");

  return (
    <Screen
      title={t("work.title")}
      back
      onRefresh={() => {
        onRefresh();
        void active.refetch();
      }}
      refreshing={refreshing}
    >
      {error ? <Banner message={error} /> : null}
      {blocked ? <Banner message={t("work.suspended", { reason: profile.status_reason })} /> : null}

      <Card>
        <View className="flex-row flex-wrap items-center gap-2">
          <Text variant="heading" accessibilityRole="header" className="flex-1">
            {profile.display_name}
          </Text>
          {profile.is_verified ? <VerifiedBadge /> : <ToneBadge tone="warning" label={t(`work.status.${profile.status}`)} />}
        </View>
        <ArtisanStats avg={profile.rating_avg} count={profile.rating_count} jobs={profile.jobs_completed} />
        {!blocked ? (
          <Checkbox checked={profile.is_available} disabled={saving} onChange={(v) => void toggleAvailable(v)} label={t("work.available")}>
            <View className="flex-1 gap-1">
              <Text variant="label">{t("work.available")}</Text>
              <Text variant="caption">{t("work.availableHint")}</Text>
            </View>
          </Checkbox>
        ) : null}
      </Card>

      <Card>
        <Text variant="heading" accessibilityRole="header">
          {t("work.checklist")}
        </Text>
        {req.complete ? <Banner tone="success" message={t("work.checkedAll")} /> : null}
        <CheckRow label={t("work.check.id")} status={check("id")} onPress={() => router.push("/work/id-check")} />
        <CheckRow label={t("work.check.phone")} status={check("phone")} />
        <CheckRow
          label={t("work.check.address")}
          status={check("address")}
          onPress={profile.verification_mode === "nin" ? () => router.push("/work/address") : undefined}
        />
        <CheckRow
          label={t("work.check.guarantors", { count: req.guarantors, needed: req.guarantors_needed })}
          status={vouchStatus(req.guarantors, req.guarantors_needed)}
          onPress={() => router.push("/work/people")}
        />
        <CheckRow
          label={t("work.check.references", { count: req.references, needed: req.references_needed })}
          status={vouchStatus(req.references, req.references_needed)}
          onPress={() => router.push("/work/people")}
        />
        {check("id") !== "passed" ? <Button title={t("work.doId")} variant="secondary" onPress={() => router.push("/work/id-check")} /> : null}
        {!req.complete && (req.guarantors < req.guarantors_needed || req.references < req.references_needed) ? (
          <Button title={t("work.addPeople")} variant="ghost" onPress={() => router.push("/work/people")} />
        ) : null}
      </Card>

      <View className="gap-2">
        <Text variant="heading" accessibilityRole="header">
          {t("work.jobs")}
        </Text>
        {active.error ? <Banner message={errorText(active.error)} onRetry={() => active.refetch()} retryLabel={t("common.retry")} /> : null}
        {active.isPending ? (
          <SkeletonCard label={t("common.loading")} />
        ) : jobs.length === 0 ? (
          <Card>
            <Text variant="label">{t("work.noJobs")}</Text>
            <Text variant="caption">{profile.is_verified ? t("work.noJobsBody") : t("work.noJobsPending")}</Text>
          </Card>
        ) : (
          <JobList jobs={jobs} />
        )}
        {showHistory ? (
          past.length ? <JobList jobs={past} /> : history.isPending ? <SkeletonCard label={t("common.loading")} /> : null
        ) : (
          <Button title={t("work.history")} variant="ghost" onPress={() => setShowHistory(true)} />
        )}
      </View>
    </Screen>
  );
}

function CheckRow({ label, status, onPress }: { label: string; status: CheckStatus; onPress?: () => void }) {
  const { t } = useTranslation();
  const statusText = t(`work.checkStatus.${status}`);
  return (
    <ListRow
      title={label}
      chevron={Boolean(onPress) && status !== "passed"}
      onPress={status !== "passed" ? onPress : undefined}
      accessibilityLabel={`${label}, ${statusText}`}
      trailing={<ToneBadge tone={CHECK_TONE[status]} label={statusText} />}
    />
  );
}

function JobList({ jobs }: { jobs: ArtisanJob[] }) {
  const { t } = useTranslation();
  return (
    <View className="rounded-lg border border-surface-line bg-surface-card px-4">
      {jobs.map((j, i) => {
        const status = t(`work.job.status.${j.status}`);
        const when = j.scheduled_for ? formatDateTime(j.scheduled_for) : j.location.area;
        return (
          <View key={j.id} className={i > 0 ? "border-t border-surface-line" : ""}>
            <ListRow
              title={j.ticket.title}
              subtitle={`${j.organization} · ${when}`}
              chevron
              accessibilityLabel={`${j.ticket.title}, ${status}, ${j.organization}, ${when}`}
              onPress={() => router.push({ pathname: "/work/job/[id]", params: { id: j.id } })}
              trailing={
                <>
                  <ToneBadge tone={j.status === "offered" ? "gold" : "info"} label={status} />
                  <PriorityBadge priority={j.ticket.priority} />
                </>
              }
            />
          </View>
        );
      })}
    </View>
  );
}

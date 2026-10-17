import { useState } from "react";
import { Link, useParams } from "react-router";

import {
  Badge,
  Banner,
  Button,
  ButtonLink,
  Card,
  ConfirmDialog,
  CopyButton,
  DescriptionList,
  PageHeader,
  StatusBadge,
  TextField,
  useToast,
} from "../../components";
import { fmt, strings } from "../../i18n";
import { api } from "../../lib/api";
import { listingPrice, publicListingUrl } from "../../lib/listings";
import { useOrg } from "../../lib/org";
import { formatPhone } from "../../lib/phone";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { Listing } from "../../lib/types";
import { QueryState, actionError, linkClass } from "../shared";
import { PhotoManager } from "./PhotoManager";
import { ViewingSlots } from "./ViewingSlots";

const t = strings.listings;

export function ListingDetail() {
  const { listingId = "" } = useParams();
  const q = useOrgQuery<Listing>(`/listings/${listingId}/`);
  return (
    <QueryState data={q.data} isLoading={q.isLoading} error={q.error} refetch={q.refetch}>
      {(listing) => <ListingView listing={listing} />}
    </QueryState>
  );
}

function ListingView({ listing }: { listing: Listing }) {
  const { org, base, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const canManage = can("listing.manage");
  type Kind = "publish" | "let" | "unpublish" | "archive";
  const [busy, setBusy] = useState<Kind | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmLet, setConfirmLet] = useState(false);
  const url = publicListingUrl(listing.ref);

  const paths: Record<Kind, string> = { publish: "publish", let: "mark-let", unpublish: "unpublish", archive: "archive" };
  const done: Record<Kind, string> = { publish: t.published, let: t.markedLet, unpublish: t.unpublished, archive: t.archived };
  const act = async (kind: Kind) => {
    setBusy(kind);
    setError(null);
    try {
      await api<Listing>(`/orgs/${org.id}/listings/${listing.id}/${paths[kind]}/`, { method: "POST" });
      await invalidate();
      toast.show(done[kind]);
      setConfirmLet(false);
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(null);
    }
  };

  const actions = canManage ? (
    <>
      <ButtonLink variant="secondary" to={`${base}/listings/${listing.id}/edit`}>
        {strings.common.edit}
      </ButtonLink>
      {listing.status !== "published" && (
        <Button onClick={() => void act("publish")} loading={busy === "publish"}>
          {t.publish}
        </Button>
      )}
      {listing.status === "published" && (
        <Button variant="secondary" onClick={() => setConfirmLet(true)}>
          {t.markLet}
        </Button>
      )}
      {listing.status === "published" && (
        <Button variant="ghost" onClick={() => void act("unpublish")} loading={busy === "unpublish"}>
          {t.unpublish}
        </Button>
      )}
      {listing.status !== "archived" && listing.status !== "published" && (
        <Button variant="ghost" onClick={() => void act("archive")} loading={busy === "archive"}>
          {t.archive}
        </Button>
      )}
    </>
  ) : undefined;

  return (
    <>
      <PageHeader
        title={listing.title}
        back={{ to: `${base}/listings`, label: t.title }}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={listing.status} />
            <span>{listingPrice(listing)}</span>
            <span aria-hidden="true">·</span>
            <span>{[listing.area, listing.city].filter(Boolean).join(", ")}</span>
            {listing.ai_generated && <Badge tone="info">{t.aiDrafted}</Badge>}
          </span>
        }
        actions={actions}
      />
      <div className="space-y-6">
        {error && <Banner tone="error">{error}</Banner>}

        <Card title={t.share}>
          <div className="space-y-4">
            {listing.status !== "published" && <Banner tone="warning">{t.notPublishedYet}</Banner>}
            <div className="flex flex-wrap items-end gap-2">
              <TextField
                containerClassName="min-w-0 flex-1"
                label={t.publicLink}
                value={url}
                readOnly
                onFocus={(e) => e.currentTarget.select()}
              />
              <CopyButton text={url} label={t.copyLink} />
            </div>
            <div className="space-y-2">
              <p className="text-sm font-medium text-ink-800">{t.whatsappCaption}</p>
              {listing.whatsapp_caption ? (
                <>
                  <p className="whitespace-pre-wrap rounded-md bg-surface-muted p-3 text-base text-ink-800">{listing.whatsapp_caption}</p>
                  <CopyButton text={`${listing.whatsapp_caption}\n${url}`} label={t.copyCaption} />
                </>
              ) : (
                <p className="text-base text-ink-600">{t.noCaption}</p>
              )}
            </div>
          </div>
        </Card>

        <PhotoManager listing={listing} />

        <Card title={strings.listings.detail}>
          <DescriptionList
            items={[
              { label: t.bedrooms, value: listing.bedrooms ?? "" },
              { label: t.bathrooms, value: listing.bathrooms ?? "" },
              { label: t.address, value: listing.address },
              { label: t.contactPhone, value: formatPhone(listing.contact_phone) },
              {
                label: t.leads,
                value: (
                  <Link to={`${base}/leads?listing=${listing.id}`} className={linkClass}>
                    {fmt(t.leadCount, { count: listing.lead_count })}
                  </Link>
                ),
              },
              { label: t.features, value: listing.features.join(", ") },
            ]}
          />
          {listing.description && (
            <div className="mt-4">
              <p className="text-sm text-ink-600">{t.description}</p>
              <p className="mt-1 whitespace-pre-wrap text-base text-ink-800">{listing.description}</p>
            </div>
          )}
        </Card>

        <ViewingSlots listingId={listing.id} />
      </div>
      <ConfirmDialog
        open={confirmLet}
        onClose={() => setConfirmLet(false)}
        onConfirm={() => void act("let")}
        title={t.markLetTitle}
        description={t.markLetBody}
        confirmLabel={t.markLet}
        loading={busy === "let"}
        error={error}
      />
    </>
  );
}

import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { Banner, Button, Card, EmptyState, LoadingBlock, MoneyInput, Select, TextField } from "../../components";
import { fmt, strings } from "../../i18n";
import { errorText } from "../../lib/api";
import { listingPrice } from "../../lib/listings";
import { parseMoneyInput } from "../../lib/money";
import { usePublicGet } from "../../lib/usePublicGet";
import type { PublicListing } from "../../lib/types";
import { PayLayout } from "../pay/PayLayout";

const t = strings.publicListing;
const BEDROOMS = ["1", "2", "3", "4", "5"].map((n) => ({ value: n, label: n }));

/** Public search: GET /listings/?area=&max_rent=&bedrooms= (no login). */
export function PublicSearch() {
  const [params, setParams] = useSearchParams();
  const area = params.get("area") ?? "";
  const maxRent = params.get("max_rent") ?? "";
  const bedrooms = params.get("bedrooms") ?? "";
  const { data, error, loading, retry } = usePublicGet<PublicListing[]>("/listings/", { area, max_rent: maxRent, bedrooms });

  const [draftArea, setDraftArea] = useState(area);
  const [draftRent, setDraftRent] = useState(maxRent);
  const [draftBeds, setDraftBeds] = useState(bedrooms);
  const [rentError, setRentError] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const rent = draftRent.trim() ? parseMoneyInput(draftRent) : "";
    if (rent === null) {
      setRentError(strings.fields.amountInvalid);
      return;
    }
    setRentError(null);
    const next = new URLSearchParams();
    if (draftArea.trim()) next.set("area", draftArea.trim());
    if (rent) next.set("max_rent", rent);
    if (draftBeds) next.set("bedrooms", draftBeds);
    setParams(next);
  };

  return (
    <PayLayout title={t.search} footer={t.poweredBy} wide>
      <p className="text-base text-ink-600">{t.searchIntro}</p>
      <Card>
        <form onSubmit={submit} noValidate role="search" className="grid gap-4 sm:grid-cols-3 sm:items-start">
          <TextField label={t.area} hint={t.areaHint} value={draftArea} onChange={(e) => setDraftArea(e.target.value)} />
          <MoneyInput label={t.maxRent} optional value={draftRent} onChange={setDraftRent} error={rentError} />
          <Select label={t.minBedrooms} value={draftBeds} placeholder={t.anyBedrooms} options={BEDROOMS} onChange={(e) => setDraftBeds(e.target.value)} />
          <Button type="submit" className="sm:col-span-3">
            {t.searchButton}
          </Button>
        </form>
      </Card>
      {loading ? (
        <LoadingBlock rows={3} />
      ) : error || !data ? (
        <Banner tone="error" onRetry={retry}>
          {errorText(error)}
        </Banner>
      ) : data.length === 0 ? (
        <EmptyState title={t.noResults} />
      ) : (
        <ul className="space-y-4">
          {data.map((l) => (
            <li key={l.ref}>
              <Card as="article" className="flex gap-4 p-4 md:p-4">
                {l.photos[0] && (
                  <img
                    src={l.photos[0].url}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    className="h-24 w-28 shrink-0 rounded-md bg-surface-muted object-cover"
                  />
                )}
                <div className="min-w-0 space-y-1">
                  <h2 className="font-display text-lg font-semibold text-ink-900">
                    <Link to={`/l/${encodeURIComponent(l.ref)}`} className="underline-offset-4 hover:underline">
                      {l.title}
                    </Link>
                  </h2>
                  <p className="font-semibold text-ink-800">{listingPrice(l)}</p>
                  <p className="text-sm text-ink-600">
                    {[l.area, l.city].filter(Boolean).join(", ")}
                    {l.bedrooms != null ? ` · ${fmt(t.bedrooms, { count: l.bedrooms })}` : ""}
                  </p>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </PayLayout>
  );
}

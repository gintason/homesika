import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";

import { Badge, Banner, Button, Card, LoadingBlock, PhoneInput, Select, TextArea, TextField } from "../../components";
import { fmt, strings } from "../../i18n";
import { api, ApiError, errorText } from "../../lib/api";
import { formatDateTime } from "../../lib/dates";
import { listingPrice } from "../../lib/listings";
import { normalisePhone } from "../../lib/phone";
import { usePublicGet } from "../../lib/usePublicGet";
import type { PublicListingDetail } from "../../lib/types";
import { PayLayout } from "../pay/PayLayout";

const t = strings.publicListing;

/** Same rule as the API: E.164 after Nigerian normalisation. */
export function validPublicPhone(raw: string): boolean {
  return /^\+\d{10,15}$/.test(normalisePhone(raw));
}

function useContactForm() {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [errors, setErrors] = useState<{ name?: string; phone_number?: string; slot?: string; message?: string }>({});
  const check = (extra: Record<string, string | undefined> = {}) => {
    const found = {
      name: name.trim() ? undefined : strings.common.required,
      phone_number: !phone.trim() ? strings.common.required : validPublicPhone(phone) ? undefined : strings.fields.phoneInvalid,
      ...extra,
    };
    setErrors(found);
    return Object.values(found).every((v) => !v);
  };
  const fromApi = (e: unknown): string | null => {
    if (e instanceof ApiError && Object.keys(e.fieldErrors).length) {
      setErrors(e.fieldErrors);
      return e.formErrors[0] ?? null;
    }
    return errorText(e);
  };
  return { name, setName, phone, setPhone, errors, setErrors, check, fromApi };
}

export function PublicListingPage() {
  const { ref = "" } = useParams();
  const { data, error, loading, retry, reload } = usePublicGet<PublicListingDetail>(`/listings/${encodeURIComponent(ref)}/`);

  return (
    <PayLayout title={data?.title ?? t.title} footer={t.poweredBy} wide>
      {loading ? (
        <LoadingBlock rows={4} />
      ) : error || !data ? (
        error?.status === 404 ? (
          <Banner tone="info">
            {t.notFound}{" "}
            <Link to="/listings" className="font-semibold underline">
              {t.search}
            </Link>
          </Banner>
        ) : (
          <Banner tone="error" onRetry={retry}>
            {errorText(error)}
          </Banner>
        )
      ) : (
        <ListingBody listing={data} reload={reload} />
      )}
    </PayLayout>
  );
}

function ListingBody({ listing, reload }: { listing: PublicListingDetail; reload: () => void }) {
  const [cover, ...rest] = listing.photos;
  return (
    <>
      {cover && (
        <img
          src={cover.url}
          alt={cover.caption || fmt(t.photoAlt, { n: 1, title: listing.title })}
          decoding="async"
          className="aspect-[4/3] w-full rounded-lg bg-surface-muted object-cover"
        />
      )}
      {rest.length > 0 && (
        <ul className="flex gap-2 overflow-x-auto pb-1">
          {rest.map((p, i) => (
            <li key={p.id} className="shrink-0">
              <a href={p.url} target="_blank" rel="noopener noreferrer">
                <img
                  src={p.url}
                  alt={p.caption || fmt(t.photoAlt, { n: i + 2, title: listing.title })}
                  loading="lazy"
                  decoding="async"
                  className="h-24 w-32 rounded-md bg-surface-muted object-cover"
                />
              </a>
            </li>
          ))}
        </ul>
      )}
      <Card>
        <p className="font-display text-2xl font-bold text-ink-900">{listingPrice(listing)}</p>
        <p className="mt-1 text-base text-ink-800">{[listing.area, listing.city].filter(Boolean).join(", ")}</p>
        <p className="mt-2 flex flex-wrap gap-2">
          {listing.bedrooms != null && <Badge>{fmt(t.bedrooms, { count: listing.bedrooms })}</Badge>}
          {listing.bathrooms != null && <Badge>{fmt(t.bathrooms, { count: listing.bathrooms })}</Badge>}
        </p>
        <p className="mt-3 text-sm text-ink-600">{fmt(t.by, { landlord: listing.landlord })}</p>
      </Card>
      {listing.features.length > 0 && (
        <Card title={t.features}>
          <ul className="flex flex-wrap gap-2">
            {listing.features.map((f) => (
              <li key={f} className="rounded-pill bg-primary-50 px-3 py-1 text-sm font-medium text-primary-800">
                {f}
              </li>
            ))}
          </ul>
        </Card>
      )}
      {listing.description && (
        <Card title={t.about}>
          <p className="whitespace-pre-wrap text-base text-ink-800">{listing.description}</p>
        </Card>
      )}
      <BookViewing listing={listing} reload={reload} />
      <Enquire listingRef={listing.ref} />
    </>
  );
}

function BookViewing({ listing, reload }: { listing: PublicListingDetail; reload: () => void }) {
  const c = useContactForm();
  const [slot, setSlot] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [booked, setBooked] = useState<string | null>(null);

  if (booked) {
    return (
      <Card title={t.book}>
        <Banner tone="success">{fmt(t.booked, { when: formatDateTime(booked) })}</Banner>
      </Card>
    );
  }
  if (listing.slots.length === 0) {
    return (
      <Card title={t.book}>
        <p className="text-base text-ink-600">{t.noSlots}</p>
      </Card>
    );
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!c.check({ slot: slot ? undefined : t.pickSlotRequired })) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ status: string; starts_at: string }>(`/listings/${encodeURIComponent(listing.ref)}/book/`, {
        method: "POST",
        auth: false,
        body: { name: c.name.trim(), phone_number: normalisePhone(c.phone), slot },
      });
      setBooked(res?.starts_at ?? listing.slots.find((s) => s.id === slot)?.starts_at ?? "");
    } catch (err) {
      if (err instanceof ApiError && err.code === "slot_unavailable") {
        setError(err.message || t.slotGone);
        setSlot("");
        reload();
      } else {
        setError(c.fromApi(err));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title={t.book}>
      <form onSubmit={submit} noValidate className="space-y-4">
        <p className="text-base text-ink-600">{t.bookIntro}</p>
        {error && <Banner tone="error">{error}</Banner>}
        <Select
          label={t.pickSlot}
          value={slot}
          placeholder={t.pickSlot}
          options={listing.slots.map((s) => ({ value: s.id, label: formatDateTime(s.starts_at) }))}
          onChange={(e) => {
            setSlot(e.target.value);
            c.setErrors((x) => ({ ...x, slot: undefined }));
          }}
          error={c.errors.slot}
        />
        <TextField label={t.yourName} autoComplete="name" maxLength={120} value={c.name} onChange={(e) => c.setName(e.target.value)} error={c.errors.name} />
        <PhoneInput value={c.phone} onChange={c.setPhone} error={c.errors.phone_number} />
        <Button type="submit" loading={busy} fullWidth>
          {t.bookButton}
        </Button>
      </form>
    </Card>
  );
}

function Enquire({ listingRef }: { listingRef: string }) {
  const c = useContactForm();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!c.check()) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/listings/${encodeURIComponent(listingRef)}/enquire/`, {
        method: "POST",
        auth: false,
        body: { name: c.name.trim(), phone_number: normalisePhone(c.phone), message: message.trim() },
      });
      setSent(true);
    } catch (err) {
      setError(c.fromApi(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title={t.enquire}>
      {sent ? (
        <Banner tone="success">{t.sent}</Banner>
      ) : (
        <form onSubmit={submit} noValidate className="space-y-4">
          <p className="text-base text-ink-600">{t.enquireIntro}</p>
          {error && <Banner tone="error">{error}</Banner>}
          <TextField label={t.yourName} autoComplete="name" maxLength={120} value={c.name} onChange={(e) => c.setName(e.target.value)} error={c.errors.name} />
          <PhoneInput value={c.phone} onChange={c.setPhone} error={c.errors.phone_number} />
          <TextArea label={t.message} optional maxLength={1000} value={message} onChange={(e) => setMessage(e.target.value)} error={c.errors.message} />
          <Button type="submit" variant="secondary" loading={busy} fullWidth>
            {t.send}
          </Button>
        </form>
      )}
    </Card>
  );
}

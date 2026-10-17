import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router";

import {
  Banner,
  Button,
  Card,
  ChipsInput,
  LoadingBlock,
  MoneyInput,
  PageHeader,
  PhoneInput,
  Select,
  TextArea,
  TextField,
  optionsFrom,
  useToast,
} from "../../components";
import { strings } from "../../i18n";
import { api } from "../../lib/api";
import { useForm } from "../../lib/form";
import { formatPlainAmount, isPositive, parseMoneyInput } from "../../lib/money";
import { useMarkets } from "../../lib/markets";
import { useOrg } from "../../lib/org";
import { normalisePhone } from "../../lib/phone";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { Listing, RentPeriod, Unit } from "../../lib/types";
import { parseWhole } from "../shared";
import { ListingWriter, type DraftField } from "./ListingWriter";

const t = strings.listings;

const EMPTY = {
  title: "",
  area: "",
  city: "Lagos",
  address: "",
  bedrooms: "",
  bathrooms: "",
  rent_amount: "",
  rent_period: "year" as RentPeriod,
  contact_phone: "",
  unit: "",
  description: "",
  whatsapp_caption: "",
  features: [] as string[],
  ai_generated: false,
};

function countError(value: string): string | undefined {
  const n = parseWhole(value);
  return n !== null && (Number.isNaN(n) || n > 20) ? t.wholeNumber : undefined;
}

export function ListingForm() {
  const { listingId } = useParams();
  const editing = Boolean(listingId);
  const { org, base, can } = useOrg();
  const navigate = useNavigate();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const existing = useOrgQuery<Listing>(`/listings/${listingId}/`, undefined, { enabled: editing });
  const units = useOrgQuery<Unit[]>("/units/", undefined, { enabled: can("property.view") });
  const [busy, setBusy] = useState(false);
  const form = useForm(EMPTY);
  const { setValues, set, values } = form;

  useEffect(() => {
    const l = existing.data;
    if (!l) return;
    setValues({
      title: l.title,
      area: l.area,
      city: l.city,
      address: l.address,
      bedrooms: l.bedrooms == null ? "" : String(l.bedrooms),
      bathrooms: l.bathrooms == null ? "" : String(l.bathrooms),
      rent_amount: formatPlainAmount(l.rent_amount),
      rent_period: l.rent_period,
      contact_phone: l.contact_phone,
      unit: l.unit ?? "",
      description: l.description,
      whatsapp_caption: l.whatsapp_caption,
      features: l.features ?? [],
      ai_generated: l.ai_generated,
    });
  }, [existing.data, setValues]);

  const applyDraft = (field: DraftField, value: string | string[]) => {
    if (field === "features") {
      const merged = [...values.features];
      for (const f of value as string[]) if (!merged.some((m) => m.toLowerCase() === f.toLowerCase())) merged.push(f);
      set("features", merged.slice(0, 30));
    } else {
      set(field, (field === "title" ? (value as string).slice(0, 140) : value) as string);
    }
    set("ai_generated", true);
    toast.show(strings.writer.used, "info");
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const v = form.values;
    const rent = parseMoneyInput(v.rent_amount);
    const phone = v.contact_phone.trim() ? normalisePhone(v.contact_phone) : "";
    if (
      !form.validate({
        title: v.title.trim() ? undefined : strings.common.required,
        area: v.area.trim() ? undefined : strings.common.required,
        rent_amount: !v.rent_amount.trim()
          ? strings.common.required
          : rent === null
            ? strings.fields.amountInvalid
            : isPositive(rent)
              ? undefined
              : strings.fields.amountZero,
        bedrooms: countError(v.bedrooms),
        bathrooms: countError(v.bathrooms),
        contact_phone: phone && !/^\+\d{10,15}$/.test(phone) ? strings.fields.phoneInvalid : undefined,
      })
    )
      return;
    setBusy(true);
    try {
      const saved = await api<Listing>(`/orgs/${org.id}/listings/${editing ? `${listingId}/` : ""}`, {
        method: editing ? "PATCH" : "POST",
        body: {
          title: v.title.trim(),
          area: v.area.trim(),
          city: v.city.trim(),
          address: v.address.trim(),
          bedrooms: parseWhole(v.bedrooms),
          bathrooms: parseWhole(v.bathrooms),
          rent_amount: rent,
          rent_period: v.rent_period,
          contact_phone: phone,
          unit: v.unit || null,
          description: v.description.trim(),
          whatsapp_caption: v.whatsapp_caption.trim(),
          features: v.features,
          ai_generated: v.ai_generated,
        },
      });
      await invalidate();
      toast.show(editing ? strings.common.saved : t.created);
      navigate(`${base}/listings/${saved.id}`);
    } catch (err) {
      form.fromApiError(err);
      setBusy(false);
    }
  };

  const unitOptions = (units.data ?? []).map((u) => ({ value: u.id, label: `${u.property_name} · ${u.label}` }));

  return (
    <>
      <PageHeader
        title={editing ? t.edit : t.add}
        back={{ to: editing ? `${base}/listings/${listingId}` : `${base}/listings`, label: strings.common.back }}
      />
      {editing && existing.isLoading ? (
        <LoadingBlock />
      ) : editing && existing.error ? (
        <Banner tone="error" onRetry={() => void existing.refetch()}>
          {strings.errors.loadFailed}
        </Banner>
      ) : (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <Card>
            <form onSubmit={submit} noValidate className="space-y-4">
              {form.formError && <Banner tone="error">{form.formError}</Banner>}
              <TextField label={t.listingTitle} hint={t.listingTitleHint} required maxLength={140} {...form.text("title")} />
              <div className="grid gap-4 sm:grid-cols-2">
                <TextField
                  label={t.area}
                  hint={t.areaHint}
                  required
                  maxLength={80}
                  list="listing-areas"
                  autoComplete="off"
                  {...form.text("area")}
                />
                <CityField value={form.values.city} onChange={(v) => form.set("city", v)} />
              </div>
              <TextField label={t.address} hint={t.addressHint} optional maxLength={255} {...form.text("address")} />
              <div className="grid gap-4 sm:grid-cols-2">
                <TextField label={t.bedrooms} optional inputMode="numeric" {...form.text("bedrooms")} />
                <TextField label={t.bathrooms} optional inputMode="numeric" {...form.text("bathrooms")} />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <MoneyInput
                  label={t.rentAmount}
                  required
                  value={values.rent_amount}
                  onChange={(v) => set("rent_amount", v)}
                  error={form.errors.rent_amount}
                  currencySymbol={org.currency === "NGN" ? "₦" : org.currency}
                />
                <Select label={t.rentPeriod} options={optionsFrom(t.periodOptions)} {...form.text("rent_period")} />
              </div>
              <ChipsInput
                label={t.features}
                hint={t.featuresHint}
                value={values.features}
                onChange={(v) => set("features", v)}
                error={form.errors.features}
              />
              <TextArea label={t.description} optional rows={6} {...form.text("description")} />
              <TextArea label={t.whatsappCaption} hint={t.whatsappCaptionHint} optional rows={4} {...form.text("whatsapp_caption")} />
              <PhoneInput
                label={t.contactPhone}
                hint={t.contactPhoneHint}
                optional
                value={values.contact_phone}
                onChange={(v) => set("contact_phone", v)}
                error={form.errors.contact_phone}
              />
              {can("property.view") && (
                <Select
                  label={t.unit}
                  hint={t.unitHint}
                  optional
                  placeholder={t.noUnit}
                  options={unitOptions}
                  {...form.text("unit")}
                />
              )}
              {!editing && <p className="text-sm text-ink-600">{t.saveFirst}</p>}
              <Button type="submit" loading={busy}>
                {editing ? strings.common.saveChanges : t.add}
              </Button>
            </form>
          </Card>
          <ListingWriter
            listingId={listingId}
            photoCount={existing.data?.photos.length ?? 0}
            onUse={applyDraft}
            facts={() => ({
              area: values.area,
              city: values.city,
              bedrooms: Number.isNaN(parseWhole(values.bedrooms)) ? null : parseWhole(values.bedrooms),
              bathrooms: Number.isNaN(parseWhole(values.bathrooms)) ? null : parseWhole(values.bathrooms),
              rent_amount: parseMoneyInput(values.rent_amount),
              rent_period: values.rent_period,
              features: values.features,
            })}
          />
        </div>
      )}
    </>
  );
}

/** City from the markets list (Lagos, Abuja…), with its neighbourhoods offered as suggestions for Area. */
function CityField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const markets = useMarkets();
  const cities = markets.data?.cities ?? [];
  const known = cities.some((c) => c.name === value);
  const areas = cities.find((c) => c.name === value)?.areas ?? [];
  return (
    <>
      {cities.length && (known || !value) ? (
        <Select
          label={t.city}
          value={value}
          options={cities.map((c) => ({ value: c.name, label: c.name }))}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <TextField label={t.city} maxLength={80} value={value} onChange={(e) => onChange(e.target.value)} />
      )}
      <datalist id="listing-areas">
        {areas.map((a) => (
          <option key={a} value={a} />
        ))}
      </datalist>
    </>
  );
}

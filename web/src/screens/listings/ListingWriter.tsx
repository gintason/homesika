import { useState, type ReactNode } from "react";

import { Banner, Button, Card, CopyButton, TextArea, TextField } from "../../components";
import { fmt, strings } from "../../i18n";
import { api, ApiError } from "../../lib/api";
import { useOrg } from "../../lib/org";
import type { ListingDraft, RentPeriod } from "../../lib/types";

const w = strings.writer;

export interface WriterFacts {
  area: string;
  city: string;
  bedrooms: number | null;
  bathrooms: number | null;
  /** API decimal string, or null when the form's rent isn't valid yet. */
  rent_amount: string | null;
  rent_period: RentPeriod;
  features: string[];
}

export type DraftField = "title" | "description" | "whatsapp_caption" | "features";

/**
 * "Write it for me": posts the facts to listings/generate/ and shows the draft with "Use this"
 * buttons. Nothing is saved or published from here; the agent applies what they want to the form.
 */
export function ListingWriter({
  facts,
  listingId,
  photoCount = 0,
  onUse,
}: {
  facts: () => WriterFacts;
  listingId?: string;
  photoCount?: number;
  onUse: (field: DraftField, value: string | string[]) => void;
}) {
  const { org } = useOrg();
  const [kind, setKind] = useState("");
  const [notes, setNotes] = useState("");
  const [kindError, setKindError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<ListingDraft | null>(null);

  const generate = async () => {
    const f = facts();
    const missingKind = !kind.trim();
    setKindError(missingKind ? strings.common.required : null);
    if (!f.area.trim() || !f.rent_amount) {
      setError(w.needFacts);
      return;
    }
    if (missingKind) return;
    setError(null);
    setBusy(true);
    const body: Record<string, unknown> = {
      kind: kind.trim(),
      area: f.area.trim(),
      city: f.city.trim() || undefined,
      bedrooms: f.bedrooms ?? undefined,
      bathrooms: f.bathrooms ?? undefined,
      rent_amount: f.rent_amount,
      rent_period: f.rent_period,
      features: f.features.length ? f.features : undefined,
      notes: notes.trim() || undefined,
      listing: listingId,
    };
    try {
      setDraft(await api<ListingDraft>(`/orgs/${org.id}/listings/generate/`, { method: "POST", body }));
    } catch (err) {
      if (err instanceof ApiError && err.code === "generator_unavailable") setError(err.message || w.unavailable);
      else if (err instanceof ApiError && err.status === 400) setError(Object.values(err.fieldErrors)[0] ?? err.summary);
      else setError(err instanceof ApiError ? err.summary : w.unavailable);
    } finally {
      setBusy(false);
    }
  };

  const applyButton = (field: DraftField, value: string | string[], label: string) => (
    <Button variant="secondary" onClick={() => onUse(field, value)} aria-label={`${w.use}: ${label}`}>
      {w.use}
    </Button>
  );

  return (
    <Card title={w.title} as="section" aria-label={w.title}>
      <div className="space-y-4">
        <p className="text-base text-ink-600">{w.intro}</p>
        <TextField
          label={w.kind}
          hint={w.kindHint}
          value={kind}
          maxLength={60}
          onChange={(e) => {
            setKind(e.target.value);
            setKindError(null);
          }}
          error={kindError}
        />
        <TextArea label={w.notes} hint={w.notesHint} optional value={notes} maxLength={1500} onChange={(e) => setNotes(e.target.value)} />
        <p className="text-sm text-ink-600">
          {w.usesForm} {listingId && photoCount > 0 ? fmt(w.withPhotos, { count: photoCount }) : ""}
        </p>
        {error && <Banner tone="error">{error}</Banner>}
        <Button onClick={() => void generate()} loading={busy} fullWidth>
          {draft ? w.regenerate : w.generate}
        </Button>
        {busy && (
          <p role="status" className="text-sm text-ink-600">
            {w.writing}
          </p>
        )}

        {draft && (
          <div className="space-y-4 border-t border-surface-line pt-4" aria-label={w.draftTitle} role="region">
            <h3 className="font-display text-lg font-semibold text-ink-900">{w.draftTitle}</h3>
            <Banner tone="warning">{w.draftWarning}</Banner>
            <Button
              variant="secondary"
              fullWidth
              onClick={() => {
                onUse("title", draft.title);
                onUse("description", draft.description);
                onUse("whatsapp_caption", draft.whatsapp_caption);
                onUse("features", draft.features);
              }}
            >
              {w.useAll}
            </Button>
            <DraftPart label={strings.listings.listingTitle} text={draft.title} action={applyButton("title", draft.title, strings.listings.listingTitle)} />
            <DraftPart
              label={strings.listings.description}
              text={draft.description}
              action={applyButton("description", draft.description, strings.listings.description)}
            />
            <DraftPart
              label={strings.listings.whatsappCaption}
              text={draft.whatsapp_caption}
              action={
                <>
                  {applyButton("whatsapp_caption", draft.whatsapp_caption, strings.listings.whatsappCaption)}
                  <CopyButton text={draft.whatsapp_caption} label={strings.common.copy} variant="ghost" ariaLabel={strings.listings.copyCaption} />
                </>
              }
            />
            {draft.features.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium text-ink-800">{strings.listings.features}</p>
                <ul className="flex flex-wrap gap-2">
                  {draft.features.map((f) => (
                    <li key={f} className="rounded-pill bg-surface-muted px-3 py-1 text-sm text-ink-800">
                      {f}
                    </li>
                  ))}
                </ul>
                {applyButton("features", draft.features, strings.listings.features)}
              </div>
            )}
            {draft.suggested_replies.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium text-ink-800">{w.suggestedReplies}</p>
                <p className="text-sm text-ink-600">{w.suggestedRepliesHint}</p>
                <ul className="space-y-3">
                  {draft.suggested_replies.map((r, i) => (
                    <li key={i} className="rounded-md bg-surface-muted p-3">
                      <p className="font-semibold text-ink-800">{r.question}</p>
                      <p className="mt-1 whitespace-pre-wrap text-ink-800">{r.answer}</p>
                      <CopyButton text={r.answer} label={w.copyReply} variant="ghost" ariaLabel={`${w.copyReply}: ${r.question}`} />
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

function DraftPart({ label, text, action }: { label: string; text: string; action: ReactNode }) {
  if (!text) return null;
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-ink-800">{label}</p>
      <p className="whitespace-pre-wrap rounded-md bg-surface-muted p-3 text-base text-ink-800">{text}</p>
      <div className="flex flex-wrap gap-2">{action}</div>
    </div>
  );
}

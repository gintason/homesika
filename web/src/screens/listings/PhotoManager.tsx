import { useState, type ChangeEvent } from "react";

import { Banner, Card, ConfirmDialog, buttonClasses, cx, useToast } from "../../components";
import { fmt, strings } from "../../i18n";
import { api } from "../../lib/api";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg } from "../../lib/queries";
import type { Listing, ListingPhoto } from "../../lib/types";
import { actionError } from "../shared";

const t = strings.listings;
const MAX_PHOTOS = 12;
const MAX_BYTES = 8 * 1024 * 1024;
const TYPES = ["image/jpeg", "image/png", "image/webp"];

/** Thumbnails, multipart upload (POST photos/ with field "image") and delete. */
export function PhotoManager({ listing }: { listing: Listing }) {
  const { org, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const canManage = can("listing.manage");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<{ photo: ListingPhoto; n: number } | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!files.length) return;
    setError(null);
    const room = MAX_PHOTOS - listing.photos.length;
    if (files.length > room) {
      setError(strings.listings.photosHint);
      return;
    }
    const bad = files.find((f) => f.size > MAX_BYTES || (f.type && !TYPES.includes(f.type)));
    if (bad) {
      setError(`${bad.name}: ${t.photosHint}`);
      return;
    }
    setUploading(true);
    try {
      for (const file of files) {
        const body = new FormData();
        body.append("image", file);
        await api<ListingPhoto>(`/orgs/${org.id}/listings/${listing.id}/photos/`, { method: "POST", body });
      }
      toast.show(t.photoAdded);
    } catch (err) {
      setError(actionError(err));
    } finally {
      await invalidate();
      setUploading(false);
    }
  };

  const remove = async () => {
    if (!deleting) return;
    setBusy(true);
    setDeleteError(null);
    try {
      await api(`/orgs/${org.id}/listings/${listing.id}/photos/${deleting.photo.id}/`, { method: "DELETE" });
      await invalidate();
      toast.show(strings.common.deleted);
      setDeleting(null);
    } catch (err) {
      setDeleteError(actionError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      title={t.photos}
      actions={
        canManage && listing.photos.length < MAX_PHOTOS ? (
          <label className={cx(buttonClasses("secondary"), "cursor-pointer focus-within:ring-2 focus-within:ring-primary-500", uploading && "opacity-60")}>
            <input
              type="file"
              accept={TYPES.join(",")}
              multiple
              className="sr-only"
              disabled={uploading}
              onChange={(e) => void upload(e)}
            />
            {uploading ? t.uploading : t.addPhoto}
          </label>
        ) : undefined
      }
    >
      <div className="space-y-4">
        {canManage && <p className="text-sm text-ink-600">{t.photosHint}</p>}
        {error && <Banner tone="error">{error}</Banner>}
        {uploading && (
          <p role="status" className="text-sm text-ink-600">
            {t.uploading}
          </p>
        )}
        {listing.photos.length === 0 ? (
          <p className="text-base text-ink-600">{t.noPhotos}</p>
        ) : (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
            {listing.photos.map((p, i) => (
              <li key={p.id} className="space-y-1">
                <img
                  src={p.url}
                  alt={p.caption || fmt(t.photoAlt, { n: i + 1, title: listing.title })}
                  loading="lazy"
                  decoding="async"
                  className="aspect-[4/3] w-full rounded-md bg-surface-muted object-cover"
                />
                {canManage && (
                  <button
                    type="button"
                    onClick={() => setDeleting({ photo: p, n: i + 1 })}
                    className="min-h-touch text-sm font-medium text-danger-700 underline underline-offset-4"
                    aria-label={fmt(t.deletePhoto, { n: i + 1 })}
                  >
                    {strings.common.delete}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      <ConfirmDialog
        open={deleting !== null}
        onClose={() => {
          setDeleting(null);
          setDeleteError(null);
        }}
        onConfirm={() => void remove()}
        title={t.deletePhotoTitle}
        confirmLabel={strings.common.delete}
        destructive
        loading={busy}
        error={deleteError}
      />
    </Card>
  );
}

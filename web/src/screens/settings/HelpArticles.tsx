import { useState, type FormEvent } from "react";

import {
  Badge,
  Banner,
  Button,
  Checkbox,
  ConfirmDialog,
  DataTable,
  Dialog,
  PageHeader,
  Select,
  StatusBadge,
  TextArea,
  TextField,
  optionsFrom,
  useToast,
} from "../../components";
import { strings } from "../../i18n";
import { api } from "../../lib/api";
import { formatDate } from "../../lib/dates";
import { useForm } from "../../lib/form";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { KbArticle, KbAudience } from "../../lib/types";
import { actionError } from "../shared";

const t = strings.kb;
const AUDIENCES = Object.keys(t.audiences) as KbAudience[];
export const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** The organization's own knowledge-base articles the assistant may quote (kb-articles/ CRUD). */
export function HelpArticles() {
  const { base, can } = useOrg();
  const canManage = can("kb.manage");
  const q = useOrgQuery<KbArticle[]>("/kb-articles/", undefined, { enabled: canManage });
  const [editing, setEditing] = useState<KbArticle | "new" | null>(null);
  const [deleting, setDeleting] = useState<KbArticle | null>(null);

  if (!canManage) {
    return (
      <>
        <PageHeader title={t.title} back={{ to: `${base}/settings`, label: strings.nav.settings }} />
        <Banner tone="info">{t.noAccess}</Banner>
      </>
    );
  }

  const add = <Button onClick={() => setEditing("new")}>{t.add}</Button>;
  return (
    <>
      <PageHeader title={t.title} description={t.intro} back={{ to: `${base}/settings`, label: strings.nav.settings }} actions={add} />
      <DataTable
        caption={t.title}
        rows={q.data}
        loading={q.isLoading}
        error={q.error}
        onRetry={() => void q.refetch()}
        rowKey={(a) => a.id}
        empty={{ title: t.empty, body: t.emptyHint, action: add }}
        columns={[
          { key: "title", header: t.articleTitle, cell: (a) => <span className="font-medium">{a.title}</span> },
          { key: "language", header: t.language, cell: (a) => t.languages[a.language] ?? a.language },
          {
            key: "audience",
            header: t.audience,
            cell: (a) =>
              a.audience.length ? (
                <span className="flex flex-wrap gap-1">
                  {a.audience.map((x) => (
                    <Badge key={x}>{t.audiences[x] ?? x}</Badge>
                  ))}
                </span>
              ) : (
                t.everyone
              ),
          },
          { key: "status", header: t.status, cell: (a) => <StatusBadge status={a.status} /> },
          { key: "updated", header: t.updated, cell: (a) => formatDate(a.updated_at) },
          {
            key: "actions",
            header: strings.common.actions,
            hideHeader: true,
            cell: (a) => (
              <span className="flex flex-wrap gap-1">
                <Button variant="ghost" onClick={() => setEditing(a)} aria-label={`${strings.common.edit}: ${a.title}`}>
                  {strings.common.edit}
                </Button>
                <Button variant="ghost" onClick={() => setDeleting(a)} aria-label={`${strings.common.delete}: ${a.title}`}>
                  {strings.common.delete}
                </Button>
              </span>
            ),
          },
        ]}
      />
      {editing && <ArticleDialog article={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      <DeleteArticle article={deleting} onClose={() => setDeleting(null)} />
    </>
  );
}

export function ArticleDialog({ article, onClose }: { article: KbArticle | null; onClose: () => void }) {
  const { org } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [busy, setBusy] = useState(false);
  const form = useForm({
    slug: article?.slug ?? "",
    title: article?.title ?? "",
    body: article?.body ?? "",
    language: article?.language ?? "en",
    audience: article?.audience ?? ([] as KbAudience[]),
    status: article?.status ?? "published",
  });
  const v = form.values;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const slug = v.slug.trim();
    if (
      !form.validate({
        slug: !slug ? strings.common.required : SLUG_RE.test(slug) ? undefined : t.slugInvalid,
        title: v.title.trim() ? undefined : strings.common.required,
        body: v.body.trim() ? undefined : strings.common.required,
      })
    )
      return;
    setBusy(true);
    try {
      await api<KbArticle>(`/orgs/${org.id}/kb-articles/${article ? `${article.id}/` : ""}`, {
        method: article ? "PATCH" : "POST",
        body: { slug, title: v.title.trim(), body: v.body.trim(), language: v.language, audience: v.audience, status: v.status },
      });
      await invalidate();
      toast.show(article ? strings.common.saved : t.created);
      onClose();
    } catch (err) {
      form.fromApiError(err);
      setBusy(false);
    }
  };

  const toggle = (a: KbAudience, on: boolean) =>
    form.set("audience", on ? AUDIENCES.filter((x) => x === a || v.audience.includes(x)) : v.audience.filter((x) => x !== a));

  return (
    <Dialog open onClose={busy ? () => undefined : onClose} title={article ? t.edit : t.add}>
      <form onSubmit={submit} noValidate className="space-y-4">
        {form.formError && <Banner tone="error">{form.formError}</Banner>}
        <TextField label={t.articleTitle} maxLength={160} {...form.text("title")} />
        <TextField label={t.slug} hint={t.slugHint} maxLength={80} autoCapitalize="none" {...form.text("slug")} />
        <TextArea label={t.body} rows={8} {...form.text("body")} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label={t.language} options={optionsFrom(t.languages)} {...form.text("language")} />
          <Select label={t.status} options={optionsFrom(t.statuses)} {...form.text("status")} />
        </div>
        <fieldset>
          <legend className="text-sm font-medium text-ink-800">{t.audience}</legend>
          <p className="text-sm text-ink-600">{t.audienceHint}</p>
          {AUDIENCES.map((a) => (
            <Checkbox key={a} label={t.audiences[a]} checked={v.audience.includes(a)} onChange={(e) => toggle(a, e.target.checked)} />
          ))}
          {form.errors.audience && <p className="text-sm font-medium text-danger-700">{form.errors.audience}</p>}
        </fieldset>
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {strings.common.cancel}
          </Button>
          <Button type="submit" loading={busy}>
            {article ? strings.common.saveChanges : t.add}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function DeleteArticle({ article, onClose }: { article: KbArticle | null; onClose: () => void }) {
  const { org } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const remove = async () => {
    if (!article) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/orgs/${org.id}/kb-articles/${article.id}/`, { method: "DELETE" });
      await invalidate();
      toast.show(strings.common.deleted);
      onClose();
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <ConfirmDialog
      open={article !== null}
      onClose={() => {
        setError(null);
        onClose();
      }}
      onConfirm={() => void remove()}
      title={t.deleteTitle}
      description={article && <><strong>{article.title}</strong><br />{t.deleteBody}</>}
      confirmLabel={strings.common.delete}
      destructive
      loading={busy}
      error={error}
    />
  );
}

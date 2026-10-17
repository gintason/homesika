import { router } from "expo-router";
import * as WebBrowser from "expo-web-browser";

import { useSession } from "@/store/session";

export type Segment = { text: string; url?: string };

const URL_RE = /https?:\/\/[^\s<>"']+/g;
// Punctuation that ends a sentence rather than the link ("...: https://x/pay/ABC.").
const TRAILING = /[.,;:!?)\]}]+$/;

/** Split chat text into plain text and http(s) links. Nothing else (tel:, javascript:) is linked. */
export function linkify(text: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  for (const m of text.matchAll(URL_RE)) {
    const start = m.index ?? 0;
    const raw = m[0];
    const url = raw.replace(TRAILING, "");
    if (!url) continue;
    if (start > last) out.push({ text: text.slice(last, start) });
    out.push({ text: url, url });
    last = start + url.length;
  }
  if (last < text.length) out.push({ text: text.slice(last) });
  return out;
}

/** Unique links in a message, in order. */
export function linksIn(text: string): string[] {
  return [...new Set(linkify(text).flatMap((s) => (s.url ? [s.url] : [])))];
}

/** "https://app.homesika.com/pay/HSK-123" -> "HSK-123" (payments.pay_url on the backend). */
export function payReference(url: string): string | null {
  const m = /^https?:\/\/[^/]+\/pay\/([A-Za-z0-9_-]+)\/?(?:[?#].*)?$/.exec(url);
  return m ? (m[1] ?? null) : null;
}

export function hostOf(url: string): string {
  const m = /^https?:\/\/([^/:?#]+)/.exec(url);
  return m ? (m[1] ?? url).replace(/^www\./, "") : url;
}

/**
 * Open a link from the chat in the in-app browser. Pay links behave like the pay flow: no app lock
 * while the payer is in checkout, then the result screen polls the payment status.
 */
export async function openChatLink(url: string) {
  const reference = payReference(url);
  if (reference) useSession.getState().suspendLockForCheckout();
  try {
    await WebBrowser.openBrowserAsync(url, { dismissButtonStyle: "close", showTitle: true, enableBarCollapsing: true });
  } catch {
    // No browser could open; for a pay link the result screen still lets them check the status.
  }
  if (reference) router.push({ pathname: "/pay/[reference]", params: { reference } });
}

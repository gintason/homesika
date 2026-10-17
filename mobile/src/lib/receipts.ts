import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";

import { billsApi, tenantApi } from "@/api";
import i18n from "@/i18n";

import { absoluteUrl, ApiError, freshAccessToken, refreshAccessToken } from "./api";

/**
 * GET /me/payments/{id}/receipt/ needs the Authorization header, so it can't be opened as a plain
 * link. Download it with the token into the cache, then hand it to the share sheet (which also
 * offers "Open in…" / "Save to Files").
 */
export function downloadReceipt(paymentId: string, receiptNumber: string): Promise<string> {
  return downloadPdf(tenantApi.receiptPath(paymentId), receiptNumber);
}

/** GET /bills/orders/{id}/receipt/ (only once the order is delivered). */
export function downloadBillReceipt(orderId: string, receiptNumber: string): Promise<string> {
  return downloadPdf(billsApi.receiptPath(orderId), receiptNumber);
}

async function downloadPdf(path: string, receiptNumber: string): Promise<string> {
  const safeName = receiptNumber.replace(/[^A-Za-z0-9_-]/g, "_");
  const destination = new File(Paths.cache, `homesika-receipt-${safeName}.pdf`);
  const url = absoluteUrl(path);

  const download = (access: string) =>
    File.downloadFileAsync(url, destination, {
      headers: { Authorization: `Bearer ${access}`, Accept: "application/pdf", "Accept-Language": i18n.language || "en" },
      idempotent: true, // overwrite an earlier copy
    });

  let access = await freshAccessToken();
  if (!access) throw new ApiError(401, "not_authenticated", i18n.t("payments.receiptFailed"));
  let file: File;
  try {
    file = await download(access);
  } catch {
    // Most likely the access token expired between the check and the request: refresh once.
    access = await refreshAccessToken();
    if (!access) throw new ApiError(401, "not_authenticated", i18n.t("payments.receiptFailed"));
    file = await download(access);
  }

  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(file.uri, {
      mimeType: "application/pdf",
      UTI: "com.adobe.pdf",
      dialogTitle: i18n.t("payments.receipt"),
    });
  }
  return file.uri;
}

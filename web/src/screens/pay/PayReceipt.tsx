import { Link, useParams } from "react-router";

import { buttonClasses } from "../../components";
import { strings } from "../../i18n";
import { API_URL } from "../../lib/config";
import { PayLayout, receiptPdfUrl } from "./PayLayout";

const t = strings.pay;

/** Linked from the "payment received" SMS. The PDF itself is served by the API. */
export function PayReceipt() {
  const { reference = "" } = useParams();
  return (
    <PayLayout title={t.receiptTitle}>
      <p className="text-base text-ink-700">{t.receiptBody}</p>
      <a href={receiptPdfUrl(API_URL, reference)} className={buttonClasses("primary", true)} target="_blank" rel="noopener">
        {t.openReceipt}
      </a>
      <Link to={`/pay/${encodeURIComponent(reference)}`} className={buttonClasses("ghost", true)}>
        {t.backToLink}
      </Link>
    </PayLayout>
  );
}

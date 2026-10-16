import { useParams } from "react-router";

import { buttonClasses } from "../../components";
import { strings } from "../../i18n";
import { API_URL } from "../../lib/config";
import { PayLayout } from "./PayLayout";

/** Linked from the SMS for a payment the landlord recorded (cash/transfer). The token is unguessable. */
export function ReceiptInfo() {
  const { token = "" } = useParams();
  return (
    <PayLayout title={strings.receipts.title}>
      <p className="text-base text-ink-700">{strings.receipts.body}</p>
      <a
        href={`${API_URL}/api/v1/receipts/${encodeURIComponent(token)}/`}
        className={buttonClasses("primary", true)}
        target="_blank"
        rel="noopener"
      >
        {strings.receipts.open}
      </a>
    </PayLayout>
  );
}

import { useSearchParams } from "react-router";

import { ButtonLink, Checkbox, PageHeader } from "../../components";
import { strings } from "../../i18n";
import { useOrg } from "../../lib/org";
import { PaymentsTable } from "../tables";

const t = strings.payments;

export function PaymentsList() {
  const { base, can } = useOrg();
  const [params, setParams] = useSearchParams();
  const needsReview = params.get("needs_review") === "1";
  return (
    <>
      <PageHeader title={t.title} actions={can("payment.record") && <ButtonLink to={`${base}/payments/new`}>{t.record}</ButtonLink>} />
      <div className="mb-4">
        <Checkbox
          label={t.needsReviewOnly}
          checked={needsReview}
          onChange={(e) => setParams(e.target.checked ? { needs_review: "1" } : {}, { replace: true })}
        />
      </div>
      <PaymentsTable query={{ needs_review: needsReview }} />
    </>
  );
}

import { useSearchParams } from "react-router";

import { Checkbox, PageHeader, Select } from "../../components";
import { strings } from "../../i18n";
import { ChargesTable } from "../tables";

const t = strings.charges;

/** Filters live in the URL (?status=outstanding&overdue=1) so a filtered view can be shared. */
export function ChargesList() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const overdue = params.get("overdue") === "1";
  const update = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };
  return (
    <>
      <PageHeader title={t.title} />
      <fieldset className="mb-4 flex flex-wrap items-end gap-4">
        <legend className="sr-only">{strings.common.filters}</legend>
        <Select
          containerClassName="w-full sm:w-[240px]"
          label={t.status}
          value={status}
          onChange={(e) => update("status", e.target.value)}
          placeholder={strings.common.all}
          options={[
            { value: "outstanding", label: t.outstanding },
            { value: "open", label: strings.status.open },
            { value: "part_paid", label: strings.status.part_paid },
            { value: "paid", label: strings.status.paid },
            { value: "waived", label: strings.status.waived },
            { value: "void", label: strings.status.void },
          ]}
        />
        <Checkbox label={t.overdueOnly} checked={overdue} onChange={(e) => update("overdue", e.target.checked ? "1" : null)} />
      </fieldset>
      <ChargesTable query={{ status, overdue }} />
    </>
  );
}

import { ButtonLink, EmptyState } from "../components";
import { strings } from "../i18n";

export function NotFound() {
  return (
    <div className="mx-auto max-w-xl px-5 py-16">
      <EmptyState
        title={strings.notFound.title}
        body={strings.notFound.body}
        action={<ButtonLink to="/">{strings.notFound.home}</ButtonLink>}
      />
    </div>
  );
}

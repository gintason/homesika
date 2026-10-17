import { useSearchParams } from "react-router";

import { ButtonLink, Logo, buttonClasses } from "../../components";
import { strings } from "../../i18n";

const t = strings.join;

/** Public landing for an invite link (/join?code=…): open the app with the code, or sign up on the web. */
export default function JoinPage() {
  const [params] = useSearchParams();
  const code = (params.get("code") ?? "").replace(/[^A-Za-z0-9]/g, "").toUpperCase().slice(0, 12);
  return (
    <main className="mx-auto max-w-md px-4 py-10">
      <Logo />
      <h1 className="mt-6 font-display text-3xl font-bold text-ink-900">{t.title}</h1>
      <p className="mt-3 text-base text-ink-700">{t.body}</p>
      {code ? (
        <>
          <div className="mt-6 rounded-lg bg-surface-card p-5 ring-1 ring-surface-line">
            <p className="text-sm text-ink-600">{t.code}</p>
            <p className="mt-1 font-mono text-3xl font-bold tracking-widest text-ink-900">{code}</p>
            <p className="mt-3 text-ink-800">{t.reward}</p>
          </div>
          <div className="mt-6 flex flex-col gap-3">
            <a className={buttonClasses("primary")} href={`homesika://register?code=${code}`}>
              {t.openApp}
            </a>
            <ButtonLink to={`/signup?code=${code}`} variant="secondary">
              {t.signUpWeb}
            </ButtonLink>
          </div>
          <p className="mt-4 text-sm text-ink-600">{t.rules}</p>
        </>
      ) : (
        <p className="mt-6 text-ink-700">{t.noCode}</p>
      )}
    </main>
  );
}

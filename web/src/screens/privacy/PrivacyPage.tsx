import { PayLayout } from "../pay/PayLayout";
import { NOTICE_VERSION, SECTIONS } from "./notice";

/** Public privacy notice (/privacy), linked from sign-up in the app (EXPO_PUBLIC_PRIVACY_URL). */
export function PrivacyPage() {
  return (
    <PayLayout title="Privacy notice" wide footer={`Version ${NOTICE_VERSION}`}>
      {SECTIONS.map((s) => (
        <section key={s.title} className="space-y-2">
          <h2 className="font-display text-xl font-semibold text-ink-900">{s.title}</h2>
          {s.body.map((p) => (
            <p key={p} className="text-base text-ink-800">
              {p}
            </p>
          ))}
        </section>
      ))}
    </PayLayout>
  );
}

export default PrivacyPage;

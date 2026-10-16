import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { Banner, Button, PhoneInput, useToast } from "../../components";
import { strings } from "../../i18n";
import { api, ApiError, errorText } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { lastPhone } from "../../lib/device";
import { formatPhone, isValidNigerianPhone, normalisePhone } from "../../lib/phone";
import type { OtpChallenge } from "../../lib/types";
import { AuthLayout } from "./AuthLayout";
import { CreatePinStep, OtpStep } from "./steps";

const t = strings.auth;

type Step = { kind: "phone" } | { kind: "otp"; challenge: OtpChallenge } | { kind: "pin"; setupToken: string };

/** pin/forgot -> otp/verify -> pin/setup. The API signs the user out everywhere else. */
export function ForgotPin() {
  const { completeSignIn } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>({ kind: "phone" });
  const [phone, setPhone] = useState(() => (lastPhone.get() ? formatPhone(lastPhone.get()) : ""));
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (!isValidNigerianPhone(phone)) {
      setError(strings.fields.phoneInvalid);
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const challenge = await api<OtpChallenge>("/auth/pin/forgot/", {
        method: "POST",
        auth: false,
        body: { identifier: normalisePhone(phone) },
      });
      setStep({ kind: "otp", challenge });
    } catch (err) {
      if (err instanceof ApiError && err.fieldErrors.identifier) setError(err.fieldErrors.identifier);
      else setFormError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  if (step.kind === "otp") {
    return (
      <AuthLayout title={t.forgotTitle}>
        <OtpStep
          challenge={step.challenge}
          onVerified={(resp) => {
            if ("setup_token" in resp) setStep({ kind: "pin", setupToken: resp.setup_token });
          }}
          onBack={() => setStep({ kind: "phone" })}
        />
      </AuthLayout>
    );
  }
  if (step.kind === "pin") {
    return (
      <AuthLayout title={t.createPinTitle} intro={t.createPinIntro}>
        <CreatePinStep
          setupToken={step.setupToken}
          onDone={(resp) => {
            completeSignIn(resp);
            toast.show(t.forgotDone);
            navigate("/", { replace: true });
          }}
        />
      </AuthLayout>
    );
  }
  return (
    <AuthLayout title={t.forgotTitle} intro={t.forgotIntro}>
      <form onSubmit={submit} noValidate className="space-y-4">
        {formError && <Banner tone="error">{formError}</Banner>}
        <PhoneInput value={phone} onChange={setPhone} error={error} required />
        <Button type="submit" fullWidth loading={busy}>
          {t.sendCode}
        </Button>
      </form>
      <p className="mt-6 border-t border-surface-line pt-4 text-base">
        <Link to="/signin" className="font-medium text-primary-600 underline underline-offset-4">
          {t.signIn}
        </Link>
      </p>
    </AuthLayout>
  );
}

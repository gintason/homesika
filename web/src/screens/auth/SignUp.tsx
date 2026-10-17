import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { Banner, Button, Checkbox, PhoneInput, TextField } from "../../components";
import { strings } from "../../i18n";
import { api } from "../../lib/api";
import { storeCredentials, useAuth } from "../../lib/auth";
import { useForm } from "../../lib/form";
import { isValidNigerianPhone, normalisePhone } from "../../lib/phone";
import type { OtpChallenge, SignedIn } from "../../lib/types";
import { AuthLayout } from "./AuthLayout";
import { CreatePinStep, OtpStep, TransactionPinStep } from "./steps";

const t = strings.auth;

type Step =
  | { kind: "details" }
  | { kind: "otp"; challenge: OtpChallenge }
  | { kind: "pin"; setupToken: string }
  | { kind: "txpin"; resp: SignedIn; loginPin: string };

/** register -> otp/verify -> pin/setup (signed in) -> optional transaction PIN -> create organization. */
export function SignUp() {
  const { completeSignIn } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>({ kind: "details" });
  const [busy, setBusy] = useState(false);
  const [params] = useSearchParams();
  const form = useForm({
    first_name: "",
    last_name: "",
    phone_number: "",
    email: "",
    // From an invite link (/join?code=…): the new account gets free bill service fees.
    referral_code: (params.get("code") ?? "").toUpperCase(),
    accept_terms: false,
  });
  const v = form.values;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = form.validate({
      first_name: v.first_name.trim() ? undefined : strings.common.required,
      last_name: v.last_name.trim() ? undefined : strings.common.required,
      phone_number: isValidNigerianPhone(v.phone_number) ? undefined : strings.fields.phoneInvalid,
      email: !v.email || /^\S+@\S+\.\S+$/.test(v.email) ? undefined : strings.fields.emailInvalid,
      accept_terms: v.accept_terms ? undefined : t.acceptTermsRequired,
    });
    if (!ok) return;
    setBusy(true);
    try {
      const challenge = await api<OtpChallenge>("/auth/register/", {
        method: "POST",
        auth: false,
        body: {
          first_name: v.first_name.trim(),
          last_name: v.last_name.trim(),
          phone_number: normalisePhone(v.phone_number),
          email: v.email.trim(),
          accept_terms: true,
          channel: "sms",
          ...(v.referral_code.trim() ? { referral_code: v.referral_code.trim() } : {}),
        },
      });
      setStep({ kind: "otp", challenge });
    } catch (err) {
      form.fromApiError(err);
    } finally {
      setBusy(false);
    }
  };

  if (step.kind === "otp") {
    return (
      <AuthLayout title={t.newDeviceTitle}>
        <OtpStep
          challenge={step.challenge}
          onVerified={(resp) => {
            if ("setup_token" in resp) setStep({ kind: "pin", setupToken: resp.setup_token });
          }}
          onBack={() => setStep({ kind: "details" })}
        />
      </AuthLayout>
    );
  }
  if (step.kind === "pin") {
    return (
      <AuthLayout title={t.createPinTitle} intro={t.createPinIntro}>
        <CreatePinStep
          setupToken={step.setupToken}
          onDone={(resp, pin) => {
            // Tokens are stored now (so the transaction PIN call is authenticated), but we stay on this
            // page until that optional step is done.
            storeCredentials(resp);
            setStep({ kind: "txpin", resp, loginPin: pin });
          }}
        />
      </AuthLayout>
    );
  }
  if (step.kind === "txpin") {
    return (
      <AuthLayout title={t.txPinTitle} intro={t.txPinIntro}>
        <TransactionPinStep
          loginPin={step.loginPin}
          onDone={() => {
            completeSignIn(step.resp);
            navigate("/orgs/new", { replace: true });
          }}
        />
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title={t.signUpTitle} intro={t.signUpIntro}>
      <form onSubmit={submit} noValidate className="space-y-4">
        {form.formError && <Banner tone="error">{form.formError}</Banner>}
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label={strings.fields.firstName} autoComplete="given-name" required {...form.text("first_name")} />
          <TextField label={strings.fields.lastName} autoComplete="family-name" required {...form.text("last_name")} />
        </div>
        <PhoneInput
          value={v.phone_number}
          onChange={(x) => form.set("phone_number", x)}
          error={form.errors.phone_number}
          required
        />
        <TextField label={strings.fields.email} type="email" autoComplete="email" optional {...form.text("email")} />
        <TextField label={t.referralCode} hint={t.referralHint} autoComplete="off" optional {...form.text("referral_code")} />
        <Checkbox
          label={t.acceptTerms}
          checked={v.accept_terms}
          onChange={(e) => form.set("accept_terms", e.target.checked)}
          error={form.errors.accept_terms}
        />
        <Button type="submit" fullWidth loading={busy}>
          {strings.common.continue}
        </Button>
      </form>
      <p className="mt-6 border-t border-surface-line pt-4 text-base text-ink-700">
        {t.haveAccount}{" "}
        <Link to="/signin" className="font-medium text-primary-600 underline underline-offset-4">
          {t.signIn}
        </Link>
      </p>
    </AuthLayout>
  );
}


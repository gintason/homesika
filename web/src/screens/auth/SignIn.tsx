import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { Banner, Button, PhoneInput, PinInput } from "../../components";
import { fmt, strings } from "../../i18n";
import { api, ApiError, errorText } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { deviceSecret, getDeviceId, lastPhone } from "../../lib/device";
import { formatPhone, isValidNigerianPhone, normalisePhone } from "../../lib/phone";
import type { OtpChallenge, SetupNeeded, SignedIn } from "../../lib/types";
import { AuthLayout } from "./AuthLayout";
import { OtpStep } from "./steps";

const t = strings.auth;

type Step = { kind: "pin" } | { kind: "phone" } | { kind: "otp"; challenge: OtpChallenge };

/**
 * Trusted browser (holds a device secret): PIN only, via /auth/pin-login/.
 * New browser: phone + PIN via /auth/login/, then the one-time code via /auth/otp/verify/.
 */
export function SignIn() {
  const { completeSignIn, isTrustedDevice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [step, setStep] = useState<Step>(() => (isTrustedDevice() ? { kind: "pin" } : { kind: "phone" }));
  const [phone, setPhone] = useState(() => (lastPhone.get() ? formatPhone(lastPhone.get()) : ""));
  const [pin, setPin] = useState("");
  const [errors, setErrors] = useState<{ phone?: string; pin?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const done = (resp: SignedIn) => {
    completeSignIn(resp);
    navigate(from, { replace: true });
  };

  const handleError = (err: unknown) => {
    if (err instanceof ApiError) {
      if (err.code === "device_not_recognised") {
        deviceSecret.clear();
        setStep({ kind: "phone" });
        setNotice(t.deviceForgotten);
        setPin("");
        return;
      }
      if (err.code === "invalid_login_pin") {
        setErrors({ pin: err.message });
        return;
      }
      if (err.code === "login_pin_locked") {
        setFormError(t.pinLocked);
        return;
      }
      setErrors({
        phone: err.fieldErrors.identifier,
        pin: err.fieldErrors.pin,
      });
      if (!err.fieldErrors.identifier && !err.fieldErrors.pin) setFormError(err.summary);
      return;
    }
    setFormError(errorText(err));
  };

  const submitPin = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (!/^\d{6}$/.test(pin)) {
      setErrors({ pin: t.pinFormat });
      return;
    }
    setErrors({});
    setBusy(true);
    try {
      const resp = await api<SignedIn>("/auth/pin-login/", {
        method: "POST",
        auth: false,
        body: { device_id: getDeviceId(), device_secret: deviceSecret.get(), pin },
      });
      done(resp);
    } catch (err) {
      handleError(err);
      setBusy(false);
    }
  };

  const submitPhone = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    const found: { phone?: string; pin?: string } = {};
    if (!isValidNigerianPhone(phone)) found.phone = strings.fields.phoneInvalid;
    if (!/^\d{6}$/.test(pin)) found.pin = t.pinFormat;
    setErrors(found);
    if (found.phone || found.pin) return;
    setBusy(true);
    try {
      const challenge = await api<OtpChallenge>("/auth/login/", {
        method: "POST",
        auth: false,
        body: { identifier: normalisePhone(phone), pin },
      });
      setStep({ kind: "otp", challenge });
    } catch (err) {
      handleError(err);
    } finally {
      setBusy(false);
    }
  };

  const footer = (
    <div className="mt-6 space-y-2 border-t border-surface-line pt-4 text-base">
      <p>
        <Link to="/forgot-pin" className="font-medium text-primary-600 underline underline-offset-4">
          {t.forgotPin}
        </Link>
      </p>
      <p className="text-ink-700">
        {t.noAccount}{" "}
        <Link to="/signup" className="font-medium text-primary-600 underline underline-offset-4">
          {t.signUp}
        </Link>
      </p>
    </div>
  );

  if (step.kind === "otp") {
    return (
      <AuthLayout title={t.newDeviceTitle}>
        <OtpStep
          challenge={step.challenge}
          onVerified={(resp: SignedIn | SetupNeeded) => {
            if ("tokens" in resp) done(resp);
          }}
          onBack={() => setStep({ kind: "phone" })}
        />
      </AuthLayout>
    );
  }

  if (step.kind === "pin") {
    return (
      <AuthLayout title={t.welcomeBack} intro={fmt(t.signInAs, { phone: formatPhone(lastPhone.get()) })}>
        <form onSubmit={submitPin} noValidate className="space-y-4">
          {formError && <Banner tone="error">{formError}</Banner>}
          <PinInput label={t.pin} value={pin} onChange={setPin} error={errors.pin} autoFocus />
          <Button type="submit" fullWidth loading={busy}>
            {t.signIn}
          </Button>
          <Button
            variant="ghost"
            fullWidth
            onClick={() => {
              setStep({ kind: "phone" });
              setPhone("");
              setPin("");
              setErrors({});
            }}
          >
            {t.notYou}
          </Button>
        </form>
        {footer}
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title={t.signInTitle}>
      <form onSubmit={submitPhone} noValidate className="space-y-4">
        {notice && <Banner tone="info">{notice}</Banner>}
        {formError && <Banner tone="error">{formError}</Banner>}
        <PhoneInput value={phone} onChange={setPhone} error={errors.phone} required />
        <PinInput label={t.pin} hint={t.pinHint} value={pin} onChange={setPin} error={errors.pin} />
        <Button type="submit" fullWidth loading={busy}>
          {t.signIn}
        </Button>
      </form>
      {footer}
    </AuthLayout>
  );
}

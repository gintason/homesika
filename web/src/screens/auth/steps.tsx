import { useEffect, useState, type FormEvent } from "react";

import { Banner, Button, OtpInput, PinInput } from "../../components";
import { fmt, strings } from "../../i18n";
import { api, ApiError, errorText } from "../../lib/api";
import { getDeviceId, getDeviceName } from "../../lib/device";
import { isWeakPin } from "../../lib/pin";
import type { OtpChallenge, SetupNeeded, SignedIn } from "../../lib/types";

const t = strings.auth;

/** Seconds left before "resend" is allowed; restarts whenever a new challenge object arrives. */
function useCountdown(challenge: OtpChallenge) {
  const [current, setCurrent] = useState(challenge);
  const [left, setLeft] = useState(challenge.resend_in);
  if (current !== challenge) {
    setCurrent(challenge);
    setLeft(challenge.resend_in);
  }
  useEffect(() => {
    if (left <= 0) return;
    const id = window.setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => window.clearTimeout(id);
  }, [left]);
  return left;
}

/** Enter the 6-digit code. Resolves to tokens (new device) or a setup token (sign-up, forgot PIN). */
export function OtpStep({
  challenge: initial,
  onVerified,
  onBack,
}: {
  challenge: OtpChallenge;
  onVerified: (resp: SignedIn | SetupNeeded) => void;
  onBack: () => void;
}) {
  const [challenge, setChallenge] = useState(initial);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resending, setResending] = useState(false);
  const resendLeft = useCountdown(challenge);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!/^\d{6}$/.test(code)) {
      setError(t.otpInvalid);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resp = await api<SignedIn | SetupNeeded>("/auth/otp/verify/", {
        method: "POST",
        auth: false,
        body: { challenge_id: challenge.challenge_id, code, device_id: getDeviceId(), device_name: getDeviceName() },
      });
      onVerified(resp);
    } catch (err) {
      setError(err instanceof ApiError ? (err.fieldErrors.code ?? err.summary) : errorText(err));
      setBusy(false);
    }
  };

  const resend = async (channel?: "email") => {
    setResending(true);
    setError(null);
    setInfo(null);
    try {
      const next = await api<OtpChallenge>("/auth/otp/resend/", {
        method: "POST",
        auth: false,
        body: { challenge_id: challenge.challenge_id, ...(channel ? { channel } : {}) },
      });
      setChallenge(next);
      setInfo(t.codeResent);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setResending(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <p className="text-base text-ink-700">
        {fmt(t.otpSent, { destination: challenge.destination, minutes: Math.max(1, Math.round(challenge.expires_in / 60)) })}
      </p>
      {error && <Banner tone="error">{error}</Banner>}
      {info && <Banner tone="success">{info}</Banner>}
      <OtpInput value={code} onChange={setCode} autoFocus error={null} />
      <Button type="submit" fullWidth loading={busy}>
        {t.verify}
      </Button>
      <div className="flex flex-col items-start gap-1">
        {resendLeft > 0 ? (
          <p className="text-sm text-ink-600" aria-live="polite">
            {fmt(t.resendIn, { seconds: resendLeft })}
          </p>
        ) : (
          <Button variant="ghost" onClick={() => void resend()} loading={resending}>
            {t.resend}
          </Button>
        )}
        {challenge.email_fallback && resendLeft <= 0 && (
          <Button variant="ghost" onClick={() => void resend("email")} disabled={resending}>
            {t.sendByEmail}
          </Button>
        )}
        <Button variant="ghost" onClick={onBack}>
          {strings.common.back}
        </Button>
      </div>
    </form>
  );
}

export function validateNewPin(pin: string, confirm: string, length: 4 | 6): { pin?: string; confirm?: string } {
  const out: { pin?: string; confirm?: string } = {};
  if (!new RegExp(`^\\d{${length}}$`).test(pin)) out.pin = length === 6 ? t.pinFormat : t.txPinFormat;
  else if (isWeakPin(pin)) out.pin = t.pinWeak;
  if (!out.pin && pin !== confirm) out.confirm = t.pinMismatch;
  return out;
}

/** Choose the 6-digit login PIN with the setup token from otp/verify. Signs the user in. */
export function CreatePinStep({
  setupToken,
  onDone,
}: {
  setupToken: string;
  onDone: (resp: SignedIn, pin: string) => void;
}) {
  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<{ pin?: string; confirm?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const found = validateNewPin(pin, confirm, 6);
    setErrors(found);
    setFormError(null);
    if (found.pin || found.confirm) return;
    setBusy(true);
    try {
      const resp = await api<SignedIn>("/auth/pin/setup/", {
        method: "POST",
        auth: false,
        body: {
          setup_token: setupToken,
          pin,
          pin_confirm: confirm,
          device_id: getDeviceId(),
          device_name: getDeviceName(),
        },
      });
      onDone(resp, pin);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors({ pin: err.fieldErrors.pin, confirm: err.fieldErrors.pin_confirm });
        setFormError(err.fieldErrors.pin || err.fieldErrors.pin_confirm ? null : err.summary);
      } else setFormError(errorText(err));
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      {formError && <Banner tone="error">{formError}</Banner>}
      <PinInput label={t.newPin} value={pin} onChange={setPin} mode="new" error={errors.pin} autoFocus />
      <PinInput label={t.confirmPin} value={confirm} onChange={setConfirm} mode="new" error={errors.confirm} />
      <Button type="submit" fullWidth loading={busy}>
        {strings.common.continue}
      </Button>
    </form>
  );
}

/** Optional 4-digit transaction PIN (needs the login PIN as step-up). */
export function TransactionPinStep({ loginPin, onDone }: { loginPin: string; onDone: () => void }) {
  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<{ pin?: string; confirm?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const found = validateNewPin(pin, confirm, 4);
    setErrors(found);
    setFormError(null);
    if (found.pin || found.confirm) return;
    setBusy(true);
    try {
      await api("/me/transaction-pin/", {
        method: "POST",
        body: { login_pin: loginPin, pin, pin_confirm: confirm },
      });
      onDone();
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors({ pin: err.fieldErrors.pin, confirm: err.fieldErrors.pin_confirm });
        setFormError(err.fieldErrors.pin || err.fieldErrors.pin_confirm ? null : err.summary);
      } else setFormError(errorText(err));
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      {formError && <Banner tone="error">{formError}</Banner>}
      <PinInput label={t.txPin} value={pin} onChange={setPin} length={4} mode="new" error={errors.pin} autoFocus />
      <PinInput label={t.txPinConfirm} value={confirm} onChange={setConfirm} length={4} mode="new" error={errors.confirm} />
      <Button type="submit" fullWidth loading={busy}>
        {strings.common.save}
      </Button>
      <Button variant="ghost" fullWidth onClick={onDone}>
        {t.skipForNow}
      </Button>
    </form>
  );
}

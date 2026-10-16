import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { router } from "expo-router";
import * as SecureStore from "expo-secure-store";

import Login from "@/app/(auth)/login";
import Verify from "@/app/(auth)/verify";
import LockScreen from "@/app/lock";
import { getSecure, setSecure, tokens } from "@/lib/secure";
import { useAuthFlow } from "@/store/authFlow";
import { useSession } from "@/store/session";
import { json, mockFetch, user } from "@/testing/utils";

const challenge = {
  challenge_id: "ch-1",
  purpose: "new_device",
  channel: "sms",
  destination: "+234•••••678",
  email_fallback: false,
  expires_in: 600,
  resend_in: 60,
};

const typePin = (pin: string) => {
  for (const d of pin) fireEvent.press(screen.getByLabelText(d));
};

beforeEach(async () => {
  jest.clearAllMocks();
  (SecureStore as unknown as { __reset: () => void }).__reset(); // in-memory mock (jest.setup.js)
  useAuthFlow.getState().reset();
  useSession.setState({ status: "signedOut", profile: null, biometricEnabled: false });
});

describe("sign in on a new phone: phone + PIN, then a code", () => {
  it("sends the normalised phone and PIN, then verifies the code and signs in", async () => {
    const calls = mockFetch((c) => {
      if (c.url.endsWith("/api/v1/auth/login/")) return json(201, challenge);
      if (c.url.endsWith("/api/v1/auth/otp/verify/"))
        return json(200, { next: "done", user, tokens: { access: "acc", refresh: "ref" }, device_secret: "secret-1" });
      return undefined;
    });

    render(<Login />);
    fireEvent.changeText(screen.getByLabelText("Phone number"), "0801 234 5678");
    fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("+234 801 234 5678")).toBeTruthy();
    typePin("739152");

    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/verify"));
    expect(calls[0]).toMatchObject({
      method: "POST",
      body: { identifier: "+2348012345678", pin: "739152" },
    });
    expect(calls[0]!.headers.Authorization).toBeUndefined();
    expect(useAuthFlow.getState().challenge?.challenge_id).toBe("ch-1");

    screen.unmount();
    render(<Verify />);
    expect(screen.getByText(/We sent a 6-digit code by SMS to/)).toBeTruthy();
    fireEvent.changeText(screen.getByTestId("otp-input"), "123456");

    await waitFor(() => expect(useSession.getState().status).toBe("ready"));
    const verify = calls.find((c) => c.url.endsWith("/otp/verify/"))!;
    expect(verify.body).toMatchObject({ challenge_id: "ch-1", code: "123456", device_id: expect.stringMatching(/^dev_[0-9a-f]{32}$/) });
    expect(await tokens.get()).toEqual({ access: "acc", refresh: "ref" });
    expect(await getSecure("deviceSecret")).toBe("secret-1");
    expect(useSession.getState().profile).toEqual({ firstName: "Ada", lastName: "Obi", phone: "+2348012345678" });
  });

  it("shows a wrong PIN with attempts left and lets the user try again", async () => {
    mockFetch(() => json(403, { error: { code: "invalid_login_pin", message: "Incorrect PIN.", details: { attempts_left: 4 } } }));
    render(<Login />);
    fireEvent.changeText(screen.getByLabelText("Phone number"), "08012345678");
    fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    typePin("739152");
    expect(await screen.findByText("Incorrect PIN. Attempts left: 4.")).toBeTruthy();
    expect(router.push).not.toHaveBeenCalled();
    expect(screen.getByLabelText("0 of 6 digits entered")).toBeTruthy(); // pad cleared for another go
  });

  it("rejects an invalid phone number before calling the API", () => {
    const calls = mockFetch(() => undefined);
    render(<Login />);
    fireEvent.changeText(screen.getByLabelText("Phone number"), "0801");
    fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("Enter a valid Nigerian phone number.")).toBeTruthy();
    expect(calls).toHaveLength(0);
  });
});

describe("lock screen (trusted phone: PIN only)", () => {
  it("unlocks with the PIN and this phone's device secret", async () => {
    await setSecure("deviceSecret", "secret-1");
    await setSecure("deviceId", "dev_0123456789abcdef0123456789abcdef");
    useSession.setState({ status: "locked", profile: { firstName: "Ada", lastName: "Obi", phone: "+2348012345678" } });
    const calls = mockFetch((c) =>
      c.url.endsWith("/api/v1/auth/pin-login/") ? json(200, { user, tokens: { access: "a2", refresh: "r2" } }) : undefined,
    );

    render(<LockScreen />);
    expect(screen.getByText("Welcome back, Ada")).toBeTruthy();
    typePin("739152");

    await waitFor(() => expect(useSession.getState().status).toBe("ready"));
    expect(calls[0]!.body).toEqual({ device_id: "dev_0123456789abcdef0123456789abcdef", device_secret: "secret-1", pin: "739152" });
  });

  it("a phone signed out elsewhere goes back to sign-in", async () => {
    await setSecure("deviceSecret", "old");
    useSession.setState({ status: "locked" });
    mockFetch(() => json(401, { error: { code: "device_not_recognised", message: "Please sign in again on this device." } }));
    render(<LockScreen />);
    typePin("739152");
    await waitFor(() => expect(useSession.getState().status).toBe("signedOut"));
    expect(await getSecure("deviceSecret")).toBeNull();
  });
});

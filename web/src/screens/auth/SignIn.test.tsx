import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";

import { ToastProvider } from "../../components";
import { AuthProvider } from "../../lib/auth";
import { deviceSecret, getDeviceId, lastPhone } from "../../lib/device";
import { session } from "../../lib/session";
import { envelope, mockFetch } from "../../test/fetch";
import { LocationProbe, testQueryClient } from "../../test/render";
import { SignIn } from "./SignIn";

const USER = {
  id: "u1",
  phone_number: "+2348031234567",
  email: null,
  first_name: "Ada",
  last_name: "Obi",
  country: "NG",
  preferred_language: "en",
  is_phone_verified: true,
  is_email_verified: false,
  has_login_pin: true,
  has_transaction_pin: false,
  created_at: "2026-10-01T00:00:00Z",
};

function renderSignIn() {
  return render(
    <QueryClientProvider client={testQueryClient()}>
      <AuthProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={["/signin"]}>
            <Routes>
              <Route path="/signin" element={<SignIn />} />
              <Route path="*" element={<LocationProbe />} />
            </Routes>
          </MemoryRouter>
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("Sign in", () => {
  it("new device: phone + PIN, then the code, then signed in with the device bound", async () => {
    const m = mockFetch({
      "POST /api/v1/auth/login/": {
        status: 201,
        body: { challenge_id: "ch1", purpose: "new_device", channel: "sms", destination: "+234•••••567", email_fallback: false, expires_in: 600, resend_in: 60 },
      },
      "POST /api/v1/auth/otp/verify/": {
        body: { next: "done", user: USER, tokens: { access: "acc", refresh: "ref" }, device_secret: "sec-1" },
      },
    });
    renderSignIn();

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText(/valid Nigerian phone number/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Phone number/), { target: { value: "0803 123 4567" } });
    fireEvent.change(screen.getByLabelText("6-digit PIN"), { target: { value: "402913" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const code = await screen.findByLabelText("6-digit code");
    expect(m.find("POST", "/api/v1/auth/login/")[0]!.body).toEqual({ identifier: "+2348031234567", pin: "402913" });
    expect(code).toHaveAttribute("autocomplete", "one-time-code");
    fireEvent.change(code, { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/"));
    expect(m.find("POST", "/api/v1/auth/otp/verify/")[0]!.body).toMatchObject({ challenge_id: "ch1", code: "123456", device_id: getDeviceId() });
    expect(session.getAccess()).toBe("acc");
    expect(session.getRefresh()).toBe("ref");
    expect(deviceSecret.get()).toBe("sec-1");
  });

  it("trusted device: PIN only via pin-login", async () => {
    deviceSecret.set("sec-1");
    lastPhone.set("+2348031234567");
    const m = mockFetch({
      "POST /api/v1/auth/pin-login/": { body: { user: USER, tokens: { access: "acc2", refresh: "ref2" } } },
    });
    renderSignIn();
    expect(screen.getByText("Signing in as 0803 123 4567")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("6-digit PIN"), { target: { value: "402913" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(session.getAccess()).toBe("acc2"));
    expect(m.calls[0]!.body).toEqual({ device_id: getDeviceId(), device_secret: "sec-1", pin: "402913" });
  });

  it("falls back to phone + PIN when the device is no longer recognised", async () => {
    deviceSecret.set("stale");
    lastPhone.set("+2348031234567");
    mockFetch({
      "POST /api/v1/auth/pin-login/": envelope(401, "device_not_recognised", "Please sign in again on this device."),
    });
    renderSignIn();
    fireEvent.change(screen.getByLabelText("6-digit PIN"), { target: { value: "402913" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText(/isn't recognised any more/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Phone number/)).toBeInTheDocument();
    expect(deviceSecret.get()).toBeNull();
  });

  it("shows an incorrect PIN next to the field", async () => {
    deviceSecret.set("sec");
    lastPhone.set("+2348031234567");
    mockFetch({ "POST /api/v1/auth/pin-login/": envelope(403, "invalid_login_pin", "Incorrect PIN.") });
    renderSignIn();
    fireEvent.change(screen.getByLabelText("6-digit PIN"), { target: { value: "402913" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Incorrect PIN.")).toBeInTheDocument();
    expect(screen.getByLabelText("6-digit PIN")).toHaveAttribute("aria-invalid", "true");
  });
});

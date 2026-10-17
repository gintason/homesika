import { act, fireEvent, screen } from "@testing-library/react-native";

import Profile from "@/app/(app)/(tabs)/profile";
import { tokens } from "@/lib/secure";
import { useSession } from "@/store/session";
import { json, mockFetch, renderWithClient, user } from "@/testing/utils";

beforeEach(async () => {
  await tokens.set("access-1", "refresh-1");
  useSession.setState({ status: "ready", profile: { firstName: "Ada", lastName: "Obi", phone: "+2348012345678" } });
});

afterEach(async () => {
  await act(() => useSession.getState().setLanguage("en"));
});

describe("Profile: WhatsApp", () => {
  it("turns WhatsApp reminders on with PUT /me/whatsapp/", async () => {
    let optedIn = false;
    const calls = mockFetch((c) => {
      if (c.url.endsWith("/api/v1/me/")) return json(200, user);
      if (c.url.endsWith("/api/v1/me/whatsapp/")) {
        if (c.method === "PUT") optedIn = (c.body as { opted_in: boolean }).opted_in;
        return json(200, { opted_in: optedIn });
      }
      return undefined;
    });
    renderWithClient(<Profile />);
    const toggle = await screen.findByRole("checkbox", { name: "Send reminders and receipts on WhatsApp" });
    expect(toggle.props.accessibilityState.checked).toBe(false);
    expect(screen.getByText(/instead of SMS/)).toBeTruthy();
    expect(screen.getByText(/Reply STOP on WhatsApp/)).toBeTruthy();

    fireEvent.press(toggle);
    await screen.findByRole("checkbox", { name: "Send reminders and receipts on WhatsApp", checked: true });
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.url).toBe("http://localhost:8001/api/v1/me/whatsapp/");
    expect(put.body).toEqual({ opted_in: true });
  });

  it("shows the WhatsApp copy in Pidgin", async () => {
    await act(() => useSession.getState().setLanguage("pcm"));
    mockFetch((c) => (c.url.endsWith("/api/v1/me/") ? json(200, user) : json(200, { opted_in: true })));
    renderWithClient(<Profile />);
    expect(await screen.findByRole("checkbox", { name: "Send reminder and receipt for WhatsApp", checked: true })).toBeTruthy();
    expect(screen.getByText(/reply STOP for WhatsApp/)).toBeTruthy();
  });
});

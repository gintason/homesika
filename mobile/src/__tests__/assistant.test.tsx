import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import { router } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { Alert } from "react-native";

import Help from "@/app/(app)/(tabs)/help";
import { tokens } from "@/lib/secure";
import { useSession } from "@/store/session";
import { json, mockFetch, renderWithClient, type Call } from "@/testing/utils";

const HISTORY = "/api/v1/assistant/messages/?channel=app";
const MESSAGES = "/api/v1/assistant/messages/";

const msg = (id: string, direction: "in" | "out", body: string, extra: Record<string, unknown> = {}) => ({
  id,
  direction,
  sender: direction === "in" ? "person" : "assistant",
  kind: "text",
  body,
  status: direction === "in" ? "received" : "delivered",
  error: "",
  sent_by_name: null,
  created_at: "2026-10-15T10:00:00Z",
  ...extra,
});

const history = (messages: unknown[] = [], pending_action: unknown = null) => ({
  conversation: messages.length ? "conv-1" : null,
  messages,
  pending_action,
});

const reply = (text: string, extra: Record<string, unknown> = {}) => ({
  conversation: "conv-1",
  text,
  pending_action: null,
  escalated: false,
  ...extra,
});

const action = {
  id: "11111111-2222-3333-4444-555555555555",
  tool: "create_my_payment_link",
  summary: "Create a payment link for ₦440,000.00 to Obi Properties",
  status: "proposed",
  expires_at: "2026-10-15T10:15:00Z",
};

const isPost = (c: Call) => c.method === "POST" && c.url.endsWith(MESSAGES);

beforeEach(async () => {
  jest.clearAllMocks();
  await tokens.set("access-1", "refresh-1");
  useSession.setState({ status: "ready", profile: { firstName: "Ada", lastName: "Obi", phone: "+2348012345678" }, lockSuspendedUntil: 0 });
});

afterEach(async () => {
  await act(() => useSession.getState().setLanguage("en"));
});

describe("Help: assistant chat", () => {
  it("shows the history, sends a message and shows the reply (typing indicator while waiting)", async () => {
    let answer!: (r: Response) => void;
    const calls = mockFetch((c) => {
      if (c.url.endsWith(HISTORY)) return json(200, history([msg("m1", "in", "Hello"), msg("m2", "out", "Hi Ada, how can I help?")]));
      if (isPost(c)) return new Promise<Response>((r) => (answer = r));
      return undefined;
    });
    renderWithClient(<Help />);
    expect(await screen.findByText("Hi Ada, how can I help?")).toBeTruthy();
    expect(screen.getByText("Hello")).toBeTruthy();

    fireEvent.changeText(screen.getByLabelText("Message"), "  How much do I owe?  ");
    fireEvent.press(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("How much do I owe?")).toBeTruthy();
    expect(screen.getByTestId("typing")).toBeTruthy();
    expect(screen.getByLabelText("Message").props.value).toBe("");

    await act(async () => answer(json(201, reply("You owe ₦440,000.00 in total."))));
    expect(await screen.findByText("You owe ₦440,000.00 in total.")).toBeTruthy();
    expect(screen.queryByTestId("typing")).toBeNull();

    const post = calls.find(isPost)!;
    expect(post.body).toEqual({ text: "How much do I owe?", channel: "app" });
    expect(post.headers.Authorization).toBe("Bearer access-1");
  });

  it("offers localised suggested questions and the 112 note in a new chat", async () => {
    const calls = mockFetch((c) => (c.url.endsWith(HISTORY) ? json(200, history()) : isPost(c) ? json(201, reply("You owe nothing.")) : undefined));
    renderWithClient(<Help />);
    expect(await screen.findByText("In an emergency call 112. Homesika is not an emergency service.")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Send me my receipts" }));
    expect(await screen.findByText("You owe nothing.")).toBeTruthy();
    expect(calls.find(isPost)!.body).toEqual({ text: "Send me my receipts", channel: "app" });
  });

  it("shows a confirmation card and confirms it", async () => {
    const calls = mockFetch((c) => {
      if (c.url.endsWith(HISTORY)) return json(200, history([msg("m1", "in", "I want to pay"), msg("m2", "out", "Tap Confirm to get the link.")], action));
      if (c.url.endsWith(`/api/v1/assistant/actions/${action.id}/confirm/`))
        return json(200, reply("Here is your payment link: https://app.homesika.com/pay/HSK-ABC123"));
      return undefined;
    });
    renderWithClient(<Help />);
    expect(await screen.findByText(action.summary)).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText(/Here is your payment link/)).toBeTruthy();
    expect(screen.queryByText(action.summary)).toBeNull();
    const confirm = calls.find((c) => c.url.includes("/actions/"))!;
    expect(confirm.method).toBe("POST");
    expect(confirm.body).toBeUndefined();

    // The pay link opens in the in-app browser like the pay flow, then the result screen.
    fireEvent.press(screen.getByRole("link", { name: "Open payment link" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith({ pathname: "/pay/[reference]", params: { reference: "HSK-ABC123" } }));
    expect(WebBrowser.openBrowserAsync).toHaveBeenCalledWith("https://app.homesika.com/pay/HSK-ABC123", expect.any(Object));
    expect(useSession.getState().lockSuspendedUntil).toBeGreaterThan(Date.now());
  });

  it("rejects a proposed action", async () => {
    const calls = mockFetch((c) => {
      if (c.url.endsWith(HISTORY)) return json(200, history([msg("m1", "out", "Shall I book it?")], action));
      if (c.url.endsWith(`/actions/${action.id}/reject/`)) return json(200, reply("Okay, I've cancelled that."));
      return undefined;
    });
    renderWithClient(<Help />);
    fireEvent.press(await screen.findByRole("button", { name: "Cancel" }));
    expect(await screen.findByText("Okay, I've cancelled that.")).toBeTruthy();
    expect(screen.queryByText(action.summary)).toBeNull();
    expect(calls.filter((c) => c.url.includes("/actions/")).map((c) => c.url)).toEqual([
      `http://localhost:8001/api/v1/assistant/actions/${action.id}/reject/`,
    ]);
  });

  it("shows a pending action proposed in a reply", async () => {
    mockFetch((c) =>
      c.url.endsWith(HISTORY) ? json(200, history()) : isPost(c) ? json(201, reply("Please confirm below.", { pending_action: action })) : undefined,
    );
    renderWithClient(<Help />);
    fireEvent.changeText(await screen.findByLabelText("Message"), "Send me a pay link");
    fireEvent.press(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(action.summary)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeTruthy();
  });

  it("tells the user a person will reply when the chat is escalated", async () => {
    mockFetch((c) =>
      c.url.endsWith(HISTORY)
        ? json(200, history())
        : isPost(c)
          ? json(201, reply("I've passed this to the Homesika team.", { escalated: true }))
          : undefined,
    );
    renderWithClient(<Help />);
    fireEvent.changeText(await screen.findByLabelText("Message"), "I already paid but it says I owe");
    fireEvent.press(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/They'll reply here in this chat during working hours/)).toBeTruthy();
  });

  it("retries after a network failure without sending twice", async () => {
    let posts = 0;
    const calls = mockFetch((c) => {
      if (c.url.endsWith(HISTORY)) return json(200, history()); // the first attempt never reached the server
      if (isPost(c)) {
        posts++;
        return posts === 1 ? Promise.reject(new TypeError("Network request failed")) : json(201, reply("You owe ₦440,000.00."));
      }
      return undefined;
    });
    renderWithClient(<Help />);
    fireEvent.changeText(await screen.findByLabelText("Message"), "How much do I owe?");
    fireEvent.press(screen.getByRole("button", { name: "Send" }));
    const retry = await screen.findByRole("button", { name: "Not sent. Tap to try again" });
    expect(posts).toBe(1);

    fireEvent.press(retry);
    fireEvent.press(retry); // a second tap while retrying is ignored
    expect(await screen.findByText("You owe ₦440,000.00.")).toBeTruthy();
    expect(posts).toBe(2);
    expect(screen.getAllByText("How much do I owe?")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Not sent. Tap to try again" })).toBeNull();
    // Two history reads: the first load and the check before re-sending.
    expect(calls.filter((c) => c.url.endsWith(HISTORY))).toHaveLength(2);
  });

  it("doesn't re-send when the server already got the message (only the response was lost)", async () => {
    let landed = false;
    let posts = 0;
    mockFetch((c) => {
      if (c.url.endsWith(HISTORY))
        return json(200, landed ? history([msg("m1", "in", "Send me my receipts"), msg("m2", "out", "Receipt RCT-000004 is ready.")]) : history());
      if (isPost(c)) {
        posts++;
        landed = true;
        return Promise.reject(new TypeError("Network request failed"));
      }
      return undefined;
    });
    renderWithClient(<Help />);
    fireEvent.changeText(await screen.findByLabelText("Message"), "Send me my receipts");
    fireEvent.press(screen.getByRole("button", { name: "Send" }));
    fireEvent.press(screen.getByRole("button", { name: "Send" })); // double tap while in flight
    fireEvent.press(await screen.findByRole("button", { name: "Not sent. Tap to try again" }));
    expect(await screen.findByText("Receipt RCT-000004 is ready.")).toBeTruthy();
    expect(posts).toBe(1);
    expect(screen.getAllByText("Send me my receipts")).toHaveLength(1);
  });

  it("clears the chat after confirming (DELETE)", async () => {
    const alert = jest.spyOn(Alert, "alert").mockImplementation((_title, _body, buttons) => {
      buttons?.find((b) => b.style === "destructive")?.onPress?.();
    });
    const calls = mockFetch((c) => {
      if (c.url.endsWith(HISTORY)) return json(200, history([msg("m1", "in", "Hello"), msg("m2", "out", "Hi there")]));
      if (c.method === "DELETE" && c.url.endsWith(MESSAGES)) return json(204);
      return undefined;
    });
    renderWithClient(<Help />);
    expect(await screen.findByText("Hi there")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "More options" }));
    fireEvent.press(screen.getByRole("button", { name: "Clear chat" }));
    expect(alert).toHaveBeenCalledWith("Clear this chat?", expect.any(String), expect.any(Array));
    expect(await screen.findByText("Ask Homesika")).toBeTruthy();
    expect(screen.queryByText("Hi there")).toBeNull();
    expect(calls.filter((c) => c.method === "DELETE")).toHaveLength(1);
    alert.mockRestore();
  });

  it("shows a counter near the 2000-character limit", async () => {
    mockFetch((c) => (c.url.endsWith(HISTORY) ? json(200, history()) : undefined));
    renderWithClient(<Help />);
    const input = await screen.findByLabelText("Message");
    expect(input.props.maxLength).toBe(2000);
    fireEvent.changeText(input, "a".repeat(100));
    expect(screen.queryByText(/of 2000 characters/)).toBeNull();
    fireEvent.changeText(input, "a".repeat(1900));
    expect(screen.getByText("1900 of 2000 characters")).toBeTruthy();
  });

  it("renders in Pidgin", async () => {
    await act(() => useSession.getState().setLanguage("pcm"));
    mockFetch((c) => (c.url.endsWith(HISTORY) ? json(200, history()) : undefined));
    renderWithClient(<Help />);
    expect(await screen.findByRole("button", { name: "Abeg how much I dey owe?" })).toBeTruthy();
    expect(screen.getByText("If na emergency, call 112 sharp sharp. Homesika no be emergency service.")).toBeTruthy();
    expect(screen.getByLabelText("Message")).toBeTruthy();
  });
});

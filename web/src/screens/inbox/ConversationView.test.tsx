import { fireEvent, screen, waitFor } from "@testing-library/react";

import { envelope, mockFetch } from "../../test/fetch";
import { conversation } from "../../test/fixtures";
import { ORG_ID, renderOrgScreen } from "../../test/render";
import { ConversationView } from "./ConversationView";

const C = `/api/v1/orgs/${ORG_ID}/conversations/c1/`;
const open = (role?: "agent" | "viewer") =>
  renderOrgScreen(<ConversationView />, { path: "inbox/:conversationId", url: "inbox/c1", role });

describe("Inbox conversation", () => {
  it("shows the thread and escalation, and disables replies outside the 24-hour window", async () => {
    mockFetch({ [`GET ${C}`]: { body: conversation({ can_reply_freely: false }) } });
    open();
    expect(await screen.findByText("My rent receipt is wrong")).toBeInTheDocument();
    expect(screen.getByText(/^Assistant ·/)).toBeInTheDocument();
    expect(screen.getAllByText("Dispute").length).toBeGreaterThan(0);
    expect(screen.getByText(/more than 24 hours ago/)).toBeInTheDocument();
    expect(screen.getByLabelText("Your reply")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("sends a reply with an Idempotency-Key, and handles 409 whatsapp_window_closed", async () => {
    const m = mockFetch({
      [`GET ${C}`]: { body: conversation() },
      [`POST ${C}reply/`]: (_req, nth) =>
        nth === 1
          ? { status: 201, body: conversation({ status: "handoff" }) }
          : envelope(409, "whatsapp_window_closed", "This person last wrote more than 24 hours ago."),
    });
    open();
    const box = await screen.findByLabelText("Your reply");
    expect(box).toBeEnabled();
    fireEvent.change(box, { target: { value: "Sorry about that, checking now." } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(m.find("POST", `${C}reply/`)).toHaveLength(1));
    const first = m.find("POST", `${C}reply/`)[0]!;
    expect(first.body).toEqual({ body: "Sorry about that, checking now." });
    expect(first.headers["Idempotency-Key"]).toMatch(/^[A-Za-z0-9_\-:.]{16,64}$/);
    await waitFor(() => expect(screen.getByLabelText("Your reply")).toHaveValue(""));

    fireEvent.change(screen.getByLabelText("Your reply"), { target: { value: "Are you there?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/WhatsApp only lets businesses reply freely/)).toBeInTheDocument();
    expect(screen.getByLabelText("Your reply")).toBeDisabled();
    expect(m.find("POST", `${C}reply/`)[1]!.headers["Idempotency-Key"]).not.toBe(first.headers["Idempotency-Key"]);
  });

  it("takes over and hands back to the assistant", async () => {
    let status: "bot" | "handoff" = "bot";
    const m = mockFetch({
      [`GET ${C}`]: () => ({ body: conversation({ status }) }),
      [`POST ${C}take-over/`]: () => {
        status = "handoff";
        return { body: conversation({ status }) };
      },
      [`POST ${C}release/`]: () => {
        status = "bot";
        return { body: conversation({ status }) };
      },
    });
    open("agent");
    fireEvent.click(await screen.findByRole("button", { name: "Take over" }));
    fireEvent.click(await screen.findByRole("button", { name: "Hand back to assistant" }));
    expect(await screen.findByRole("button", { name: "Take over" })).toBeInTheDocument();
    expect(m.find("POST", `${C}take-over/`)).toHaveLength(1);
    expect(m.find("POST", `${C}release/`)).toHaveLength(1);
    expect(m.find("POST", `${C}take-over/`)[0]!.body).toBeUndefined();
  });

  it("is read-only without inbox.reply", async () => {
    mockFetch({ [`GET ${C}`]: { body: conversation() } });
    open("viewer");
    await screen.findByText("My rent receipt is wrong");
    expect(screen.queryByRole("button", { name: "Take over" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Your reply")).not.toBeInTheDocument();
  });
});

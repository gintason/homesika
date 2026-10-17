import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { mockFetch } from "../../test/fetch";
import { testQueryClient } from "../../test/render";
import { AssistantPanel } from "./AssistantPanel";

const MSG = "/api/v1/assistant/messages/";
const ACTION_ID = "6f1c2b9e-1d2a-4c3b-9e8f-0a1b2c3d4e5f";
const history = {
  conversation: "conv1",
  messages: [
    { id: "m1", direction: "in", sender: "person", kind: "text", body: "Who owes rent?", status: "received", error: "", sent_by_name: null, created_at: "" },
    {
      id: "m2",
      direction: "out",
      sender: "assistant",
      kind: "text",
      body: "Chidi owes ₦500,000. See https://homesika.test/arrears.",
      status: "sent",
      error: "",
      sent_by_name: null,
      created_at: "",
    },
  ],
  pending_action: null,
};

function renderPanel() {
  return render(
    <QueryClientProvider client={testQueryClient()}>
      <AssistantPanel open onClose={() => undefined} />
    </QueryClientProvider>,
  );
}

describe("Assistant panel", () => {
  it("loads web history with links, proposes an action and runs it only after Confirm", async () => {
    const m = mockFetch({
      [`GET ${MSG}`]: { body: history },
      [`POST ${MSG}`]: {
        status: 201,
        body: {
          conversation: "conv1",
          text: "I can send Chidi a payment link for ₦500,000. Confirm?",
          pending_action: { id: ACTION_ID, tool: "send_payment_link", summary: "Send Chidi a pay link for ₦500,000", status: "proposed", expires_at: "2026-10-17T10:15:00Z" },
          escalated: false,
        },
      },
      [`POST /api/v1/assistant/actions/${ACTION_ID}/confirm/`]: {
        body: { conversation: "conv1", text: "Done. The link was sent by SMS.", pending_action: null, escalated: false },
      },
    });
    renderPanel();
    expect(await screen.findByRole("link", { name: "https://homesika.test/arrears" })).toHaveAttribute("href", "https://homesika.test/arrears");
    expect(m.find("GET", MSG)[0]!.search.get("channel")).toBe("web");
    expect(screen.getByText(/Answers come from your Homesika data/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Message to the assistant"), { target: { value: "Send Chidi a link" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    const card = await screen.findByRole("group", { name: "Confirm this action" });
    expect(within(card).getByText("Send Chidi a pay link for ₦500,000")).toBeInTheDocument();
    expect(m.find("POST", MSG)[0]!.body).toEqual({ text: "Send Chidi a link", channel: "web" });
    expect(m.find("POST", `/api/v1/assistant/actions/${ACTION_ID}/confirm/`)).toHaveLength(0);

    fireEvent.click(within(card).getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("Done. The link was sent by SMS.")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Confirm this action" })).not.toBeInTheDocument();
    expect(m.find("POST", `/api/v1/assistant/actions/${ACTION_ID}/confirm/`)).toHaveLength(1);
  });

  it("cancels a pending action with reject, and clears the conversation with DELETE", async () => {
    const m = mockFetch({
      [`GET ${MSG}`]: {
        body: { ...history, pending_action: { id: ACTION_ID, tool: "send_payment_link", summary: "Send a link", status: "proposed", expires_at: "2026-10-17T10:15:00Z" } },
      },
      [`POST /api/v1/assistant/actions/${ACTION_ID}/reject/`]: {
        body: { conversation: "conv1", text: "Okay, I won't send it.", pending_action: null, escalated: false },
      },
      [`DELETE ${MSG}`]: { status: 204 },
    });
    renderPanel();
    const card = await screen.findByRole("group", { name: "Confirm this action" });
    fireEvent.click(within(card).getByRole("button", { name: "Cancel" }));
    expect(await screen.findByText("Okay, I won't send it.")).toBeInTheDocument();
    expect(m.find("POST", `/api/v1/assistant/actions/${ACTION_ID}/reject/`)).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Clear conversation" }));
    const confirm = screen.getByRole("group", { name: "Clear this conversation?" });
    fireEvent.click(within(confirm).getByRole("button", { name: "Clear conversation" }));
    await waitFor(() => expect(m.find("DELETE", MSG)).toHaveLength(1));
    expect(await screen.findByText(/Who owes rent this month/)).toBeInTheDocument();
    expect(screen.queryByText("Who owes rent?")).not.toBeInTheDocument();
  });
});

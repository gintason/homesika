import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { mockFetch } from "../../test/fetch";
import { ORG_ID, renderOrgScreen } from "../../test/render";
import { HelpArticles } from "./HelpArticles";

const PATH = `/api/v1/orgs/${ORG_ID}/kb-articles/`;

describe("Help articles", () => {
  it("validates the article form, then creates it", async () => {
    const m = mockFetch({
      [`GET ${PATH}`]: { body: [] },
      [`POST ${PATH}`]: { status: 201, body: { id: "k1" } },
    });
    renderOrgScreen(<HelpArticles />, { path: "settings/help-articles", url: "settings/help-articles", role: "manager" });
    fireEvent.click((await screen.findAllByRole("button", { name: "New article" }))[0]!);
    const dialog = within(screen.getByRole("dialog", { name: "New article" }));

    fireEvent.click(dialog.getByRole("button", { name: "New article" }));
    expect(dialog.getAllByText("This field is required.")).toHaveLength(3);

    fireEvent.change(dialog.getByLabelText("Title"), { target: { value: "How to pay rent" } });
    fireEvent.change(dialog.getByLabelText("Short name"), { target: { value: "How To Pay" } });
    fireEvent.change(dialog.getByLabelText("Article"), { target: { value: "Pay with the link we send you." } });
    fireEvent.click(dialog.getByRole("button", { name: "New article" }));
    expect(dialog.getByText("Use only lowercase letters, numbers and dashes.")).toBeInTheDocument();
    expect(m.find("POST", PATH)).toHaveLength(0);

    fireEvent.change(dialog.getByLabelText("Short name"), { target: { value: "how-to-pay" } });
    fireEvent.change(dialog.getByLabelText("Language"), { target: { value: "pcm" } });
    fireEvent.click(dialog.getByLabelText("Prospects (people looking for a home)"));
    fireEvent.click(dialog.getByLabelText("Tenants"));
    fireEvent.click(dialog.getByRole("button", { name: "New article" }));
    await waitFor(() => expect(m.find("POST", PATH)).toHaveLength(1));
    expect(m.find("POST", PATH)[0]!.body).toEqual({
      slug: "how-to-pay",
      title: "How to pay rent",
      body: "Pay with the link we send you.",
      language: "pcm",
      audience: ["tenant", "prospect"],
      status: "published",
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("is only for kb.manage", () => {
    const m = mockFetch({});
    renderOrgScreen(<HelpArticles />, { path: "settings/help-articles", url: "settings/help-articles", role: "agent" });
    expect(screen.getByText("Only owners and managers can change help articles.")).toBeInTheDocument();
    expect(m.calls).toHaveLength(0);
  });
});

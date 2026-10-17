import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { envelope, mockFetch } from "../../test/fetch";
import { LISTING } from "../../test/fixtures";
import { ORG_ID, renderOrgScreen } from "../../test/render";
import { ListingForm } from "./ListingForm";

const BASE = `/api/v1/orgs/${ORG_ID}`;
const DRAFT = {
  title: "Spacious 2-bedroom flat in Yaba",
  description: "A bright flat close to the main road.",
  whatsapp_caption: "2-bed flat in Yaba, ₦1.5m/yr. Reply to book a viewing!",
  features: ["Prepaid meter", "Borehole"],
  suggested_replies: [{ question: "Is the price negotiable?", answer: "The agent will confirm." }],
  model: "claude-x",
};

function fillFacts() {
  fireEvent.change(screen.getByLabelText("Area"), { target: { value: "Yaba" } });
  fireEvent.change(screen.getByLabelText("Rent amount"), { target: { value: "1,500,000" } });
  fireEvent.change(screen.getByLabelText(/^Bedrooms/), { target: { value: "2" } });
  fireEvent.change(screen.getByLabelText("New feature"), { target: { value: "Parking" } });
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
  fireEvent.change(screen.getByLabelText("What is it?"), { target: { value: "2-bedroom flat" } });
}

describe("Listing form + listing writer", () => {
  it("sends the facts to the writer and 'Use this' fills the form fields", async () => {
    const m = mockFetch({
      [`GET ${BASE}/units/`]: { body: [] },
      [`POST ${BASE}/listings/generate/`]: { body: DRAFT },
      [`POST ${BASE}/listings/`]: { status: 201, body: { ...LISTING, id: "l9" } },
    });
    renderOrgScreen(<ListingForm />, { path: "listings/new", url: "listings/new" });
    fillFacts();
    fireEvent.click(screen.getByRole("button", { name: "Write a draft" }));

    const draft = await screen.findByRole("region", { name: "Draft" });
    expect(within(draft).getByText(/This is a draft written by AI/)).toBeInTheDocument();
    expect(m.find("POST", `${BASE}/listings/generate/`)[0]!.body).toEqual({
      kind: "2-bedroom flat",
      area: "Yaba",
      city: "Lagos",
      bedrooms: 2,
      rent_amount: "1500000.00",
      rent_period: "year",
      features: ["Parking"],
    });

    fireEvent.click(within(draft).getByRole("button", { name: "Use this: Title" }));
    expect(screen.getByLabelText("Title")).toHaveValue(DRAFT.title);
    fireEvent.click(within(draft).getByRole("button", { name: "Use this: WhatsApp caption" }));
    expect(screen.getByLabelText(/^WhatsApp caption/)).toHaveValue(DRAFT.whatsapp_caption);
    fireEvent.click(within(draft).getByRole("button", { name: "Use this: Features" }));
    const chips = screen.getByRole("list", { name: "Features" });
    expect(within(chips).getAllByRole("listitem").map((li) => li.textContent?.replace("×", ""))).toEqual(["Parking", "Prepaid meter", "Borehole"]);

    fireEvent.click(screen.getByRole("button", { name: "New listing" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(`/orgs/${ORG_ID}/listings/l9`));
    expect(m.find("POST", `${BASE}/listings/`)[0]!.body).toMatchObject({
      title: DRAFT.title,
      area: "Yaba",
      bedrooms: 2,
      bathrooms: null,
      rent_amount: "1500000.00",
      whatsapp_caption: DRAFT.whatsapp_caption,
      features: ["Parking", "Prepaid meter", "Borehole"],
      ai_generated: true,
      unit: null,
    });
  });

  it("explains when the writer is unavailable (503 generator_unavailable)", async () => {
    mockFetch({
      [`GET ${BASE}/units/`]: { body: [] },
      [`POST ${BASE}/listings/generate/`]: envelope(503, "generator_unavailable", "The listing writer is busy. Please try again in a minute."),
    });
    renderOrgScreen(<ListingForm />, { path: "listings/new", url: "listings/new" });
    fillFacts();
    fireEvent.click(screen.getByRole("button", { name: "Write a draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The listing writer is busy");
    expect(screen.queryByRole("region", { name: "Draft" })).not.toBeInTheDocument();
  });

  it("asks for the facts before calling the writer, and validates the form", async () => {
    const m = mockFetch({ [`GET ${BASE}/units/`]: { body: [] } });
    renderOrgScreen(<ListingForm />, { path: "listings/new", url: "listings/new" });
    fireEvent.click(screen.getByRole("button", { name: "Write a draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Fill in the area and rent above first.");
    fireEvent.click(screen.getByRole("button", { name: "New listing" }));
    expect(await screen.findAllByText("This field is required.")).toHaveLength(4);
    expect(m.calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });
});

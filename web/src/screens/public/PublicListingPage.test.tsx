import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";

import { envelope, mockFetch } from "../../test/fetch";
import { PublicListingPage } from "./PublicListingPage";

const PATH = "/api/v1/listings/LST-AB12CD/";
const S1 = { id: "s1", starts_at: "2026-10-20T10:00:00Z", ends_at: "2026-10-20T10:30:00Z" };
const S2 = { id: "s2", starts_at: "2026-10-21T10:00:00Z", ends_at: "2026-10-21T10:30:00Z" };
const PUBLIC = {
  ref: "LST-AB12CD",
  title: "2-bedroom flat in Yaba",
  description: "Bright flat.",
  features: ["Prepaid meter"],
  area: "Yaba",
  city: "Lagos",
  bedrooms: 2,
  bathrooms: 2,
  rent_amount: "1500000.00",
  rent_period: "year",
  currency: "NGN",
  landlord: "Adeyemi Properties",
  photos: [{ id: "p1", url: "https://cdn.test/1.jpg", caption: "", position: 0 }],
  published_at: "2026-10-01T09:00:00Z",
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/l/LST-AB12CD"]}>
      <Routes>
        <Route path="/l/:ref" element={<PublicListingPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const section = (name: string) => screen.getByRole("heading", { name }).closest("section")!;

describe("Public listing page", () => {
  it("books a viewing, recovering from slot_unavailable", async () => {
    const m = mockFetch({
      [`GET ${PATH}`]: (_req, nth) => ({ body: { ...PUBLIC, slots: nth === 1 ? [S1, S2] : [S2] } }),
      [`POST ${PATH}book/`]: (req) =>
        (req.body as { slot: string }).slot === "s1"
          ? envelope(409, "slot_unavailable", "That viewing time is no longer available. Please pick another.")
          : { status: 201, body: { status: "booked", starts_at: S2.starts_at } },
    });
    renderPage();
    expect(await screen.findByRole("heading", { name: "2-bedroom flat in Yaba" })).toBeInTheDocument();
    expect(screen.getByText(/1,500,000\.00 per year/)).toBeInTheDocument();
    expect(screen.getByText("Listed by Adeyemi Properties")).toBeInTheDocument();

    const book = within(section("Book a viewing"));
    fireEvent.click(book.getByRole("button", { name: "Book viewing" }));
    expect(book.getByText("Choose a viewing time.")).toBeInTheDocument();
    expect(m.find("POST", `${PATH}book/`)).toHaveLength(0);

    fireEvent.change(book.getByLabelText("Viewing time"), { target: { value: "s1" } });
    fireEvent.change(book.getByLabelText("Your name"), { target: { value: "Bisi" } });
    fireEvent.change(book.getByLabelText("Phone number"), { target: { value: "0809 111 2222" } });
    fireEvent.click(book.getByRole("button", { name: "Book viewing" }));

    expect(await book.findByRole("alert")).toHaveTextContent("no longer available");
    await waitFor(() => expect(m.find("GET", PATH)).toHaveLength(2));
    expect(m.find("POST", `${PATH}book/`)[0]!.body).toEqual({ name: "Bisi", phone_number: "+2348091112222", slot: "s1" });
    expect(m.find("POST", `${PATH}book/`)[0]!.headers.Authorization).toBeUndefined();

    const picker = within(section("Book a viewing")).getByLabelText("Viewing time");
    await waitFor(() => expect(within(picker).queryAllByRole("option")).toHaveLength(2)); // placeholder + s2
    fireEvent.change(picker, { target: { value: "s2" } });
    fireEvent.click(within(section("Book a viewing")).getByRole("button", { name: "Book viewing" }));
    expect(await screen.findByText(/Your viewing is booked for/)).toBeInTheDocument();
  });

  it("sends an enquiry", async () => {
    const m = mockFetch({
      [`GET ${PATH}`]: { body: { ...PUBLIC, slots: [] } },
      [`POST ${PATH}enquire/`]: { status: 201, body: { status: "received" } },
    });
    renderPage();
    await screen.findByText(/No viewing times are open/);
    const form = within(section("Ask a question"));
    fireEvent.change(form.getByLabelText("Your name"), { target: { value: "Bisi" } });
    fireEvent.change(form.getByLabelText("Phone number"), { target: { value: "08091112222" } });
    fireEvent.change(form.getByLabelText(/Message/), { target: { value: "Is there parking?" } });
    fireEvent.click(form.getByRole("button", { name: "Send enquiry" }));
    expect(await screen.findByText(/The agent has your details/)).toBeInTheDocument();
    expect(m.find("POST", `${PATH}enquire/`)[0]!.body).toEqual({ name: "Bisi", phone_number: "+2348091112222", message: "Is there parking?" });
  });

  it("says when the listing is gone", async () => {
    mockFetch({ [`GET ${PATH}`]: envelope(404, "not_found", "Not found.") });
    renderPage();
    expect(await screen.findByText(/It may have been let already/)).toBeInTheDocument();
  });
});

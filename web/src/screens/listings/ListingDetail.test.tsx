import { fireEvent, screen, waitFor } from "@testing-library/react";

import { mockFetch } from "../../test/fetch";
import { LISTING } from "../../test/fixtures";
import { ORG_ID, renderOrgScreen } from "../../test/render";
import { ListingDetail } from "./ListingDetail";

const BASE = `/api/v1/orgs/${ORG_ID}`;
const SLOT = { id: "s1", listing: "l1", starts_at: "2026-10-20T10:00:00Z", ends_at: "2026-10-20T10:30:00Z", capacity: 3, agent: null, booked: 1 };

function routes(extra: Parameters<typeof mockFetch>[0] = {}) {
  return mockFetch({
    [`GET ${BASE}/listings/l1/`]: { body: LISTING },
    [`GET ${BASE}/viewing-slots/`]: { body: [SLOT] },
    ...extra,
  });
}

describe("Listing detail", () => {
  it("uploads a photo as multipart with the field 'image'", async () => {
    const m = routes({
      [`POST ${BASE}/listings/l1/photos/`]: { status: 201, body: { id: "ph1", url: "https://cdn.test/p.jpg", caption: "", position: 0 } },
    });
    renderOrgScreen(<ListingDetail />, { path: "listings/:listingId", url: "listings/l1" });
    const input = await screen.findByLabelText("Add photos");
    const file = new File(["jpeg-bytes"], "front.jpg", { type: "image/jpeg" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(m.find("POST", `${BASE}/listings/l1/photos/`)).toHaveLength(1));
    const post = m.find("POST", `${BASE}/listings/l1/photos/`)[0]!;
    expect(post.body).toBeInstanceOf(FormData);
    expect((post.body as FormData).get("image")).toBe(file);
    // The browser must set the multipart boundary itself.
    expect(post.headers["Content-Type"]).toBeUndefined();
    expect(await screen.findByText("Photo added")).toBeInTheDocument();
  });

  it("shows viewing slots with the booked count, and publishes", async () => {
    const m = routes({ [`POST ${BASE}/listings/l1/publish/`]: { body: { ...LISTING, status: "published" } } });
    renderOrgScreen(<ListingDetail />, { path: "listings/:listingId", url: "listings/l1" });
    expect(await screen.findByText(/Booked: 1 of 3/)).toBeInTheDocument();
    expect(screen.getByLabelText("Public link")).toHaveValue(`${window.location.origin}/l/LST-AB12CD`);
    fireEvent.click(screen.getByRole("button", { name: "Publish" }));
    await waitFor(() => expect(m.find("POST", `${BASE}/listings/l1/publish/`)).toHaveLength(1));
  });

  it("hides publish, edit and uploads without listing.manage", async () => {
    routes();
    renderOrgScreen(<ListingDetail />, { path: "listings/:listingId", url: "listings/l1", role: "accountant" });
    expect(await screen.findByRole("heading", { name: LISTING.title })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Add photos")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add viewing time" })).not.toBeInTheDocument();
  });
});

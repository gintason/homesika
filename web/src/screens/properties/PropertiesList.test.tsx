import { fireEvent, screen } from "@testing-library/react";

import { envelope, mockFetch } from "../../test/fetch";
import { ORG_ID, renderOrgScreen } from "../../test/render";
import { PropertiesList } from "./PropertiesList";

const PATH = `/api/v1/orgs/${ORG_ID}/properties/`;
const PROPERTY = {
  id: "p1",
  name: "Palm Court",
  kind: "block",
  address: "12 Allen Avenue",
  city: "Ikeja",
  state: "Lagos",
  country: "NG",
  notes: "",
  is_archived: false,
  unit_count: 6,
  occupied_count: 4,
  created_at: "2026-10-01T00:00:00Z",
};

describe("Properties list", () => {
  it("shows a skeleton, then the properties", async () => {
    mockFetch({ [`GET ${PATH}`]: { body: [PROPERTY] } });
    renderOrgScreen(<PropertiesList />, { path: "properties", url: "properties" });
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(await screen.findByRole("link", { name: "Palm Court" })).toHaveAttribute("href", `/orgs/${ORG_ID}/properties/p1`);
    expect(screen.getByText("4 of 6 occupied")).toBeInTheDocument();
    expect(screen.getByText("Block of flats")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add property" })).toBeInTheDocument();
  });

  it("shows an empty state with the add action", async () => {
    mockFetch({ [`GET ${PATH}`]: { body: [] } });
    renderOrgScreen(<PropertiesList />, { path: "properties", url: "properties" });
    expect(await screen.findByRole("heading", { name: "No properties yet" })).toBeInTheDocument();
  });

  it("shows an error with a working retry", async () => {
    let fail = true;
    mockFetch({
      [`GET ${PATH}`]: () => (fail ? envelope(500, "server_error", "Something went wrong. Please try again.") : { body: [PROPERTY] }),
    });
    renderOrgScreen(<PropertiesList />, { path: "properties", url: "properties" });
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't load this.");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "Palm Court" })).toBeInTheDocument();
  });

  it("hides the add action from read-only roles", async () => {
    mockFetch({ [`GET ${PATH}`]: { body: [PROPERTY] } });
    renderOrgScreen(<PropertiesList />, { path: "properties", url: "properties", role: "viewer" });
    await screen.findByRole("link", { name: "Palm Court" });
    expect(screen.queryByRole("link", { name: "Add property" })).not.toBeInTheDocument();
  });
});

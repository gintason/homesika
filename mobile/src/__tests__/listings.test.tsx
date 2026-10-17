import { fireEvent, screen, waitFor } from "@testing-library/react-native";
import { router, useLocalSearchParams } from "expo-router";

import FindPlace from "@/app/(app)/find/index";
import ListingDetail from "@/app/(app)/find/[ref]";
import { useSession } from "@/store/session";
import { json, mockFetch, renderWithClient, type Call } from "@/testing/utils";

const listing = {
  ref: "LST-PALM4D",
  title: "Flat 4D, Palm Court",
  description: "Bright 3-bedroom flat with parking.",
  features: ["Parking", "Prepaid meter"],
  area: "Lekki",
  city: "Lagos",
  bedrooms: 3,
  bathrooms: 3,
  rent_amount: "4500000.00",
  rent_period: "year",
  currency: "NGN",
  landlord: "Obi Properties",
  photos: [{ id: "p1", url: "https://cdn.example.com/p1.jpg", caption: "Living room", position: 0 }],
  published_at: "2026-10-01T00:00:00Z",
};

const slots = [
  { id: "aaaaaaaa-0000-0000-0000-000000000001", starts_at: "2026-10-18T13:00:00Z", ends_at: "2026-10-18T13:30:00Z" },
  { id: "aaaaaaaa-0000-0000-0000-000000000002", starts_at: "2026-10-19T09:00:00Z", ends_at: "2026-10-19T09:30:00Z" },
];

beforeEach(() => {
  jest.clearAllMocks();
  useSession.setState({ status: "ready", profile: { firstName: "Ada", lastName: "Obi", phone: "+2348012345678" } });
});

describe("Find a place", () => {
  it("lists published listings and searches with filters", async () => {
    const calls = mockFetch((c) => (c.url.includes("/api/v1/listings/") ? json(200, [listing]) : undefined));
    renderWithClient(<FindPlace />);
    expect(await screen.findByText("Flat 4D, Palm Court")).toBeTruthy();
    expect(screen.getByText("₦4,500,000.00")).toBeTruthy();
    expect(calls[0]!.url).toBe("http://localhost:8001/api/v1/listings/");
    expect(calls[0]!.headers.Authorization).toBeUndefined(); // public endpoint

    fireEvent.changeText(screen.getByLabelText("Area"), "Lekki");
    fireEvent.changeText(screen.getByLabelText("Highest rent"), "5,000,000");
    fireEvent.press(screen.getByRole("radio", { name: "Bedrooms: 3" }));
    fireEvent.press(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1]!.url).toBe("http://localhost:8001/api/v1/listings/?area=Lekki&max_rent=5000000.00&bedrooms=3");

    fireEvent.press(await screen.findByRole("button", { name: /Flat 4D, Palm Court/ }));
    expect(router.push).toHaveBeenCalledWith({ pathname: "/find/[ref]", params: { ref: "LST-PALM4D" } });
  });

  it("books a viewing with details from the profile, and handles a slot that was just taken", async () => {
    jest.mocked(useLocalSearchParams).mockReturnValue({ ref: "LST-PALM4D" });
    let taken = true;
    const detailUrl = "http://localhost:8001/api/v1/listings/LST-PALM4D/";
    const calls = mockFetch((c: Call) => {
      if (c.url === detailUrl) return json(200, { ...listing, slots: taken ? slots : slots.slice(1) });
      if (c.url.endsWith("/book/")) {
        if (taken) {
          taken = false;
          return json(409, { error: { code: "slot_unavailable", message: "That viewing time is no longer available. Please pick another.", details: {} } });
        }
        return json(201, { status: "booked", starts_at: slots[1]!.starts_at });
      }
      return undefined;
    });
    renderWithClient(<ListingDetail />);
    expect(await screen.findByText("Parking")).toBeTruthy();
    expect(screen.getByLabelText("Living room")).toBeTruthy();
    expect(screen.getByLabelText("Your name").props.value).toBe("Ada Obi");

    fireEvent.press(screen.getByRole("radio", { name: "18 Oct 2026, 14:00" }));
    fireEvent.press(screen.getByRole("button", { name: "Book viewing" }));
    expect(await screen.findByText("That viewing time has just been taken. Please pick another.")).toBeTruthy();
    const firstBook = calls.find((c) => c.url.endsWith("/book/"))!;
    expect(firstBook.body).toEqual({ name: "Ada Obi", phone_number: "+2348012345678", slot: slots[0]!.id });
    // The listing is reloaded so only open times show, and the taken one is unselected.
    await waitFor(() => expect(calls.filter((c) => c.url === detailUrl).length).toBe(2));

    fireEvent.press(await screen.findByRole("radio", { name: "19 Oct 2026, 10:00" }));
    fireEvent.press(screen.getByRole("button", { name: "Book viewing" }));
    expect(await screen.findByText("Your viewing is booked for 19 Oct 2026, 10:00.")).toBeTruthy();
    expect(calls.filter((c) => c.url.endsWith("/book/")).map((c) => (c.body as { slot: string }).slot)).toEqual([slots[0]!.id, slots[1]!.id]);
  });

  it("asks about a listing (enquire)", async () => {
    jest.mocked(useLocalSearchParams).mockReturnValue({ ref: "LST-PALM4D" });
    const calls = mockFetch((c) => {
      if (c.url.endsWith("/api/v1/listings/LST-PALM4D/")) return json(200, { ...listing, slots: [] });
      if (c.url.endsWith("/enquire/")) return json(201, { status: "received" });
      return undefined;
    });
    renderWithClient(<ListingDetail />);
    expect(await screen.findByText(/No viewing times are open right now/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Book viewing" })).toBeNull();
    fireEvent.changeText(screen.getByLabelText("Your question"), "Is there parking for two cars?");
    fireEvent.press(screen.getByRole("button", { name: "Ask about it" }));
    expect(await screen.findByText("Sent. The landlord can now reach you on +234 801 234 5678.")).toBeTruthy();
    expect(calls.find((c) => c.url.endsWith("/enquire/"))!.body).toEqual({
      name: "Ada Obi",
      phone_number: "+2348012345678",
      message: "Is there parking for two cars?",
    });
  });
});

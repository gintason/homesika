import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import * as ImagePicker from "expo-image-picker";
import { router, useLocalSearchParams } from "expo-router";
import { Linking } from "react-native";

import RepairDetail from "@/app/(app)/repairs/[id]";
import RepairsHome from "@/app/(app)/repairs/index";
import ReportRepair from "@/app/(app)/repairs/new";
import ApplyAsArtisan from "@/app/(app)/work/apply";
import IdCheck from "@/app/(app)/work/id-check";
import WorkHome from "@/app/(app)/work/index";
import JobDetail from "@/app/(app)/work/job/[id]";
import People from "@/app/(app)/work/people";
import { visitChoices } from "@/lib/repairs";
import { tokens } from "@/lib/secure";
import { json, lease, mockFetch, renderWithClient, type Call } from "@/testing/utils";

const page = (results: unknown[]) => ({ next: null, previous: null, results });

function ticket(o: Record<string, unknown> = {}) {
  return {
    id: "t1",
    reference: "R0000A01",
    status: "awaiting_approval",
    category: "plumbing",
    priority: "urgent",
    title: "Kitchen tap leaking",
    description: "Drips all night long.",
    access_notes: "After 4pm",
    channel: "app",
    unit: { id: "u1", label: "Flat 2", property: "Palm Court", address: "12 Allen Avenue", city: "Ikeja", organization: "Bello Properties" },
    closed_reason: "",
    done_at: null,
    confirmed_at: null,
    auto_confirmed: false,
    created_at: "2026-10-14T09:00:00Z",
    photos: [],
    job: null,
    rating: null,
    events: [{ id: "e1", kind: "created", actor_role: "tenant", actor_name: "Ada", note: "", internal: false, created_at: "2026-10-14T09:00:00Z" }],
    can: ["cancel", "comment", "photo"],
    ...o,
  };
}

const kunleJob = (o: Record<string, unknown> = {}) => ({
  id: "j1",
  status: "accepted",
  artisan: { id: "a1", display_name: "Kunle Plumbing Works", is_verified: true, rating_avg: 4.8, rating_count: 5, jobs_completed: 12, phone_number: "+2348031110030" },
  offer_expires_at: "2026-10-15T09:00:00Z",
  scheduled_for: "2026-10-16T13:00:00Z",
  started_at: null,
  completed_at: null,
  completion_note: "",
  ...o,
});

beforeEach(async () => {
  jest.clearAllMocks();
  await tokens.set("access-1", "refresh-1");
});

describe("repairs: tenant", () => {
  it("lists my requests and offers Report a problem when I have a home", async () => {
    mockFetch((c) =>
      c.url.includes("/me/tickets/") ? json(200, page([ticket()])) : c.url.includes("/me/leases/") ? json(200, [lease]) : undefined,
    );
    renderWithClient(<RepairsHome />);
    expect(await screen.findByText("Kitchen tap leaking")).toBeTruthy();
    expect(screen.getByText("Waiting for landlord")).toBeTruthy();
    expect(screen.getByText("Urgent")).toBeTruthy();
    fireEvent.press(await screen.findByRole("button", { name: "Report a problem" }));
    expect(router.push).toHaveBeenCalledWith("/repairs/new");
  });

  it("reports a problem with a shrunk photo, sending an Idempotency-Key, then opens it", async () => {
    const calls = mockFetch((c) => {
      if (c.url.includes("/me/leases/")) return json(200, [lease]);
      if (c.url.endsWith("/api/v1/me/tickets/") && c.method === "POST") return json(201, ticket());
      if (c.url.endsWith("/me/tickets/t1/photos/")) return json(201, { id: "p1", stage: "report", url: "https://x/f/1/", created_at: "" });
      return undefined;
    });
    renderWithClient(<ReportRepair />);
    fireEvent.press(await screen.findByRole("button", { name: "Send to my landlord" }));
    expect(await screen.findByText("Choose what needs fixing.")).toBeTruthy();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);

    fireEvent.press(screen.getByRole("radio", { name: "Plumbing" }));
    fireEvent.press(screen.getByRole("radio", { name: "Urgent" }));
    fireEvent.changeText(screen.getByLabelText("In a few words"), "Kitchen tap leaking");
    fireEvent.changeText(screen.getByLabelText("What's wrong?"), "Drips all night long.");
    fireEvent.press(screen.getByRole("button", { name: "Take a photo" }));
    expect(await screen.findByRole("button", { name: "Remove photo 1" })).toBeTruthy();
    const append = jest.spyOn(FormData.prototype, "append");
    fireEvent.press(screen.getByRole("button", { name: "Send to my landlord" }));

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith({ pathname: "/repairs/[id]", params: { id: "t1" } }));
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/me/tickets/"))!;
    expect(post.body).toEqual({
      lease: "lease-1",
      category: "plumbing",
      priority: "urgent",
      title: "Kitchen tap leaking",
      description: "Drips all night long.",
      access_notes: "",
    });
    expect(post.headers["Idempotency-Key"]).toMatch(/^ticket/);
    const upload = calls.find((c) => c.url.endsWith("/photos/"))!;
    expect(upload.raw).toBeInstanceOf(FormData);
    expect(upload.headers["Content-Type"]).toBeUndefined(); // multipart boundary set by fetch
    // React Native's FormData takes {uri, name, type}; Jest's Node FormData would stringify it, so check the call.
    expect(append).toHaveBeenCalledWith("image", { uri: "file:///small.jpg", name: "photo.jpg", type: "image/jpeg" });
  });

  it("keeps the request when a photo fails, and says so", async () => {
    mockFetch((c) => {
      if (c.url.includes("/me/leases/")) return json(200, [lease]);
      if (c.url.endsWith("/api/v1/me/tickets/")) return json(201, ticket());
      if (c.url.endsWith("/photos/")) return json(400, { error: { code: "validation_error", message: "bad", details: {} } });
      return undefined;
    });
    renderWithClient(<ReportRepair />);
    fireEvent.press(await screen.findByRole("radio", { name: "Plumbing" }));
    fireEvent.changeText(screen.getByLabelText("In a few words"), "Kitchen tap leaking");
    fireEvent.changeText(screen.getByLabelText("What's wrong?"), "Drips all night long.");
    fireEvent.press(screen.getByRole("button", { name: "Choose from gallery" }));
    await screen.findByRole("button", { name: "Remove photo 1" });
    fireEvent.press(screen.getByRole("button", { name: "Send to my landlord" }));
    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith({ pathname: "/repairs/[id]", params: { id: "t1", photosFailed: "1" } }),
    );
  });

  it("emergency: tells me to call 112 first", async () => {
    mockFetch((c) => (c.url.includes("/me/leases/") ? json(200, [lease]) : undefined));
    const open = jest.spyOn(Linking, "openURL").mockResolvedValue(true);
    renderWithClient(<ReportRepair />);
    fireEvent.press(await screen.findByRole("radio", { name: "Emergency" }));
    expect(screen.getByText(/get safe and call 112 now/)).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Call 112" }));
    expect(open).toHaveBeenCalledWith("tel:112");
  });

  it("explains a denied camera permission", async () => {
    mockFetch((c) => (c.url.includes("/me/leases/") ? json(200, [lease]) : undefined));
    jest.mocked(ImagePicker.requestCameraPermissionsAsync).mockResolvedValueOnce({ granted: false } as never);
    renderWithClient(<ReportRepair />);
    fireEvent.press(await screen.findByRole("button", { name: "Take a photo" }));
    expect(await screen.findByText(/needs permission to use your camera/)).toBeTruthy();
  });

  it("detail: shows my Verified artisan, then I confirm and rate", async () => {
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: "t1" });
    let state: Record<string, unknown> = ticket({ status: "done", job: kunleJob({ status: "completed", completion_note: "Replaced washer" }), can: ["confirm", "reopen", "comment", "photo"] });
    const calls = mockFetch((c) => {
      if (c.url.endsWith("/me/tickets/t1/") && c.method === "GET") return json(200, state);
      if (c.url.endsWith("/confirm/")) {
        state = { ...state, status: "confirmed", can: ["rate"] };
        return json(200, state);
      }
      if (c.url.endsWith("/rate/")) {
        state = { ...state, rating: { score: 4, comment: "" }, can: [] };
        return json(200, state);
      }
      if (c.url.includes("/me/tickets/")) return json(200, page([]));
      return undefined;
    });
    renderWithClient(<RepairDetail />);
    expect(await screen.findByText("Kunle Plumbing Works")).toBeTruthy();
    expect(screen.getByLabelText("Verified")).toBeTruthy();
    expect(screen.getByText(/4\.8 from 5 ratings · 12 jobs done/)).toBeTruthy();
    expect(screen.getByText("Replaced washer")).toBeTruthy();
    expect(screen.getByText(/doesn't take payment/)).toBeTruthy();

    fireEvent.press(screen.getByRole("button", { name: "Yes, it's fixed" }));
    expect(await screen.findByText("Rate the artisan")).toBeTruthy();
    const send = screen.getByRole("button", { name: "Send rating" });
    expect(send.props.accessibilityState.disabled).toBe(true);
    fireEvent.press(screen.getByRole("radio", { name: "4 stars" }));
    fireEvent.press(send);
    expect(await screen.findByText("Your rating: 4 out of 5")).toBeTruthy();
    expect(calls.find((c) => c.url.endsWith("/rate/"))!.body).toEqual({ score: 4, comment: "" });
  });

  it("detail: 'not fixed' needs a note and goes back to the artisan", async () => {
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: "t1" });
    const calls = mockFetch((c) => {
      if (c.url.endsWith("/reopen/")) return json(200, ticket({ status: "assigned", job: kunleJob(), can: ["comment", "photo"] }));
      if (c.url.endsWith("/me/tickets/t1/")) return json(200, ticket({ status: "done", job: kunleJob({ status: "completed" }), can: ["confirm", "reopen"] }));
      if (c.url.includes("/me/tickets/")) return json(200, page([]));
      return undefined;
    });
    renderWithClient(<RepairDetail />);
    fireEvent.press(await screen.findByRole("button", { name: "No, it's not fixed" }));
    const send = screen.getByRole("button", { name: "Send to the artisan" });
    expect(send.props.accessibilityState.disabled).toBe(true);
    fireEvent.changeText(screen.getByLabelText("What's still wrong?"), "Still dripping");
    fireEvent.press(send);
    await waitFor(() => expect(calls.find((c) => c.url.endsWith("/reopen/"))!.body).toEqual({ note: "Still dripping" }));
  });

  it("detail: calls the artisan only once they've accepted (phone shown)", async () => {
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: "t1" });
    const open = jest.spyOn(Linking, "openURL").mockResolvedValue(true);
    mockFetch((c) => (c.url.endsWith("/me/tickets/t1/") ? json(200, ticket({ status: "assigned", job: kunleJob(), can: ["comment"] })) : undefined));
    renderWithClient(<RepairDetail />);
    fireEvent.press(await screen.findByRole("button", { name: "Call Kunle Plumbing Works" }));
    expect(open).toHaveBeenCalledWith("tel:+2348031110030");
  });
});

const artisan = (o: Record<string, unknown> = {}) => ({
  id: "a1",
  display_name: "Musa Plumbing Works",
  trades: ["plumbing"],
  service_areas: ["Lekki"],
  address: "4 Ado Road",
  city: "Lagos",
  state: "Lagos",
  bio: "",
  years_experience: 8,
  is_available: true,
  status: "pending",
  status_reason: "",
  is_verified: false,
  verified_at: null,
  rating_avg: null,
  rating_count: 0,
  jobs_completed: 0,
  checks: [
    { kind: "address", status: "pending", note: "", id_type: "", id_number_last4: "", attempts: 0 },
    { kind: "id", status: "not_started", note: "", id_type: "", id_number_last4: "", attempts: 0 },
    { kind: "phone", status: "passed", note: "", id_type: "", id_number_last4: "", attempts: 0 },
  ],
  vouchers: [],
  requirements: { id: false, phone: true, address: false, guarantors: 0, guarantors_needed: 2, references: 0, references_needed: 1, complete: false },
  ...o,
});

describe("work: artisans", () => {
  it("not signed up yet: explains and offers Sign up", async () => {
    mockFetch((c) => (c.url.endsWith("/artisans/me/") ? json(404, { error: { code: "not_artisan", message: "x", details: {} } }) : undefined));
    renderWithClient(<WorkHome />);
    expect(await screen.findByText("Get repair jobs from landlords")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Sign up" }));
    expect(router.push).toHaveBeenCalledWith("/work/apply");
  });

  it("signs up with several trades and consent", async () => {
    const calls = mockFetch((c) => (c.url.endsWith("/artisans/apply/") ? json(201, artisan()) : undefined));
    renderWithClient(<ApplyAsArtisan />);
    fireEvent.changeText(screen.getByLabelText("Your name or business name"), "Musa Plumbing Works");
    fireEvent.press(screen.getByRole("checkbox", { name: "Plumbing" }));
    fireEvent.press(screen.getByRole("checkbox", { name: "Tiling and masonry" }));
    fireEvent.changeText(screen.getByLabelText("Areas you work in"), "Lekki, Ajah ,");
    fireEvent.changeText(screen.getByLabelText("Your home or workshop address"), "4 Ado Road");
    fireEvent.press(screen.getByRole("button", { name: "Sign up" }));
    expect(await screen.findByText("Please agree to the checks to continue.")).toBeTruthy();
    expect(calls).toHaveLength(0);
    fireEvent.press(screen.getByRole("checkbox", { name: /I agree that Homesika may check my ID/ }));
    fireEvent.press(screen.getByRole("button", { name: "Sign up" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/work"));
    expect(calls[0]!.body).toMatchObject({
      display_name: "Musa Plumbing Works",
      trades: ["plumbing", "tiling"],
      service_areas: ["Lekki", "Ajah"],
      address: "4 Ado Road",
      consent: true,
    });
  });

  it("hub: shows the checklist, toggles availability and lists a new job", async () => {
    const calls = mockFetch((c) => {
      if (c.url.endsWith("/artisans/me/") && c.method === "PATCH") return json(200, artisan({ is_available: false }));
      if (c.url.endsWith("/artisans/me/")) return json(200, artisan());
      if (c.url.includes("/artisans/me/jobs/?status=active"))
        return json(200, page([{ id: "j1", status: "offered", organization: "Obi Properties", scheduled_for: null, location: { area: "Lekki", state: "Lagos" }, ticket: { title: "Kitchen tap leaking", priority: "urgent" } }]));
      return undefined;
    });
    renderWithClient(<WorkHome />);
    expect(await screen.findByText("Musa Plumbing Works")).toBeTruthy();
    expect(screen.getByLabelText("ID check, To do")).toBeTruthy();
    expect(screen.getByLabelText("Phone number, Done")).toBeTruthy();
    expect(screen.getByLabelText("Guarantors (0 of 2), To do")).toBeTruthy();
    expect(await screen.findByText("Kitchen tap leaking")).toBeTruthy();
    fireEvent.press(screen.getByRole("checkbox", { name: "Taking new jobs" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ is_available: false }));
  });

  it("adds a guarantor with a normalised phone number", async () => {
    let profile = artisan();
    const calls = mockFetch((c) => {
      if (c.url.endsWith("/vouchers/") && c.method === "POST") {
        profile = artisan({ vouchers: [{ id: "v1", kind: "guarantor", full_name: "Uncle Sule", phone_number: "+2348061112222", relationship: "uncle", occupation: "", status: "pending", link_sent_at: "", sends: 1, responded_at: null }] });
        return json(201, profile.vouchers[0]);
      }
      if (c.url.endsWith("/artisans/me/")) return json(200, profile);
      return undefined;
    });
    renderWithClient(<People />);
    fireEvent.press(await screen.findByRole("button", { name: "Add a guarantor" }));
    fireEvent.changeText(screen.getByLabelText("Full name"), "Uncle Sule");
    fireEvent.changeText(screen.getByLabelText("Phone number"), "0806 111 2222");
    fireEvent.changeText(screen.getByLabelText("How do they know you?"), "uncle");
    fireEvent.changeText(screen.getByLabelText("Their address"), "2 Market Rd");
    fireEvent.press(screen.getByRole("button", { name: "Send them the link" }));
    expect(await screen.findByText("We've sent Uncle Sule an SMS")).toBeTruthy();
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({ kind: "guarantor", phone_number: "+2348061112222", address: "2 Market Rd" });
    expect(await screen.findByText("Waiting for them")).toBeTruthy();
  });

  it("ID check: sends type, number and the photo as multipart", async () => {
    const calls = mockFetch((c) => {
      if (c.url.endsWith("/verification/id/")) return json(200, artisan({ checks: [{ kind: "id", status: "pending", note: "", id_type: "nin", id_number_last4: "8901", attempts: 1 }] }));
      if (c.url.endsWith("/artisans/me/")) return json(200, artisan());
      return undefined;
    });
    renderWithClient(<IdCheck />);
    fireEvent.changeText(await screen.findByLabelText("ID number"), "12345678901");
    fireEvent.press(screen.getByRole("button", { name: "Take a photo of the ID" }));
    await screen.findByRole("button", { name: "Take it again" });
    const append = jest.spyOn(FormData.prototype, "append");
    fireEvent.press(screen.getByRole("button", { name: "Send for checking" }));
    expect(await screen.findByText("Sent. We'll tell you by SMS when it's checked.")).toBeTruthy();
    const form = calls.find((c) => c.url.endsWith("/verification/id/"))!.raw as FormData;
    expect([form.get("id_type"), form.get("id_number")]).toEqual(["nin", "12345678901"]);
    expect(append).toHaveBeenCalledWith("document", { uri: "file:///small.jpg", name: "photo.jpg", type: "image/jpeg" });
  });

  it("job: no address before accepting; accept to agree a time by phone, then finish with a note", async () => {
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: "j1" });
    const base = {
      id: "j1",
      organization: "Obi Properties",
      offer_note: "Bring tape",
      offer_expires_at: "2026-10-15T09:00:00Z",
      scheduled_for: null,
      started_at: null,
      completed_at: null,
      completion_note: "",
      confirmed_at: null,
      created_at: "2026-10-14T09:00:00Z",
      ticket: { id: "t1", reference: "R0000A01", status: "assigned", category: "plumbing", priority: "urgent", title: "Kitchen tap leaking", description: "Drips", access_notes: "", photos: [], events: [] },
      rating: null,
    };
    let job: Record<string, unknown> = { ...base, status: "offered", location: { area: "Lekki", state: "Lagos" }, contact: null, can: ["accept", "decline"] };
    const calls = mockFetch((c: Call) => {
      if (c.url.endsWith("/accept/")) {
        job = { ...base, status: "accepted", location: { area: "Lekki", state: "Lagos", address: "12 Allen Avenue", property: "Palm Court", unit: "Flat 2" }, contact: { name: "Ada", phone_number: "+2348012345678" }, can: ["schedule", "start", "complete", "comment", "photo"] };
        return json(200, job);
      }
      if (c.url.endsWith("/complete/")) {
        job = { ...job, status: "completed", can: ["comment"] };
        return json(200, job);
      }
      if (c.url.endsWith("/artisans/me/jobs/j1/")) return json(200, job);
      if (c.url.includes("/artisans/me/jobs/")) return json(200, page([]));
      return undefined;
    });
    renderWithClient(<JobDetail />);
    expect(await screen.findByText(/You'll see the address and the tenant's phone number after you accept/)).toBeTruthy();
    expect(screen.getByText("Note from the landlord: Bring tape")).toBeTruthy();
    fireEvent.press(screen.getByRole("radio", { name: "I'll call to agree a time" }));
    fireEvent.press(screen.getByRole("button", { name: "Accept the job" }));
    expect(await screen.findByText("12 Allen Avenue", { exact: false })).toBeTruthy();
    expect(calls.find((c) => c.url.endsWith("/accept/"))!.body).toEqual({ scheduled_for: null });
    expect(screen.getByRole("button", { name: "Call Ada" })).toBeTruthy();

    fireEvent.press(screen.getByRole("button", { name: "I've finished" }));
    fireEvent.changeText(screen.getByLabelText("What did you do?"), "Replaced the washer");
    await act(async () => {
      fireEvent.press(screen.getByRole("button", { name: "Mark as done" }));
    });
    expect(await screen.findByText("Done. The tenant will confirm.")).toBeTruthy();
    expect(calls.find((c) => c.url.endsWith("/complete/"))!.body).toEqual({ note: "Replaced the washer" });
  });

  it("only offers visit times still ahead", () => {
    const at = new Date(2026, 9, 15, 13, 50); // 1:50pm: 10am today has passed, 2pm is too soon
    expect(visitChoices(at).map((c) => `${c.day} ${c.part}`)).toEqual(["tomorrow morning", "tomorrow afternoon"]);
    const early = new Date(2026, 9, 15, 7, 0);
    expect(visitChoices(early)).toHaveLength(4);
  });
});

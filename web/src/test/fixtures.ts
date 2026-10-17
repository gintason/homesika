/** Sample API objects for Phase 2 screen tests (shapes from backend serializers). */
import type { ConversationDetail, Lead, Listing } from "../lib/types";

export const LISTING: Listing = {
  id: "l1",
  ref: "LST-AB12CD",
  unit: null,
  title: "2-bedroom flat in Yaba",
  description: "",
  whatsapp_caption: "",
  features: [],
  area: "Yaba",
  city: "Lagos",
  address: "4 Herbert Macaulay Way",
  bedrooms: 2,
  bathrooms: 2,
  rent_amount: "1500000.00",
  rent_period: "year",
  currency: "NGN",
  status: "draft",
  published_at: null,
  ai_generated: false,
  contact_phone: "+2348031234567",
  photos: [],
  lead_count: 0,
  created_at: "2026-10-01T09:00:00Z",
};

export const LEAD: Lead = {
  id: "ld1",
  listing: "l1",
  listing_title: "2-bedroom flat in Yaba",
  name: "Bisi Ade",
  phone_number: "+2348091112222",
  source: "web",
  stage: "new",
  message: "Is it still available?",
  notes: "",
  assigned_to: null,
  viewings: [],
  created_at: "2026-10-10T09:00:00Z",
};

export function conversation(overrides: Partial<ConversationDetail> = {}): ConversationDetail {
  return {
    id: "c1",
    channel: "whatsapp",
    status: "bot",
    language: "en",
    contact_name: "Tunde",
    contact_phone: "+2348035556666",
    open_escalation: null,
    last_message: null,
    last_inbound_at: "2026-10-16T09:00:00Z",
    last_message_at: "2026-10-16T09:00:00Z",
    can_reply_freely: true,
    handoff_by: null,
    messages: [
      {
        id: "m1",
        direction: "in",
        sender: "person",
        kind: "text",
        body: "My rent receipt is wrong",
        status: "received",
        error: "",
        sent_by_name: null,
        created_at: "2026-10-16T09:00:00Z",
      },
      {
        id: "m2",
        direction: "out",
        sender: "assistant",
        kind: "text",
        body: "I'll pass this to your landlord's team.",
        status: "sent",
        error: "",
        sent_by_name: null,
        created_at: "2026-10-16T09:00:05Z",
      },
    ],
    escalations: [
      { id: "e1", reason: "dispute", summary: "Disputes receipt amount", status: "open", assigned_to: null, resolved_at: null, created_at: "2026-10-16T09:00:05Z" },
    ],
    ...overrides,
  };
}

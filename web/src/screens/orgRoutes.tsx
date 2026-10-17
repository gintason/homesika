import { Navigate, Route } from "react-router";

import { Arrears } from "./charges/Arrears";
import { ConversationView } from "./inbox/ConversationView";
import { InboxList } from "./inbox/InboxList";
import { LeadsList } from "./leads/LeadsList";
import { ListingDetail } from "./listings/ListingDetail";
import { ListingForm } from "./listings/ListingForm";
import { ListingsList } from "./listings/ListingsList";
import { ChargesList } from "./charges/ChargesList";
import { Dashboard } from "./orgs/Dashboard";
import { ExpenseForm } from "./expenses/ExpenseForm";
import { ExpensesList } from "./expenses/ExpensesList";
import { LeaseDetail } from "./leases/LeaseDetail";
import { LeaseForm } from "./leases/LeaseForm";
import { LeasesList } from "./leases/LeasesList";
import { CreatePaymentLink } from "./links/CreatePaymentLink";
import { PaymentLinksList } from "./links/PaymentLinksList";
import { PaymentDetail } from "./payments/PaymentDetail";
import { PaymentsList } from "./payments/PaymentsList";
import { RecordPayment } from "./payments/RecordPayment";
import { PropertiesList } from "./properties/PropertiesList";
import { NewRepair } from "./repairs/NewRepair";
import { RepairDetail } from "./repairs/RepairDetail";
import { RepairsList } from "./repairs/RepairsList";
import { PropertyDetail } from "./properties/PropertyDetail";
import { PropertyForm } from "./properties/PropertyForm";
import { Statement } from "./reports/Statement";
import { HelpArticles } from "./settings/HelpArticles";
import { Settings } from "./settings/Settings";
import { TenantDetail } from "./tenants/TenantDetail";
import { TenantForm } from "./tenants/TenantForm";
import { TenantsList } from "./tenants/TenantsList";
import { ViewingsList } from "./viewings/ViewingsList";

/** Routes under /orgs/:orgId (rendered inside OrgLayout). */
export const orgRoutes = (
  <>
    <Route index element={<Navigate to="dashboard" replace />} />
    <Route path="dashboard" element={<Dashboard />} />
    <Route path="properties" element={<PropertiesList />} />
    <Route path="properties/new" element={<PropertyForm />} />
    <Route path="properties/:propertyId" element={<PropertyDetail />} />
    <Route path="properties/:propertyId/edit" element={<PropertyForm />} />
    <Route path="tenants" element={<TenantsList />} />
    <Route path="tenants/new" element={<TenantForm />} />
    <Route path="tenants/:tenantId" element={<TenantDetail />} />
    <Route path="tenants/:tenantId/edit" element={<TenantForm />} />
    <Route path="leases" element={<LeasesList />} />
    <Route path="leases/new" element={<LeaseForm />} />
    <Route path="leases/:leaseId" element={<LeaseDetail />} />
    <Route path="charges" element={<ChargesList />} />
    <Route path="arrears" element={<Arrears />} />
    <Route path="payments" element={<PaymentsList />} />
    <Route path="payments/new" element={<RecordPayment />} />
    <Route path="payments/:paymentId" element={<PaymentDetail />} />
    <Route path="payment-links" element={<PaymentLinksList />} />
    <Route path="payment-links/new" element={<CreatePaymentLink />} />
    <Route path="expenses" element={<ExpensesList />} />
    <Route path="expenses/new" element={<ExpenseForm />} />
    <Route path="expenses/:expenseId/edit" element={<ExpenseForm />} />
    <Route path="statement" element={<Statement />} />
    <Route path="settings" element={<Settings />} />
    <Route path="settings/help-articles" element={<HelpArticles />} />
    <Route path="listings" element={<ListingsList />} />
    <Route path="listings/new" element={<ListingForm />} />
    <Route path="listings/:listingId" element={<ListingDetail />} />
    <Route path="listings/:listingId/edit" element={<ListingForm />} />
    <Route path="leads" element={<LeadsList />} />
    <Route path="viewings" element={<ViewingsList />} />
    <Route path="inbox" element={<InboxList />} />
    <Route path="inbox/:conversationId" element={<ConversationView />} />
    <Route path="repairs" element={<RepairsList />} />
    <Route path="repairs/new" element={<NewRepair />} />
    <Route path="repairs/:ticketId" element={<RepairDetail />} />
  </>
);

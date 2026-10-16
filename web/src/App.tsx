import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router";

import { LoadingBlock, ToastProvider } from "./components";
import { MockCheckout } from "./screens/pay/MockCheckout";
import { PayDone } from "./screens/pay/PayDone";
import { PayPage } from "./screens/pay/PayPage";
import { PayReceipt } from "./screens/pay/PayReceipt";
import { ReceiptInfo } from "./screens/pay/ReceiptInfo";

// The staff dashboard (React Query, every screen) loads as a separate chunk, so tenants opening a pay
// link from an SMS on a cheap phone download only the small public pages.
const StaffApp = lazy(() => import("./StaffApp"));

export function FullPageLoading() {
  return (
    <div className="mx-auto max-w-md px-5 py-16">
      <LoadingBlock rows={3} />
    </div>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/pay/:reference" element={<PayPage />} />
      <Route path="/pay/:reference/done" element={<PayDone />} />
      <Route path="/pay/:reference/mock-checkout" element={<MockCheckout />} />
      <Route path="/pay/:reference/receipt" element={<PayReceipt />} />
      <Route path="/receipts/:token" element={<ReceiptInfo />} />
      <Route
        path="*"
        element={
          <Suspense fallback={<FullPageLoading />}>
            <StaffApp />
          </Suspense>
        }
      />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AppRoutes />
      </ToastProvider>
    </BrowserRouter>
  );
}

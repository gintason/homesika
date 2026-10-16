import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router";

import { Banner, LoadingBlock } from "./components";
import { strings } from "./i18n";
import { ApiError } from "./lib/api";
import { AuthProvider, useAuth } from "./lib/auth";
import { ForgotPin } from "./screens/auth/ForgotPin";
import { SignIn } from "./screens/auth/SignIn";
import { SignUp } from "./screens/auth/SignUp";
import { NotFound } from "./screens/NotFound";
import { CreateOrg } from "./screens/orgs/CreateOrg";
import { HomeRedirect } from "./screens/orgs/HomeRedirect";
import { OrgLayout } from "./screens/orgs/OrgLayout";
import { orgRoutes } from "./screens/orgRoutes";

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Retry network blips and 5xx with backoff; never retry 4xx (it won't change).
        retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
      },
    },
  });
}

function Centered({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-md px-5 py-16">{children}</div>;
}

function RequireAuth() {
  const { status, retry } = useAuth();
  const location = useLocation();
  if (status === "loading") {
    return (
      <Centered>
        <LoadingBlock rows={3} />
      </Centered>
    );
  }
  if (status === "error") {
    return (
      <Centered>
        <Banner tone="error" onRetry={retry}>
          {strings.errors.network}
        </Banner>
      </Centered>
    );
  }
  if (status === "signedOut") {
    return <Navigate to="/signin" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Outlet />;
}

function PublicOnly() {
  const { status } = useAuth();
  if (status === "signedIn") return <Navigate to="/" replace />;
  return <Outlet />;
}

export function StaffRoutes() {
  return (
    <Routes>
      <Route element={<PublicOnly />}>
        <Route path="/signin" element={<SignIn />} />
        <Route path="/signup" element={<SignUp />} />
        <Route path="/forgot-pin" element={<ForgotPin />} />
      </Route>
      <Route element={<RequireAuth />}>
        <Route path="/" element={<HomeRedirect />} />
        <Route path="/orgs/new" element={<CreateOrg />} />
        <Route path="/orgs/:orgId" element={<OrgLayout />}>
          {orgRoutes}
        </Route>
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

export default function StaffApp() {
  const [client] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>
        <StaffRoutes />
      </AuthProvider>
    </QueryClientProvider>
  );
}

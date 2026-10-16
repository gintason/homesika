import { useQuery } from "@tanstack/react-query";
import { createContext, useContext } from "react";

import { api } from "./api";
import { can as roleCan, type Capability } from "./permissions";
import { storage } from "./storage";
import type { Organization, Role } from "./types";

export interface OrgContextValue {
  org: Organization;
  orgs: Organization[];
  role: Role | null;
  can: (capability: Capability) => boolean;
  /** "/orgs/{id}" prefix for links inside this organization. */
  base: string;
}

export const OrgContext = createContext<OrgContextValue | null>(null);

export function useOrg(): OrgContextValue {
  const ctx = useContext(OrgContext);
  if (!ctx) throw new Error("useOrg must be used inside an organization route");
  return ctx;
}

export function makeOrgContext(org: Organization, orgs: Organization[]): OrgContextValue {
  return {
    org,
    orgs,
    role: org.my_role,
    can: (c) => roleCan(org.my_role, c),
    base: `/orgs/${org.id}`,
  };
}

export function useMyOrgs() {
  return useQuery({ queryKey: ["orgs"], queryFn: () => api<Organization[]>("/orgs/") });
}

const LAST_ORG = "hs.last_org";
export const lastOrg = {
  get: () => storage.get(LAST_ORG),
  set: (id: string) => storage.set(LAST_ORG, id),
};

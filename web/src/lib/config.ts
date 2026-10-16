/** Base URL of the Homesika API (no trailing slash). Set VITE_API_URL at build time. */
export const API_URL: string = String(import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

export const API_PREFIX = "/api/v1";

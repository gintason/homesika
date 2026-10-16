import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import { ReceiptInfo } from "./ReceiptInfo";

describe("ReceiptInfo", () => {
  it("links to the public receipt PDF for the token", () => {
    render(
      <MemoryRouter initialEntries={["/receipts/abc123TOKENxyz"]}>
        <Routes>
          <Route path="/receipts/:token" element={<ReceiptInfo />} />
        </Routes>
      </MemoryRouter>,
    );
    const link = screen.getByRole("link", { name: "Open receipt (PDF)" });
    expect(link.getAttribute("href")).toMatch(/\/api\/v1\/receipts\/abc123TOKENxyz\/$/);
  });
});

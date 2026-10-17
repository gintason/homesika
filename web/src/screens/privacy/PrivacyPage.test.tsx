import { render, screen } from "@testing-library/react";

import { PrivacyPage } from "./PrivacyPage";

describe("Privacy notice", () => {
  it("names the AI provider and the right to a human review", () => {
    render(<PrivacyPage />);
    expect(screen.getByRole("heading", { name: "Privacy notice" })).toBeInTheDocument();
    expect(screen.getByText(/Anthropic \(Claude AI/)).toBeInTheDocument();
    expect(screen.getByText(/Smile ID \(NIN verification\)/)).toBeInTheDocument();
    expect(screen.getByText(/ask for a person at Homesika to review it/)).toBeInTheDocument();
    expect(screen.getByText(/deleted 90 days after the check passes/)).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import JoinPage from "./JoinPage";

describe("Invite link page", () => {
  it("shows the code and links to the app and web sign-up with it", () => {
    render(
      <MemoryRouter initialEntries={["/join?code=k7pm-2qx"]}>
        <JoinPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("K7PM2QX")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in the Homesika app" })).toHaveAttribute("href", "homesika://register?code=K7PM2QX");
    expect(screen.getByRole("link", { name: "Sign up on the web instead" })).toHaveAttribute("href", "/signup?code=K7PM2QX");
  });

  it("explains a link without a code", () => {
    render(
      <MemoryRouter initialEntries={["/join"]}>
        <JoinPage />
      </MemoryRouter>,
    );
    expect(screen.getByText(/has no code/)).toBeInTheDocument();
  });
});

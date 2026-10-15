import { render, screen } from "@testing-library/react";

import App from "./App";
import { tokens } from "./theme/tokens";

describe("App shell", () => {
  it("shows the brand and the palette from the design tokens", () => {
    render(<App />);
    expect(screen.getByText("Homesika")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Brand palette" })).toBeInTheDocument();
    expect(screen.getByText(tokens.color.primary[800])).toBeInTheDocument();
    expect(screen.getByText(tokens.color.emergency.base)).toBeInTheDocument();
  });
});

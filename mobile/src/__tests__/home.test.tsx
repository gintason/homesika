import { render, screen } from "@testing-library/react-native";

import Home from "@/app/index";
import tokens from "@/theme/tokens";

jest.mock("react-native-safe-area-context", () => {
  const { View } = jest.requireActual("react-native");
  return { SafeAreaView: View };
});

describe("Home shell", () => {
  it("renders the brand", () => {
    render(<Home />);
    expect(screen.getByText("Homesika")).toBeTruthy();
    expect(screen.getByText("Phase 0 · foundations")).toBeTruthy();
  });

  it("reads the shared design tokens", () => {
    expect(tokens.color.primary[800]).toBe("#0B2B63");
    expect(tokens.size.panicButton).toBeGreaterThanOrEqual(tokens.size.touchTarget * 2);
  });
});

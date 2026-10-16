import { act, fireEvent, render, screen } from "@testing-library/react-native";
import { useState } from "react";

import { OtpInput } from "@/components/OtpInput";
import { PinPad } from "@/components/PinPad";

describe("PinPad", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("submits exactly once when the 6th digit is entered, and supports delete", () => {
    const onComplete = jest.fn();
    render(<PinPad title="Enter your PIN" onComplete={onComplete} />);
    for (const d of ["7", "3", "9"]) fireEvent.press(screen.getByLabelText(d));
    fireEvent.press(screen.getByLabelText("Delete"));
    for (const d of ["9", "1", "5", "2"]) fireEvent.press(screen.getByLabelText(d));
    act(() => jest.runAllTimers());
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith("739152");

    fireEvent.press(screen.getByLabelText("1")); // pad is full: extra presses are ignored
    act(() => jest.runAllTimers());
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("announces progress and ignores input while busy", () => {
    const onComplete = jest.fn();
    render(<PinPad title="Enter your PIN" busy onComplete={onComplete} />);
    for (const d of ["1", "2", "3", "4", "5", "6"]) fireEvent.press(screen.getByLabelText(d));
    act(() => jest.runAllTimers());
    expect(onComplete).not.toHaveBeenCalled();
    expect(screen.getByLabelText("0 of 6 digits entered")).toBeTruthy();
  });

  it("shows the error and the optional fingerprint key", () => {
    const onBio = jest.fn();
    render(
      <PinPad
        title="Welcome back, Ada"
        errorSignal={1}
        errorMessage="Incorrect PIN. Attempts left: 2."
        accessory={{ icon: "finger-print", label: "Unlock with fingerprint or face", onPress: onBio }}
        onComplete={jest.fn()}
      />,
    );
    expect(screen.getByText("Incorrect PIN. Attempts left: 2.")).toBeTruthy();
    fireEvent.press(screen.getByLabelText("Unlock with fingerprint or face"));
    expect(onBio).toHaveBeenCalledTimes(1);
  });

  it("uses big touch targets (≥ 48)", () => {
    render(<PinPad title="PIN" onComplete={jest.fn()} />);
    expect(screen.getByLabelText("5").props.className ?? "").toEqual(expect.stringContaining("h-16"));
  });
});

function Otp({ onComplete }: { onComplete: (c: string) => void }) {
  const [code, setCode] = useState("");
  return <OtpInput value={code} onChange={setCode} onComplete={onComplete} />;
}

describe("OtpInput", () => {
  it("keeps digits only, caps at 6 and completes once (SMS autofill pastes all six)", () => {
    const onComplete = jest.fn();
    render(<Otp onComplete={onComplete} />);
    const input = screen.getByTestId("otp-input");
    fireEvent.changeText(input, "12a");
    expect(screen.getByLabelText("6-digit code, 2 of 6 entered", { exact: false })).toBeTruthy();
    expect(onComplete).not.toHaveBeenCalled();
    fireEvent.changeText(input, "123456789");
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith("123456");
    expect(screen.getByText("6", { includeHiddenElements: true })).toBeTruthy();
  });
});

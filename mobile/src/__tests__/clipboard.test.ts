import * as Clipboard from "expo-clipboard";
import { Share } from "react-native";

import { copyText } from "@/lib/clipboard";

jest.mock("expo-clipboard", () => ({ setStringAsync: jest.fn() }));

const setString = Clipboard.setStringAsync as jest.Mock;

describe("copyText", () => {
  beforeEach(() => {
    setString.mockReset();
    jest.spyOn(Share, "share").mockReset();
  });

  it("copies with expo-clipboard", async () => {
    setString.mockResolvedValue(true);
    await expect(copyText("1234-5678")).resolves.toBe("copied");
    expect(setString).toHaveBeenCalledWith("1234-5678");
    expect(Share.share).not.toHaveBeenCalled();
  });

  it("falls back to the share sheet when copying fails", async () => {
    setString.mockRejectedValue(new Error("no clipboard"));
    jest.spyOn(Share, "share").mockResolvedValue({ action: "sharedAction" });
    await expect(copyText("1234-5678")).resolves.toBe("shared");
    expect(Share.share).toHaveBeenCalledWith({ message: "1234-5678" });
  });

  it("reports failure when neither works", async () => {
    setString.mockResolvedValue(false);
    jest.spyOn(Share, "share").mockRejectedValue(new Error("no share"));
    await expect(copyText("1234-5678")).resolves.toBe("failed");
  });
});

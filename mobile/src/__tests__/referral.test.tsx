import { fireEvent, screen, waitFor } from "@testing-library/react-native";
import { router, useLocalSearchParams } from "expo-router";
import { Share } from "react-native";

import Register from "@/app/(auth)/register";
import Invite from "@/app/(app)/invite";
import { json, mockFetch, renderWithClient } from "@/testing/utils";

const summary = (o: Record<string, unknown> = {}) => ({
  code: "K7PM2QX",
  share_url: "https://app.homesika.ng/join?code=K7PM2QX",
  share_message: "Join me on Homesika… K7PM2QX",
  waivers_available: 3,
  waivers_expire_at: "2027-04-15T09:00:00Z",
  invited: 2,
  qualified: 1,
  can_redeem: false,
  enabled: true,
  ...o,
});

beforeEach(() => jest.clearAllMocks());

describe("referrals", () => {
  it("shows my code and free fees, and shares the message", async () => {
    mockFetch((c) => (c.url.endsWith("/me/referral/") ? json(200, summary()) : undefined));
    const share = jest.spyOn(Share, "share").mockResolvedValue({ action: "sharedAction" });
    renderWithClient(<Invite />);
    expect(await screen.findByText("K7PM2QX")).toBeTruthy();
    expect(screen.getByText("You have 3 free service fees")).toBeTruthy();
    expect(screen.getByText("2 invited · 1 bought something")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Share my code" }));
    expect(share).toHaveBeenCalledWith({ message: "Join me on Homesika… K7PM2QX" });
    expect(screen.queryByText("Got a friend's code?")).toBeNull();
  });

  it("a new account can still enter a friend's code", async () => {
    const calls = mockFetch((c) => {
      if (c.url.endsWith("/me/referral/redeem/"))
        return (c.body as { code: string }).code === "BADCODE"
          ? json(400, { error: { code: "validation_error", message: "Invalid", details: { code: ["We don't recognise this code."] } } })
          : json(200, summary({ can_redeem: false, waivers_available: 3 }));
      if (c.url.endsWith("/me/referral/")) return json(200, summary({ can_redeem: true, waivers_available: 0 }));
      return undefined;
    });
    renderWithClient(<Invite />);
    fireEvent.changeText(await screen.findByLabelText("Friend's code"), "bad-code");
    fireEvent.press(screen.getByRole("button", { name: "Use code" }));
    expect(await screen.findByText("We don't recognise this code.")).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText("Friend's code"), "ab12cd3");
    fireEvent.press(screen.getByRole("button", { name: "Use code" }));
    expect(await screen.findByText("Done. Your next service fees are free.")).toBeTruthy();
    expect(calls.at(-1)!.body).toEqual({ code: "AB12CD3" });
  });

  it("sign-up sends the code from an invite link", async () => {
    (useLocalSearchParams as jest.Mock).mockReturnValue({ code: "k7pm2qx" });
    const calls = mockFetch((c) =>
      c.url.endsWith("/auth/register/") ? json(201, { challenge_id: "ch1", channel: "sms", destination: "+234•••", resend_in: 60 }) : undefined,
    );
    renderWithClient(<Register />);
    expect(screen.getByLabelText("Friend's code (optional)").props.value).toBe("K7PM2QX");
    fireEvent.changeText(screen.getByLabelText("First name"), "Chidi");
    fireEvent.changeText(screen.getByLabelText("Last name"), "Okafor");
    fireEvent.changeText(screen.getByLabelText("Phone number"), "08031110001");
    fireEvent.press(screen.getByRole("checkbox"));
    fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/verify"));
    expect(calls[0]!.body).toMatchObject({ referral_code: "K7PM2QX", phone_number: "+2348031110001" });
  });
});

import { act, screen } from "@testing-library/react-native";

import { tenantApi } from "@/api";
import Home from "@/app/(app)/(tabs)/index";
import i18n from "@/i18n";
import en from "@/i18n/locales/en.json";
import pcm from "@/i18n/locales/pcm.json";
import { useSession } from "@/store/session";
import { json, mockFetch, page, renderWithClient } from "@/testing/utils";

function keys(obj: object, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    k.startsWith("_") ? [] : typeof v === "object" && v ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`],
  );
}

afterEach(async () => {
  await act(() => useSession.getState().setLanguage("en"));
});

describe("i18n", () => {
  it("Pidgin has every English key (and nothing extra)", () => {
    expect(keys(pcm).sort()).toEqual(keys(en).sort());
    expect((pcm as { _review?: string })._review).toMatch(/NATIVE-SPEAKER REVIEW/);
  });

  it("switching to Pidgin re-renders the screen in Pidgin", async () => {
    useSession.setState({ status: "ready", profile: { firstName: "Ada", lastName: "Obi", phone: "+2348012345678" } });
    mockFetch((c) => (c.url.includes("/leases/") ? json(200, []) : json(200, page([]))));
    renderWithClient(<Home />);
    expect(await screen.findByText("Nothing to show yet")).toBeTruthy();
    expect(screen.getByText("Hello, Ada")).toBeTruthy();

    await act(() => useSession.getState().setLanguage("pcm"));
    expect(i18n.language).toBe("pcm");
    expect(screen.getByText("How far, Ada")).toBeTruthy();
    expect(screen.getByText("Nothing dey here yet")).toBeTruthy();
    expect(screen.getByText(/Tell your landlord make e add your number \+234 801 234 5678/)).toBeTruthy();
  });

  it("sends the chosen language to the API", async () => {
    await act(() => useSession.getState().setLanguage("pcm"));
    const calls = mockFetch(() => json(200, []));
    await tenantApi.leases();
    expect(calls[0]!.headers["Accept-Language"]).toBe("pcm");
  });
});

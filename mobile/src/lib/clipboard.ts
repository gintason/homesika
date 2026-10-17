import { Clipboard, Share } from "react-native";

/**
 * Copy text (an electricity token). Uses React Native's built-in clipboard module (still shipped in
 * RN 0.86, deprecated) so no new dependency is needed; if it's unavailable, falls back to the share
 * sheet, which also offers "Copy". Returns how it was handled.
 * TODO: switch to expo-clipboard when it's added to the app.
 */
export async function copyText(text: string): Promise<"copied" | "shared" | "failed"> {
  try {
    Clipboard.setString(text);
    return "copied";
  } catch {
    try {
      await Share.share({ message: text });
      return "shared";
    } catch {
      return "failed";
    }
  }
}

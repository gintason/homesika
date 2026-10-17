import * as Clipboard from "expo-clipboard";
import { Share } from "react-native";

/**
 * Copy text (an electricity token) with expo-clipboard. If copying fails, falls back to the share
 * sheet, which also offers "Copy". Returns how it was handled.
 */
export async function copyText(text: string): Promise<"copied" | "shared" | "failed"> {
  try {
    if (await Clipboard.setStringAsync(text)) return "copied";
  } catch {
    // fall through to the share sheet
  }
  try {
    await Share.share({ message: text });
    return "shared";
  } catch {
    return "failed";
  }
}

import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import * as ImagePicker from "expo-image-picker";

/** What we upload: React Native's FormData file shape. */
export type PhotoFile = { uri: string; name: string; type: string };

export type PickResult = { kind: "picked"; photo: PhotoFile } | { kind: "cancelled" } | { kind: "denied" };

/** Long side in pixels. Plenty for a repair or an ID, and ~200-400 KB, which matters on weak networks. */
const MAX_SIDE = 1600;

/**
 * Take a photo or choose one, then shrink it and save it as JPEG before upload. The server re-encodes it
 * again and drops the location data; we never read or send the photo's location.
 */
export async function pickPhoto(source: "camera" | "library"): Promise<PickResult> {
  const perm =
    source === "camera" ? await ImagePicker.requestCameraPermissionsAsync() : await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!perm.granted) return { kind: "denied" };
  const options: ImagePicker.ImagePickerOptions = { mediaTypes: ["images"], quality: 0.8, exif: false };
  const res = source === "camera" ? await ImagePicker.launchCameraAsync(options) : await ImagePicker.launchImageLibraryAsync(options);
  const asset = res.canceled ? undefined : res.assets?.[0];
  if (!asset) return { kind: "cancelled" };
  let uri = asset.uri;
  try {
    const ctx = ImageManipulator.manipulate(uri);
    if ((asset.width ?? 0) >= (asset.height ?? 0)) {
      if ((asset.width ?? 0) > MAX_SIDE) ctx.resize({ width: MAX_SIDE });
    } else if ((asset.height ?? 0) > MAX_SIDE) {
      ctx.resize({ height: MAX_SIDE });
    }
    const image = await ctx.renderAsync();
    uri = (await image.saveAsync({ format: SaveFormat.JPEG, compress: 0.7 })).uri;
  } catch {
    // Shrinking failed (rare): upload the original; the server still checks the size.
  }
  return { kind: "picked", photo: { uri, name: "photo.jpg", type: "image/jpeg" } };
}

/** FormData with one photo field, for POST …/photos/ and the ID check. */
export function photoForm(photo: PhotoFile, field = "image", extra: Record<string, string> = {}): FormData {
  const form = new FormData();
  for (const [k, v] of Object.entries(extra)) form.append(k, v);
  // React Native's FormData takes {uri, name, type} for files.
  form.append(field, photo as unknown as Blob);
  return form;
}

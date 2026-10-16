import * as LocalAuthentication from "expo-local-authentication";

/** True when the phone has fingerprint / face hardware and the user has enrolled. */
export async function biometricsAvailable(): Promise<boolean> {
  try {
    return (await LocalAuthentication.hasHardwareAsync()) && (await LocalAuthentication.isEnrolledAsync());
  } catch {
    return false;
  }
}

export async function hasFaceUnlock(): Promise<boolean> {
  try {
    const types = await LocalAuthentication.supportedAuthenticationTypesAsync();
    return types.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION);
  } catch {
    return false;
  }
}

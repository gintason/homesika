/* global jest */
// Native modules aren't available under Jest; stub the ones our code touches.

// Reanimated 4 / worklets: use the libraries' own Jest mocks (no UI thread under Jest).
jest.mock("react-native-worklets", () => require("react-native-worklets/lib/module/mock"));
jest.mock("react-native-reanimated", () => ({
  ...require("react-native-reanimated/mock"),
  useReducedMotion: () => false, // missing from the library mock
}));

jest.mock("react-native-safe-area-context", () => require("react-native-safe-area-context/jest/mock").default);

// In-memory secure store (tests can reset it with `require("expo-secure-store").__reset()`).
jest.mock("expo-secure-store", () => {
  const store = new Map();
  return {
    getItemAsync: jest.fn(async (k) => (store.has(k) ? store.get(k) : null)),
    setItemAsync: jest.fn(async (k, v) => void store.set(k, v)),
    deleteItemAsync: jest.fn(async (k) => void store.delete(k)),
    WHEN_UNLOCKED_THIS_DEVICE_ONLY: 1,
    __reset: () => store.clear(),
  };
});

jest.mock("expo-localization", () => ({ getLocales: () => [{ languageCode: "en" }] }));

jest.mock("expo-crypto", () => ({
  randomUUID: () => {
    const hex = Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  },
}));

jest.mock("expo-local-authentication", () => ({
  hasHardwareAsync: jest.fn(async () => false),
  isEnrolledAsync: jest.fn(async () => false),
  supportedAuthenticationTypesAsync: jest.fn(async () => []),
  AuthenticationType: { FINGERPRINT: 1, FACIAL_RECOGNITION: 2, IRIS: 3 },
}));

jest.mock("expo-web-browser", () => ({
  openBrowserAsync: jest.fn(async () => ({ type: "dismiss" })),
  dismissBrowser: jest.fn(async () => ({ type: "dismiss" })),
}));

jest.mock("expo-file-system", () => {
  class File {
    constructor(...parts) {
      this.uri = parts.map((p) => (typeof p === "string" ? p : p.uri)).join("/");
    }
  }
  File.downloadFileAsync = jest.fn(async (_url, dest) => dest);
  return { File, Directory: class {}, Paths: { cache: { uri: "file:///cache" }, document: { uri: "file:///docs" } } };
});

jest.mock("expo-sharing", () => ({
  isAvailableAsync: jest.fn(async () => true),
  shareAsync: jest.fn(async () => {}),
}));

jest.mock("@react-native-community/netinfo", () => require("@react-native-community/netinfo/jest/netinfo-mock.js"));

// Camera / gallery: tests set what the picker "returns" with mockResolvedValueOnce.
jest.mock("expo-image-picker", () => ({
  requestCameraPermissionsAsync: jest.fn(async () => ({ granted: true })),
  requestMediaLibraryPermissionsAsync: jest.fn(async () => ({ granted: true })),
  launchCameraAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///camera.jpg", width: 4000, height: 3000 }] })),
  launchImageLibraryAsync: jest.fn(async () => ({ canceled: false, assets: [{ uri: "file:///gallery.jpg", width: 800, height: 600 }] })),
}));

jest.mock("expo-image-manipulator", () => {
  const ctx = {
    resize: jest.fn(() => ctx),
    renderAsync: jest.fn(async () => ({ saveAsync: jest.fn(async () => ({ uri: "file:///small.jpg", width: 1600, height: 1200 })) })),
  };
  return { ImageManipulator: { manipulate: jest.fn(() => ctx) }, SaveFormat: { JPEG: "jpeg", PNG: "png" }, __ctx: ctx };
});

// Icons render nothing under Jest (avoids font loading); the accessible text lives elsewhere.
jest.mock("@expo/vector-icons", () => ({ Ionicons: () => null }));

// expo-router: tests drive screens directly; navigation calls are recorded.
jest.mock("expo-router", () => {
  const router = { push: jest.fn(), replace: jest.fn(), back: jest.fn(), canGoBack: jest.fn(() => true) };
  return {
    router,
    useRouter: () => router,
    useLocalSearchParams: jest.fn(() => ({})),
    Redirect: () => null,
    Stack: Object.assign(() => null, { Screen: () => null, Protected: () => null }),
    Tabs: Object.assign(() => null, { Screen: () => null }),
  };
});

// The app binds i18n in the root layout; tests render screens directly, so bind it here.
require("./src/i18n");

// Push notifications: tests read what was registered and fire listeners by hand.
jest.mock("expo-notifications", () => {
  const listeners = { received: [], response: [] };
  return {
    setNotificationHandler: jest.fn(),
    setNotificationChannelAsync: jest.fn(async () => null),
    getPermissionsAsync: jest.fn(async () => ({ status: "granted" })),
    requestPermissionsAsync: jest.fn(async () => ({ status: "granted" })),
    getExpoPushTokenAsync: jest.fn(async () => ({ type: "expo", data: "ExponentPushToken[test-device-0001]" })),
    addNotificationReceivedListener: jest.fn((fn) => {
      listeners.received.push(fn);
      return { remove: () => listeners.received.splice(listeners.received.indexOf(fn), 1) };
    }),
    addNotificationResponseReceivedListener: jest.fn((fn) => {
      listeners.response.push(fn);
      return { remove: () => listeners.response.splice(listeners.response.indexOf(fn), 1) };
    }),
    AndroidImportance: { DEFAULT: 3, HIGH: 4, MAX: 5 },
    AndroidNotificationVisibility: { PUBLIC: 1 },
    __listeners: listeners,
  };
});
jest.mock("expo-device", () => ({ isDevice: true }));
jest.mock("expo-haptics", () => ({
  impactAsync: jest.fn(async () => {}),
  notificationAsync: jest.fn(async () => {}),
  ImpactFeedbackStyle: { Light: "light", Medium: "medium", Heavy: "heavy" },
  NotificationFeedbackType: { Success: "success", Warning: "warning", Error: "error" },
}));
jest.mock("expo-location", () => ({
  requestForegroundPermissionsAsync: jest.fn(async () => ({ status: "granted" })),
  getCurrentPositionAsync: jest.fn(async () => ({ coords: { latitude: 6.4281, longitude: 3.4219, accuracy: 12 } })),
  Accuracy: { Balanced: 3 },
}));

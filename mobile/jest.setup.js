/* global jest */
// Reanimated 4 / worklets: use the libraries' own Jest mocks (no UI thread under Jest).
jest.mock("react-native-worklets", () => require("react-native-worklets/lib/module/mock"));
jest.mock("react-native-reanimated", () => require("react-native-reanimated/mock"));

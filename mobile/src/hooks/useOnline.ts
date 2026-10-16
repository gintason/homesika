import { useNetInfo } from "@react-native-community/netinfo";

/** false only when we're sure there's no connection (unknown counts as online). */
export function useOnline(): boolean {
  const { isConnected, isInternetReachable } = useNetInfo();
  return !(isConnected === false || isInternetReachable === false);
}

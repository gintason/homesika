/** Same rule as the API (accounts/validators.is_weak_pin): all one digit, or a straight run up or down. */
export function isWeakPin(pin: string): boolean {
  const digits = pin.split("").map(Number);
  if (new Set(digits).size === 1) return true;
  const steps = new Set(digits.slice(1).map((d, i) => d - (digits[i] ?? 0)));
  return steps.size === 1 && (steps.has(1) || steps.has(-1));
}

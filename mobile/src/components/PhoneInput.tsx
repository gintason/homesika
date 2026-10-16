import { TextField, type TextFieldProps } from "./TextField";

type Props = Omit<TextFieldProps, "value" | "onChangeText" | "prefix" | "keyboardType"> & {
  value: string;
  onChangeText: (raw: string) => void;
};

/**
 * Nigerian phone number with a fixed +234 prefix. Accepts 0801…, 801… or +234 801…;
 * callers normalise with normalisePhone() before sending.
 */
export function PhoneInput({ value, onChangeText, ...rest }: Props) {
  return (
    <TextField
      prefix="+234"
      value={value}
      onChangeText={(t) => onChangeText(t.replace(/[^\d+ ]/g, "").slice(0, 17))}
      keyboardType="phone-pad"
      autoComplete="tel"
      textContentType="telephoneNumber"
      {...rest}
    />
  );
}

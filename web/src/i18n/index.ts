import { en } from "./en";

/**
 * User-facing copy. English only for now; to add Pidgin, create pcm.ts with the same shape
 * (typed as `typeof en`) and pick the dictionary from the user's preferred_language.
 */
export const strings = en;
export type Strings = typeof en;

/** Fill {placeholders}: fmt("Hi {name}", {name: "Ada"}) -> "Hi Ada". */
export function fmt(template: string, vars: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, k: string) => (k in vars ? String(vars[k]) : `{${k}}`));
}

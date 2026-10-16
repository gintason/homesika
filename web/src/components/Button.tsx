import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router";

import { strings } from "../i18n";
import { cx } from "./cx";
import { Spinner } from "./Spinner";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-primary-600 text-white hover:bg-primary-700 active:bg-primary-800",
  secondary: "border border-primary-600 bg-surface-card text-primary-600 hover:bg-primary-50",
  ghost: "text-primary-600 hover:bg-primary-50",
  destructive: "bg-danger-500 text-white hover:bg-danger-700",
};

export function buttonClasses(variant: ButtonVariant = "primary", fullWidth = false, className?: string) {
  return cx(
    "inline-flex min-h-touch min-w-touch items-center justify-center gap-2 rounded-md px-5 text-base font-semibold",
    "transition-colors duration-fast disabled:cursor-not-allowed disabled:opacity-60",
    VARIANTS[variant],
    fullWidth && "w-full",
    className,
  );
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
  fullWidth?: boolean;
  icon?: ReactNode;
}

export function Button({
  variant = "primary",
  loading = false,
  fullWidth = false,
  icon,
  className,
  children,
  disabled,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={buttonClasses(variant, fullWidth, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Spinner /> : icon}
      <span>{children}</span>
      {loading && <span className="sr-only">{strings.common.pleaseWait}</span>}
    </button>
  );
}

export interface ButtonLinkProps extends LinkProps {
  variant?: ButtonVariant;
  fullWidth?: boolean;
}

/** A link that looks like a button (navigation, not an action). */
export function ButtonLink({ variant = "primary", fullWidth, className, ...rest }: ButtonLinkProps) {
  return <Link className={buttonClasses(variant, fullWidth, typeof className === "string" ? className : undefined)} {...rest} />;
}

import type { InputHTMLAttributes } from "react";

import { cx } from "../../lib/cx";
import { CONTROL_CLASS } from "./controlStyles";

/** Single-line text input; pair it with Field for label and error. */
export function TextInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(CONTROL_CLASS, className)} {...rest} />;
}

import type { SVGProps } from "react";

import { PRODUCT_NAME } from "../../lib/brand";

/**
 * The mark: a four-pointed star with concave arms, drawn as three nested layers
 * (outer outline, inner outline, solid centre). It uses currentColor only.
 */
export function BeaconLogo({ size = 20, ...rest }: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinejoin="round"
      role="img"
      aria-label={PRODUCT_NAME}
      {...rest}
    >
      <path d="M12 1.5Q13.6 10.4 22.5 12Q13.6 13.6 12 22.5Q10.4 13.6 1.5 12Q10.4 10.4 12 1.5Z" />
      <path d="M12 7.3Q12.9 11.1 16.7 12Q12.9 12.9 12 16.7Q11.1 12.9 7.3 12Q11.1 11.1 12 7.3Z" />
      <path d="M12 10.4 13.6 12 12 13.6 10.4 12Z" fill="currentColor" stroke="none" />
    </svg>
  );
}

import Image from "next/image";
import Link from "next/link";

import { cn } from "@/lib/utils";

// The logo has white lettering on transparency: place it on ink only.
export function BrandLogo({ className, href = "/" }: { className?: string; href?: string }) {
  return (
    <Link href={href} className={cn("inline-flex shrink-0", className)}>
      <Image
        src="/brand/select-logo-white.png"
        alt="Select Exterminating"
        width={900}
        height={250}
        priority
        className="h-8 w-auto"
      />
    </Link>
  );
}

/** A statement band on ink, as on the dashboards (docs/design-guidance.md §9). */
export function BrandBand({
  title,
  children,
  className,
}: {
  title: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "flex flex-col justify-center bg-ink px-8 py-12 text-white sm:px-12",
        className,
      )}
    >
      <h1 className="max-w-md text-3xl sm:text-4xl">{title}</h1>
      {children && <div className="mt-6 max-w-md text-lg leading-relaxed">{children}</div>}
    </section>
  );
}

export function ProofPoints() {
  return (
    <dl className="mt-10 grid grid-cols-3 gap-6">
      {[
        ["70+", "Years in business"],
        ["9", "Branches"],
        ["900+", "Technicians"],
      ].map(([value, label]) => (
        <div key={label}>
          <dt className="sr-only">{label}</dt>
          <dd className="text-3xl font-bold text-highlight tabular-nums">{value}</dd>
          <dd className="text-sm text-ink-muted">{label}</dd>
        </div>
      ))}
    </dl>
  );
}

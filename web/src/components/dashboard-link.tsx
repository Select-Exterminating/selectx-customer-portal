"use client";

import Link from "next/link";
import { createContext, type ReactNode, useContext } from "react";

import { cn } from "@/lib/utils";

/** Whether the dashboard's viewer can open the pages it links to (a customer's users can't). */
export const DashboardLinksContext = createContext(true);

/** A link to a page beyond the dashboard, or plain text for someone who can't open it. */
export function DashboardLink({
  href,
  className,
  children,
}: {
  href: string;
  className?: string;
  children: ReactNode;
}) {
  const linked = useContext(DashboardLinksContext);
  if (!linked) return <span className={className}>{children}</span>;
  return (
    <Link href={href} className={cn("text-primary hover:underline", className)}>
      {children}
    </Link>
  );
}

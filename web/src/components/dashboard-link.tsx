"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { createContext, type ReactNode, useCallback, useContext } from "react";

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

/** The store whose flyover is open, kept in the URL (`?store=`) so Back and shared links work. */
export function useStoreParam(): [string | null, (locationId: string | null) => void] {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const setStore = useCallback(
    (locationId: string | null) => {
      const next = new URLSearchParams(searchParams.toString());
      if (locationId) next.set("store", locationId);
      else next.delete("store");
      const query = next.toString();
      router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [router, pathname, searchParams],
  );
  return [searchParams.get("store"), setStore];
}

/** A store's name in a dashboard table: opens its flyover. Everyone who sees the dashboard can. */
export function StoreLink({
  locationId,
  className,
  children,
}: {
  locationId: string;
  className?: string;
  children: ReactNode;
}) {
  const [, setStore] = useStoreParam();
  return (
    <button
      type="button"
      onClick={() => setStore(locationId)}
      className={cn(
        "cursor-pointer text-left text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
        className,
      )}
    >
      {children}
    </button>
  );
}

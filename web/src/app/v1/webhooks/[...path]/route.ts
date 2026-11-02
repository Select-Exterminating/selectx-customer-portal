import { NextResponse, type NextRequest } from "next/server";

import { API_URL, apiUnreachable } from "@/lib/server/session";

// PestPac and GoCanvas deliver here, so FastAPI needs no public domain of its own. Unlike the BFF
// route this takes no session and no CSRF check: senders hold neither, and FastAPI judges each
// delivery itself. So only the webhook receivers pass.
const RECEIVER = /^(pestpac|gocanvas\/[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12})$/i;

// Hop-by-hop headers belong to this connection, and FastAPI takes nothing from credentials on a
// public route. Everything else goes through: signatures, and GoCanvas requests are stored as sent.
// `expect` was already answered by this server, and fetch fails outright if it's passed on.
const DROPPED_REQUEST_HEADERS = new Set([
  "authorization",
  "connection",
  "content-length",
  "cookie",
  "expect",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

async function handler(req: NextRequest, ctx: RouteContext<"/v1/webhooks/[...path]">) {
  const path = (await ctx.params).path.join("/");
  if (!RECEIVER.test(path)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }

  const headers = new Headers();
  req.headers.forEach((value, name) => {
    if (!DROPPED_REQUEST_HEADERS.has(name)) headers.set(name, value);
  });

  // Streamed, not read here: FastAPI enforces WEBHOOK_MAX_BODY_BYTES as the body arrives. Fetch
  // requires `duplex` for a stream, though TypeScript's RequestInit doesn't list it yet.
  const init: RequestInit & { duplex: "half" } = {
    method: req.method,
    headers,
    body: req.body,
    duplex: "half",
    cache: "no-store",
    redirect: "manual",
  };

  let upstream: Response;
  try {
    upstream = await fetch(`${API_URL}/v1/webhooks/${path}${req.nextUrl.search}`, init);
  } catch (error) {
    return apiUnreachable(error);
  }

  const contentType = upstream.headers.get("content-type");
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: contentType ? { "content-type": contentType } : undefined,
  });
}

export { handler as GET, handler as POST, handler as PUT };

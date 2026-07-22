import { gatewayFetch, proxyJson } from "@/lib/gateway";

export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  try {
    // the bracket build is heavy on first hit; give it room
    return await proxyJson(
      await gatewayFetch("/bracket", { signal: AbortSignal.timeout(120_000) }),
    );
  } catch {
    return Response.json({ detail: "gateway unavailable" }, { status: 503 });
  }
}

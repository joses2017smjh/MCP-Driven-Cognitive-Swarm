import { gatewayFetch, proxyJson } from "@/lib/gateway";

export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  try {
    return await proxyJson(await gatewayFetch("/leagues"));
  } catch {
    return Response.json({ detail: "gateway unavailable" }, { status: 503 });
  }
}

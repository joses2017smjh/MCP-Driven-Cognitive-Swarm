import { gatewayFetch, proxyJson } from "@/lib/gateway";

export const runtime = "nodejs";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await params;
  try {
    return await proxyJson(await gatewayFetch(`/leagues/${encodeURIComponent(id)}`));
  } catch {
    return Response.json({ detail: "gateway unavailable" }, { status: 503 });
  }
}

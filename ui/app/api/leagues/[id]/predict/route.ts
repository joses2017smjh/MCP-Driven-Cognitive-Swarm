import { gatewayFetch, proxyJson } from "@/lib/gateway";

export const runtime = "nodejs";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await params;
  const url = new URL(req.url);
  const home = url.searchParams.get("home") ?? "";
  const away = url.searchParams.get("away") ?? "";
  if (!home || !away) {
    return Response.json({ detail: "home and away required" }, { status: 400 });
  }
  const qs = `home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}`;
  try {
    return await proxyJson(
      await gatewayFetch(`/leagues/${encodeURIComponent(id)}/predict?${qs}`),
    );
  } catch {
    return Response.json({ detail: "gateway unavailable" }, { status: 503 });
  }
}

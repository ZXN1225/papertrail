import { proxy } from "@/app/api/library/route";

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ entry_id: string }> },
) {
  const { entry_id } = await context.params;
  if (!/^[0-9a-f-]{36}$/i.test(entry_id)) {
    return Response.json({ detail: "invalid_entry_id" }, { status: 422 });
  }
  return proxy(`/api/v1/library/${entry_id}`, { method: "DELETE" });
}

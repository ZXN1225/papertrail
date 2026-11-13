import { cookies } from "next/headers";
import { NextRequest } from "next/server";
import {
  backendRequest,
  invalidResponse,
  jsonResponse,
  tooLargeResponse,
  unavailableResponse,
} from "@/lib/api/backend";

const MAX_UPLOAD_BYTES = 40 * 1024 * 1024;

export async function GET(request: NextRequest) {
  const libraryEntryId = request.nextUrl.searchParams.get("library_entry_id");
  const query = libraryEntryId
    ? `?library_entry_id=${encodeURIComponent(libraryEntryId)}`
    : "";
  return proxy(`/api/v1/documents${query}`, { method: "GET" });
}

export async function POST(request: NextRequest) {
  const contentLength = Number(request.headers.get("content-length") ?? 0);
  if (contentLength > MAX_UPLOAD_BYTES + 128_000) return tooLargeResponse();

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return invalidResponse("请选择有效的 PDF 文件。");
  }
  const file = form.get("file");
  const libraryEntryId = form.get("library_entry_id");
  const title = form.get("title");
  const rightsAttested = form.get("rights_attested");
  const hasLibraryEntry =
    typeof libraryEntryId === "string" && libraryEntryId.length > 0;
  const hasTitle = typeof title === "string" && title.trim().length > 0;
  if (
    !(file instanceof File) ||
    hasLibraryEntry === hasTitle ||
    (hasLibraryEntry && !/^[0-9a-f-]{36}$/i.test(libraryEntryId)) ||
    (hasTitle && title.trim().length > 500) ||
    rightsAttested !== "true" ||
    !file.name.toLowerCase().endsWith(".pdf")
  ) {
    return invalidResponse(
      "请提供 PDF、稿件标题或个人文库条目，以及逐篇权利声明。",
    );
  }
  if (file.size > MAX_UPLOAD_BYTES) return tooLargeResponse();

  const forwarded = new FormData();
  forwarded.append("file", file, file.name);
  if (hasLibraryEntry) forwarded.append("library_entry_id", libraryEntryId);
  if (hasTitle) forwarded.append("title", title.trim());
  forwarded.append("rights_attested", "true");
  return proxy("/api/v1/documents", { method: "POST", body: forwarded });
}

async function proxy(path: string, init: RequestInit) {
  try {
    const jar = await cookies();
    const token = jar.get("papertrail_session")?.value;
    return await jsonResponse(
      await backendRequest(path, {
        ...init,
        headers: {
          ...(token
            ? { Cookie: `papertrail_session=${encodeURIComponent(token)}` }
            : {}),
        },
      }),
    );
  } catch {
    return unavailableResponse();
  }
}

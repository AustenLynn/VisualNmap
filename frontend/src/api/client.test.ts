import { ApiError, api } from "./client";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

test("preview posts the request as JSON", async () => {
  const fetchFn = mockFetch(200, { argv: ["nmap"], parts: [], warnings: [] });
  await api.preview({ target: "10.0.0.1", options: [] });
  const [url, init] = fetchFn.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("/api/command/preview");
  expect(init.method).toBe("POST");
  expect(JSON.parse(init.body as string)).toEqual({ target: "10.0.0.1", options: [] });
});

test("errors carry the backend field and message", async () => {
  mockFetch(422, { field: "target", message: "bad target" });
  await expect(api.preview({ target: "-x", options: [] })).rejects.toMatchObject({
    status: 422, field: "target", message: "bad target",
  });
});

test("string detail becomes the message", async () => {
  mockFetch(403, { detail: "Cross-site request blocked." });
  const err = await api.startScan({ target: "x", options: [] }).catch((e) => e);
  expect(err).toBeInstanceOf(ApiError);
  expect(err.message).toBe("Cross-site request blocked.");
});

test("204 resolves to undefined", async () => {
  mockFetch(204, undefined);
  await expect(api.deleteScan("abc")).resolves.toBeUndefined();
});

test("exportUrl", () => {
  expect(api.exportUrl("abc", "xml")).toBe("/api/scans/abc/export?format=xml");
});

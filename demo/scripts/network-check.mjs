import assert from "node:assert/strict";
import http from "node:http";
import https from "node:https";
import { writeFile } from "node:fs/promises";
import { openBrowser } from "@remotion/renderer";

const [output] = process.argv.slice(2);
if (!output) throw new Error("Provide a fresh evidence output path");
const nodeBlocked = await new Promise((resolve) => {
  try {
    const request = https.get("https://example.com", () => resolve(false));
    request.once("error", (error) =>
      resolve(
        error.message.includes("R9 local-only process rejected outbound host"),
      ),
    );
    request.setTimeout(5000, () => {
      request.destroy();
      resolve(false);
    });
  } catch (error) {
    resolve(
      error.message.includes("R9 local-only process rejected outbound host"),
    );
  }
});
assert.equal(nodeBlocked, true);
const server = http.createServer((_request, response) =>
  response.end("<html><body>Local setup probe</body></html>"),
);
await new Promise((resolve, reject) => {
  server.once("error", reject);
  server.listen(0, resolve);
});
const address = server.address();
assert.equal(address.address, "127.0.0.1");
const browser = await openBrowser("chrome");
try {
  const page = await browser.newPage({
    context: () => null,
    logLevel: "warn",
    indent: false,
    pageIndex: 0,
    onBrowserLog: null,
    onLog: () => {},
  });
  await page.goto({ url: `http://127.0.0.1:${address.port}`, timeout: 10000 });
  let chromiumBlocked = false;
  let chromiumError = null;
  try {
    await page.goto({ url: "https://example.com", timeout: 5000 });
  } catch (error) {
    chromiumError = error.message;
    chromiumBlocked = /ERR_PROXY_CONNECTION_FAILED|ERR_NAME_NOT_RESOLVED/.test(
      error.message,
    );
  }
  assert.equal(chromiumBlocked, true);
  await writeFile(
    output,
    JSON.stringify(
      {
        schema: "marketlab-video-network-check-v1",
        status: "passed",
        nodeExternalBlocked: nodeBlocked,
        browserExternalBlocked: chromiumBlocked,
        chromiumError,
        localBind: address.address,
        localBrowserNavigation: "passed",
        scope:
          "Selected Node and Chromium processes only; not host-wide packet capture",
      },
      null,
      2,
    ),
    { flag: "wx" },
  );
} finally {
  await browser.close({ silent: true });
  await new Promise((resolve) => server.close(resolve));
}

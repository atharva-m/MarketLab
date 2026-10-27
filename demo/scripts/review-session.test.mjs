import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { withReviewSession } from "./review-session.mjs";

test("failed browser launch closes the actual local listener and finalizes failure", async () => {
  const server = http.createServer();
  let finalized;
  await assert.rejects(
    () =>
      withReviewSession({
        server,
        launch: async () => {
          throw new Error("launch failed");
        },
        run: async () => {
          assert.fail("must not run");
        },
        finalize: async (error, cleanupErrors) => {
          finalized = { error: String(error), cleanupErrors };
        },
      }),
    /launch failed/,
  );
  assert.equal(server.listening, false);
  assert.match(finalized.error, /launch failed/);
  assert.deepEqual(finalized.cleanupErrors, []);
});

test("browser cleanup failure does not prevent local listener cleanup", async () => {
  const server = http.createServer();
  let finalized;
  await assert.rejects(
    () =>
      withReviewSession({
        server,
        launch: async () => ({
          close: async () => {
            throw new Error("close failed");
          },
        }),
        run: async () => {},
        finalize: async (error, cleanupErrors) => {
          finalized = { error, cleanupErrors };
        },
      }),
    /cleanup failed/,
  );
  assert.equal(server.listening, false);
  assert.equal(finalized.error, null);
  assert.equal(finalized.cleanupErrors[0].resource, "browser");
});

export async function withReviewSession({ server, launch, run, finalize }) {
  let browser = null;
  let failure = null;
  const cleanupErrors = [];
  try {
    await new Promise((resolve, reject) => {
      server.once("error", reject);
      server.listen(0, resolve);
    });
    browser = await launch();
    await run(browser, server.address());
  } catch (error) {
    failure = error;
  } finally {
    try {
      if (browser) await browser.close({ silent: true });
    } catch (error) {
      cleanupErrors.push({ resource: "browser", error: String(error) });
    }
    try {
      server.closeAllConnections();
      if (server.listening)
        await new Promise((resolve, reject) =>
          server.close((error) => (error ? reject(error) : resolve())),
        );
    } catch (error) {
      cleanupErrors.push({ resource: "server", error: String(error) });
    }
    await finalize(failure, cleanupErrors);
  }
  if (failure) throw failure;
  if (cleanupErrors.length)
    throw new Error("Local video review cleanup failed");
}

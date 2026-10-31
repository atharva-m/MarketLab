import { Sha256 } from "./sha256";

// A worker is dedicated to one file and terminated by the owner on cancellation.
self.onmessage = async (event: MessageEvent<{ file: File }>) => {
  try {
    const file = event.data.file;
    if (!(file instanceof Blob) || file.size <= 0 || file.size > 4 * 1024 ** 3)
      throw new Error("Choose a nonempty canonical file of at most 4 GiB.");
    const hash = new Sha256();
    const chunk = 1024 ** 2;
    for (let at = 0; at < file.size; at += chunk) {
      hash.update(
        new Uint8Array(await file.slice(at, at + chunk).arrayBuffer()),
      );
      self.postMessage({
        kind: "progress",
        bytes: Math.min(at + chunk, file.size),
      });
    }
    self.postMessage({ kind: "done", sha256: hash.digest() });
  } catch {
    self.postMessage({
      kind: "error",
      message: "The selected file could not be hashed. Reselect it and retry.",
    });
  }
};

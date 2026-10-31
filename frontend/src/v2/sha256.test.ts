import { createHash } from "node:crypto";
import { expect, it } from "vitest";
import { lengthWords, Sha256 } from "./sha256";

it("matches independent SHA-256 vectors and native hashes across block/chunk boundaries", () => {
  const vectors = [
    ["", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"],
    ["abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"],
    [
      "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
      "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
    ],
    [
      "a".repeat(1_000_000),
      "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0",
    ],
  ];
  for (const [text, expected] of vectors)
    expect(new Sha256().update(new TextEncoder().encode(text)).digest()).toBe(
      expected,
    );
  for (const length of [1, 55, 56, 63, 64, 65, 127, 128, 129, 1024 ** 2 + 73]) {
    const bytes = Uint8Array.from({ length }, (_, i) => (i * 37 + 11) % 256);
    const expected = createHash("sha256").update(bytes).digest("hex");
    for (const chunk of [1, 17, 63, 64, 65, 1024 ** 2]) {
      const hash = new Sha256();
      for (let at = 0; at < length; at += chunk)
        hash.update(bytes.subarray(at, at + chunk));
      expect(hash.digest()).toBe(expected);
      expect(() => hash.digest()).toThrow("already finalized");
      expect(() => hash.update(new Uint8Array())).toThrow("already finalized");
    }
  }
});

it("encodes lengths independently across the 4 GiB boundary without 32-bit byte wrap", () => {
  for (const bytes of [
    0, 63, 0x1fffffff, 0x20000000, 0xffffffff, 0x100000000, 0x100000001,
    0x1ffffffff,
  ]) {
    const reference = Buffer.alloc(8);
    reference.writeBigUInt64BE(BigInt(bytes) * 8n);
    const [high, low] = lengthWords(bytes);
    const actual = Buffer.alloc(8);
    actual.writeUInt32BE(high, 0);
    actual.writeUInt32BE(low, 4);
    expect(actual.equals(reference)).toBe(true);
  }
  for (const bytes of [-1, 0.5, Infinity, Number.MAX_SAFE_INTEGER + 1])
    expect(() => lengthWords(bytes)).toThrow("Invalid");
});

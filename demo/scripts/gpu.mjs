import { openBrowser } from "@remotion/renderer";
import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

export async function inspectDedicatedGpu(browser) {
  const system = (await browser.connection.send("SystemInfo.getInfo")).value;
  const page = await browser.newPage({
    context: () => null,
    logLevel: "warn",
    indent: false,
    pageIndex: 0,
    onBrowserLog: null,
    onLog: () => {},
  });
  try {
    const webgl = await page.evaluate(() => {
      const context = document
        .createElement("canvas")
        .getContext("webgl2", { powerPreference: "high-performance" });
      if (!context) return { renderer: null, vendor: null };
      const debug = context.getExtension("WEBGL_debug_renderer_info");
      return {
        renderer: debug
          ? context.getParameter(debug.UNMASKED_RENDERER_WEBGL)
          : context.getParameter(context.RENDERER),
        vendor: debug
          ? context.getParameter(debug.UNMASKED_VENDOR_WEBGL)
          : context.getParameter(context.VENDOR),
      };
    });
    const renderer = system.gpu.auxAttributes?.glRenderer ?? "";
    if (
      !/NVIDIA/i.test(renderer) ||
      !/NVIDIA/i.test(webgl.renderer ?? "") ||
      /SwiftShader|llvmpipe|WARP|software/i.test(renderer + webgl.renderer)
    )
      throw new Error(
        `Dedicated NVIDIA renderer not verified: SystemInfo=${renderer}; WebGL=${webgl.renderer}`,
      );
    return {
      devices: system.gpu.devices,
      featureStatus: system.gpu.featureStatus,
      systemGlRenderer: renderer,
      webgl,
      scope:
        "Actual selected Chromium ANGLE and WebGL adapter; does not imply every render operation uses GPU.",
    };
  } finally {
    await page.close();
  }
}

if (path.resolve(process.argv[1] ?? "") === fileURLToPath(import.meta.url)) {
  const [output] = process.argv.slice(2);
  if (!output) throw new Error("Provide fresh GPU evidence output");
  process.env.R9_VIDEO_GPU = "1";
  let browser = null;
  const receipt = { schema: "marketlab-video-gpu-probe-v1", status: "running" };
  try {
    browser = await openBrowser("chrome", { chromiumOptions: { gl: "angle" } });
    receipt.gpu = await inspectDedicatedGpu(browser);
    receipt.status = "passed";
  } catch (error) {
    receipt.status = "failed";
    receipt.error = String(error);
  } finally {
    try {
      if (browser) await browser.close({ silent: true });
      receipt.browserClosed = true;
    } catch (error) {
      receipt.status = "failed";
      receipt.cleanupError = String(error);
    }
    await writeFile(output, JSON.stringify(receipt, null, 2), { flag: "wx" });
  }
  if (receipt.status !== "passed")
    throw new Error(receipt.error ?? receipt.cleanupError);
}

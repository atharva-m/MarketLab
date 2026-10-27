// Process-scoped controls. No host firewall, proxy setting or system change.
const net = require("node:net");
const childProcess = require("node:child_process");
const { appendFileSync } = require("node:fs");
const audit = (event) => {
  if (process.env.R9_VIDEO_NETWORK_AUDIT)
    appendFileSync(
      process.env.R9_VIDEO_NETWORK_AUDIT,
      JSON.stringify(event) + "\n",
    );
};
const allowed = (host) =>
  !host || ["localhost", "127.0.0.1", "::1", "::ffff:127.0.0.1"].includes(host);
const originalConnect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...args) {
  const first = args[0];
  const options =
    typeof first === "object" && first !== null
      ? Array.isArray(first)
        ? first[0]
        : first
      : typeof first === "number" || /^\d+$/.test(first)
        ? { host: typeof args[1] === "string" ? args[1] : "localhost" }
        : { path: first };
  const host = options.host ?? options.hostname;
  const pipe = typeof options.path === "string" && !host && !options.port;
  if (!pipe && !allowed(host)) {
    audit({ event: "blocked-node-host", host });
    throw new Error(`R9 local-only process rejected outbound host: ${host}`);
  }
  return originalConnect.apply(this, args);
};
const originalListen = net.Server.prototype.listen;
net.Server.prototype.listen = function (...args) {
  if (args[0] && typeof args[0] === "object" && !args[0].path)
    args[0] = { ...args[0], host: "127.0.0.1" };
  else if (typeof args[0] === "number") {
    if (typeof args[1] === "string") args[1] = "127.0.0.1";
    else args.splice(1, 0, "127.0.0.1");
  }
  return originalListen.apply(this, args);
};
const originalSpawn = childProcess.spawn;
childProcess.spawn = function (command, args, options) {
  if (
    /(chrome|chromium|headless_shell|chrome-headless-shell)(\.exe)?$/i.test(
      command,
    )
  ) {
    if (process.env.R9_VIDEO_GPU === "1") {
      args = [
        ...(args || []),
        "--force_high_performance_gpu",
        "--use-gl=angle",
        "--use-angle=d3d11",
        "--enable-gpu-rasterization",
      ];
    }
    args = [
      ...(args || []),
      "--disable-background-networking",
      "--disable-component-update",
      "--proxy-server=http://127.0.0.1:9",
      "--proxy-bypass-list=localhost;127.0.0.1;[::1]",
      "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1",
    ];
    audit({
      event: "guarded-browser-launch",
      proxy: "http://127.0.0.1:9",
      dns: "external names unresolved",
      executable: command,
    });
  }
  return originalSpawn.call(this, command, args, options);
};

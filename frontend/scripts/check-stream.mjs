import fs from "node:fs/promises";

const configPath = new URL("../config/live-session.json", import.meta.url);
const config = JSON.parse(await fs.readFile(configPath, "utf8"));
const protocol = config.playback?.primary_protocol ?? "hls";
const hlsUrl = config.playback?.hls_url;
const iframeUrl = config.playback?.iframe_url;

if (protocol === "iframe") {
  if (!iframeUrl) {
    console.error("No playback.iframe_url configured in frontend/config/live-session.json");
    process.exit(1);
  }
  console.log(`Checking iframe page URL: ${iframeUrl}`);
  const response = await fetchUrl(iframeUrl);
  printResponse(response);
  if (!response.ok) {
    console.error("The iframe page URL returned an HTTP error.");
    process.exit(1);
  }
  const xFrameOptions = response.headers.get("x-frame-options");
  const csp = response.headers.get("content-security-policy");
  if (xFrameOptions) {
    console.error(`Warning: X-Frame-Options is set to "${xFrameOptions}". Browser embedding may be blocked.`);
  }
  if (csp?.includes("frame-ancestors")) {
    console.error(`Warning: CSP frame-ancestors is present. Browser embedding may be blocked.`);
  }
  console.log("OK: page URL is reachable. If the browser area is blank, open it in a new tab or ask provider to allow iframe embedding.");
  process.exit(0);
}

if (!hlsUrl) {
  console.error("No playback.hls_url configured in frontend/config/live-session.json");
  process.exit(1);
}

console.log(`Checking stream URL: ${hlsUrl}`);

const response = await fetchUrl(hlsUrl);
printResponse(response);

const body = await response.text();
const firstLine = body.split(/\r?\n/, 1)[0] ?? "";
console.log(`First line: ${firstLine.slice(0, 120)}`);

if (!response.ok) {
  console.error("The stream URL returned an HTTP error.");
  process.exit(1);
}

if (!body.trimStart().startsWith("#EXTM3U")) {
  console.error(
    "This URL is not an HLS playlist. Use the direct .m3u8 URL, not the website/homepage URL.",
  );
  process.exit(1);
}

console.log("OK: URL looks like a valid HLS playlist.");

async function fetchUrl(url) {
  try {
    return await fetch(url, {
      headers: {
        "User-Agent": "bota-model-stream-check/1.0",
      },
    });
  } catch (error) {
    console.error(`Request failed: ${error.message}`);
    process.exit(1);
  }
}

function printResponse(response) {
  console.log(`HTTP status: ${response.status}`);
  console.log(`Content-Type: ${response.headers.get("content-type") ?? "unknown"}`);
}

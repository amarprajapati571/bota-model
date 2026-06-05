import fs from "node:fs/promises";

const configPath = new URL("../config/live-session.json", import.meta.url);
const config = JSON.parse(await fs.readFile(configPath, "utf8"));
const hlsUrl = config.playback?.hls_url;

if (!hlsUrl) {
  console.error("No playback.hls_url configured in frontend/config/live-session.json");
  process.exit(1);
}

console.log(`Checking stream URL: ${hlsUrl}`);

let response;
try {
  response = await fetch(hlsUrl, {
    headers: {
      "User-Agent": "bota-model-stream-check/1.0",
    },
  });
} catch (error) {
  console.error(`Request failed: ${error.message}`);
  process.exit(1);
}

console.log(`HTTP status: ${response.status}`);
console.log(`Content-Type: ${response.headers.get("content-type") ?? "unknown"}`);

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

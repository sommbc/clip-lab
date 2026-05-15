import fs from "node:fs";
import path from "node:path";
import { selectComposition, renderMedia } from "@remotion/renderer";
import { getBundleLocation } from "./bundle.js";
import { renderJobs } from "./server.js";

export interface RenderParams {
  renderId: string;
  jobId: string;
  clipIndex: number;
  outputRelativePath?: string;
  props: {
    videoUrl: string;
    durationInFrames: number;
    fps: number;
    width: number;
    height: number;
    subtitles: unknown;
    hook: unknown;
    effects: unknown;
  };
}

/**
 * Executes a Remotion render in the background.
 * Updates the in-memory render job map with progress and final status.
 */
export async function executeRender(params: RenderParams): Promise<void> {
  const { renderId, jobId, clipIndex, outputRelativePath, props } = params;
  const job = renderJobs.get(renderId);

  if (!job) {
    console.error(`[render-worker] Job ${renderId} not found in map`);
    return;
  }

  try {
    job.status = "rendering";
    job.progress = 0;

    console.log(
      `[render-worker] Starting render ${renderId} (job=${jobId}, clip=${clipIndex})`
    );

    const bundleLocation = getBundleLocation();
    const browserExecutable =
      process.env.REMOTION_BROWSER_EXECUTABLE ||
      process.env.PUPPETEER_EXECUTABLE_PATH ||
      null;

    const composition = await selectComposition({
      serveUrl: bundleLocation,
      id: "ShortVideo",
      inputProps: props,
      browserExecutable,
    });

    // Determine output directory and file path
    const outputDir = process.env.OUTPUT_DIR
      ? path.resolve(process.env.OUTPUT_DIR)
      : path.resolve(import.meta.dirname, "../../output");

    const jobOutputDir = path.join(outputDir, jobId);
    fs.mkdirSync(jobOutputDir, { recursive: true });

    const outputLocation = resolveOutputLocation(
      jobOutputDir,
      outputRelativePath,
      clipIndex
    );
    fs.mkdirSync(path.dirname(outputLocation), { recursive: true });

    console.log(`[render-worker] Output: ${outputLocation}`);

    // Render the video
    await renderMedia({
      composition,
      serveUrl: bundleLocation,
      codec: "h264",
      crf: 22,
      outputLocation,
      browserExecutable,
      onProgress: ({ progress }) => {
        const percent = Math.round(progress * 100);
        job.progress = percent;

        if (percent % 10 === 0) {
          console.log(`[render-worker] ${renderId} progress: ${percent}%`);
        }
      },
    });

    // Success
    job.status = "done";
    job.progress = 100;
    job.outputUrl = outputLocation;

    console.log(`[render-worker] Render ${renderId} completed: ${outputLocation}`);
  } catch (err) {
    job.status = "error";
    job.error = err instanceof Error ? err.message : String(err);

    console.error(`[render-worker] Render ${renderId} failed:`, err);
  }
}

function resolveOutputLocation(
  jobOutputDir: string,
  outputRelativePath: string | undefined,
  clipIndex: number
): string {
  if (!outputRelativePath) {
    const timestamp = Date.now();
    return path.join(jobOutputDir, `remotion_${clipIndex}_${timestamp}.mp4`);
  }

  const resolved = path.resolve(jobOutputDir, outputRelativePath);
  const root = path.resolve(jobOutputDir);
  if (resolved !== root && !resolved.startsWith(`${root}${path.sep}`)) {
    throw new Error(`Invalid outputRelativePath outside job output directory: ${outputRelativePath}`);
  }
  return resolved;
}

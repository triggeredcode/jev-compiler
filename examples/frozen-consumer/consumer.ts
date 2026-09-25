/** Consume a frozen Jev artifact with recorded answers and no network access. */

import { readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

interface RecordedResponse {
  model: string;
  answers: Record<string, unknown>;
}

const [artifactArgument] = process.argv.slice(2);
if (!artifactArgument) {
  throw new Error("usage: consumer.ts <frozen-artifact-directory>");
}

const exampleDirectory = dirname(fileURLToPath(import.meta.url));
const artifactDirectory = resolve(artifactArgument);
const runtimeUrl = pathToFileURL(join(artifactDirectory, "runtime.ts")).href;
const programUrl = pathToFileURL(join(artifactDirectory, "program.json"));

const state = JSON.parse(
  await readFile(join(exampleDirectory, "state.json"), "utf8"),
) as unknown;
const recorded = JSON.parse(
  await readFile(join(exampleDirectory, "answers.json"), "utf8"),
) as RecordedResponse;
const { decide } = await import(runtimeUrl);

const provider = {
  async evaluate(
    _state: unknown,
    questions: Record<string, unknown>,
    _options: { model: string },
  ): Promise<RecordedResponse> {
    const missing = Object.keys(questions).filter((key) => !(key in recorded.answers));
    if (missing.length > 0) {
      throw new Error(`recording is missing answers: ${missing.join(", ")}`);
    }
    return recorded;
  },
};

const result = await decide(state, provider, programUrl);
if (result.action !== "approve") {
  throw new Error(`expected approve, received ${result.action}`);
}

process.stdout.write(
  `${JSON.stringify({
    action: result.action,
    model: recorded.model,
    stages: result.trace.map((event: { stage_id: string }) => event.stage_id),
  })}\n`,
);

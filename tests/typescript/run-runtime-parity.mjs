import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const [fixturePath, runtimePath] = process.argv.slice(2);
if (!fixturePath || !runtimePath) {
  throw new Error("usage: run-runtime-parity.mjs <fixture.json> <runtime.ts>");
}

const fixture = JSON.parse(await readFile(fixturePath, "utf8"));
const { runProgram } = await import(pathToFileURL(runtimePath).href);

function normalized(result) {
  return {
    action: result.action,
    variables: result.variables,
    trace: result.trace.map(({ started_at: _startedAt, ...event }) => event),
  };
}

const results = [];
for (const testCase of fixture.cases) {
  const responses = structuredClone(testCase.responses);
  const provider = {
    async evaluate() {
      const response = responses.shift();
      if (response === undefined) throw new Error("recorded provider is exhausted");
      return response;
    },
  };
  try {
    results.push({ name: testCase.name, result: normalized(await runProgram(
      testCase.program,
      testCase.state,
      provider,
    )) });
  } catch (error) {
    results.push({ name: testCase.name, error: error instanceof Error ? error.message : String(error) });
  }
}

process.stdout.write(JSON.stringify(results));

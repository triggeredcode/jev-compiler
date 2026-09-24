import { pathToFileURL } from "node:url";

const [runtimePath] = process.argv.slice(2);
if (!runtimePath) throw new Error("usage: run-frozen-runtime.mjs <runtime.ts>");

const { decide } = await import(pathToFileURL(runtimePath).href);
const provider = {
  async evaluate() {
    throw new Error("provider should not be called by the return-only fixture");
  },
};
const result = await decide({}, provider);
process.stdout.write(JSON.stringify({ action: result.action, variables: result.variables }));

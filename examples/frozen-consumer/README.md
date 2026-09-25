# Consume a frozen artifact

This example shows the handoff from compiler to application. It loads the public `runtime.ts` and
`program.json` files from a frozen artifact, supplies a recorded provider callback, runs one expense
claim, and checks that the action is `approve`. It needs no credentials and makes no network calls.

From the repository root, create a fresh artifact and run the consumer:

```bash
uv run jevcompiler showcase --output .jevcompiler/consumer-demo
node --no-warnings --experimental-strip-types \
  examples/frozen-consumer/consumer.ts \
  .jevcompiler/consumer-demo
```

Expected output:

```json
{"action":"approve","model":"recorded-jev-expense-v1","stages":["assess","decide"]}
```

The consumer does not import compiler source code. Its application-facing contract is the frozen
runtime's `decide(state, provider, programUrl)` function. The provider callback receives the state,
the focused questions for one stage, and the selected model; it returns a typed answer object.

For production, replace the recorded callback with a small adapter around TypeSafe or another
compatible provider. Keep credentials in the process environment, send `state`, `questions`, and
`model` to the provider, validate its response, and return the same `{ model, answers }` shape. The
decision program, branch rules, and runtime do not need to change.

The frozen Python artifact exposes an equivalent `decide(state, provider)` entry point. This example
starts with TypeScript because its generated runtime is dependency-free and can be executed directly
by Node.js 22.

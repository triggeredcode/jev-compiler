# Containers

The container image provides a reproducible Jev Compiler CLI without changing the native `uv`
workflow. It installs a built wheel into a minimal Python runtime, runs as an unprivileged user, and
contains only the public examples required by the offline showcase.

## Offline showcase

Build the image and run the same credential-free showcase used by the native quickstart:

```bash
docker compose build compiler
docker compose run --rm compiler showcase
```

Generated files persist in the `compiler-data` Docker volume. The Compose service uses a read-only
root filesystem, drops Linux capabilities, enables `no-new-privileges`, and provides writable space
only for `/tmp` and the artifact volume.

Run any CLI command after the service name:

```bash
docker compose run --rm compiler doctor
docker compose run --rm compiler validate examples/support-routing/task.yaml --kind task
docker compose run --rm compiler run \
  examples/support-routing/program.yaml \
  examples/support-routing/state.json \
  --answers examples/support-routing/answers.json
```

## Host-run Ollama or LM Studio

The default service reaches host applications through `host.docker.internal`:

- Ollama: `http://host.docker.internal:11434`
- LM Studio: `http://host.docker.internal:1234/v1`

Start the local server before running `doctor`. When needed, override either endpoint for one run:

```bash
docker compose run --rm \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  compiler doctor
```

Native Ollama or LM Studio is generally the best option on macOS because it can use the host's
hardware acceleration while the compiler remains isolated in Docker.

## Compose-managed Ollama

The optional `ollama` profile starts a pinned Ollama service and stores downloaded models in a
separate volume:

```bash
docker compose --profile ollama up -d ollama
docker compose --profile ollama exec ollama ollama pull qwen3:8b
docker compose --profile ollama run --rm compiler-ollama doctor
```

The Ollama API is exposed only to the Compose network. Stop the service with
`docker compose --profile ollama down`; add `--volumes` only when you intentionally want to delete
the compiler artifacts and downloaded models.

## Credentials

No credential is copied into the image or stored in `compose.yaml`. Inject only the key required by
the current command:

```bash
docker compose run --rm -e TYPESAFE_API_KEY compiler run \
  examples/support-routing/program.yaml \
  examples/support-routing/state.json

docker compose run --rm -e TYPESAFE_API_KEY compiler build \
  examples/support-routing/task.yaml --budget quick
```

With `-e NAME` and no value, Docker forwards that variable from the current shell. Paid OpenRouter
models still require the CLI's explicit model selection and `--allow-paid` guard. When OpenRouter is
the teacher, pass both `-e TYPESAFE_API_KEY` and `-e OPENROUTER_API_KEY`; Ollama and LM Studio need no
teacher credential, but the first full build still needs TypeSafe for live Jev evaluation.

## Direct image usage

The image entry point is `jevcompiler`, so arguments map directly to the CLI:

```bash
docker build -t jev-compiler:local .
docker run --rm jev-compiler:local --help
docker run --rm jev-compiler:local showcase --output /tmp/showcase
```

For durable output outside Compose, mount a writable directory at `/workspace/.jevcompiler`. The
build context is allowlisted by `.dockerignore`; Git metadata, environment files, and the private
`.jevcompiler/` workspace are never sent to the image builder.

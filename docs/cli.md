# The visio-ai terminal app

`visio-ai` turns a folder of code into a professional Visio diagram. Run it with no arguments for
the interactive studio, or use a subcommand.

## The studio

```powershell
visio-ai [PATH] [--type TYPE] [--focus "…"] [--theme THEME] [--attach] [--native] [--out DIR]
```

The header shows where diagrams will be drawn (**Visio desktop — drawing live**, or **Native .vsdx**
when Visio isn't installed) and which AI is configured. Then four steps:

**1 · Where is the code?** Paste any folder: a single repo or a parent folder holding many repos
(quotes and `~` are fine). Recent folders are offered first. The scan finds every repo (by `.git`,
manifests, Dockerfiles, compose or IaC files) and shows a table: name, stack, infrastructure
(cloud, Docker, CI) and the diagram it suggests. With several repos you tick the ones to include.

**2 · What should we draw?** The best-fitting diagram type is starred: architecture, cloud,
C4 context/container, deployment, data flow, pipeline, ERD, flowchart, swimlane, network, state,
org, mind map. Optionally type a focus: *"only the ingestion path"*, *"show the Kafka topics"*.

**3 · Explore the code.** Choose how:

| Option | What happens |
|---|---|
| **AI agent** | Your model explores the repo with read-only tools while a live feed shows each step (📂 browse, 📄 read, 🔎 search). It reads entrypoints, configs, IaC, compose files, routes, ORM models and CI, then drafts the diagram, checks it against the ground rules and fixes findings before handing it over. Ctrl+C stops it. |
| **Set up an AI provider** | The provider wizard (below). |
| **Hand off to my AI coding app** | Shown when Claude Code, Gemini CLI, Codex or Copilot CLI is installed: registers the visio MCP server with it and launches it on your repo with a ready prompt. |
| **Quick draft without AI** | A deterministic draft from the static scan. |

You then see the draft as an outline (groups, nodes, technologies) before anything is drawn.

**4 · Draw.** Pick a theme (the recommended one is starred) and the diagram is drawn: live in
Visio, or as `.vsdx` + preview opened in your browser. A summary shows files, counts and any rule
suggestions.

### Refine by chatting

At the `✎` prompt, describe a change in plain words. The agent keeps its context from exploring,
so it can add things it saw in the code:

```
✎ group the three databases into a Data tier
✎ add the Stripe webhook the orders service receives
✎ make the orders API the focus and use the aws theme
```

Each change redraws the diagram (in place in Visio). Commands:

| Command | |
|---|---|
| `/theme [name]` | switch theme (picker when no name) |
| `/layout [name]` | `flowchart-lr`, `flowchart-tb`, `swimlane-lr`, `swimlane-tb`, `tree-tb`, `tree-lr`, `radial`, `circular`, `grid` |
| `/export png\|svg\|pdf\|html` | export the current diagram |
| `/open` | open the file (Visio, or the HTML preview) |
| `/spec` | show the spec as JSON |
| `/save [file]` | save the spec; redraw later with `visio-ai render file.json` |
| `/lint` | rule findings for the current spec |
| `/undo` | back to the previous version |
| `/new` | draw another diagram of the same code |
| `/help`, `/quit` | |

## Commands

| Command | |
|---|---|
| `visio-ai draw PATH` | Explore and draw without questions. Flags: `--type`, `--focus`, `--provider`, `--model`, `--offline`, `--save-spec FILE` |
| `visio-ai render SPEC.json` | Draw a saved spec (output next to the spec unless `--out`) |
| `visio-ai scan PATH` | Repo profile table; `--json` for machine output; `--digest` prints exactly what the AI is given |
| `visio-ai setup` | Provider wizard |
| `visio-ai icons [status\|install\|remove]` | Official cloud icon packs, see [Cloud icons](cloud-icons.md) |
| `visio-ai handoff PATH --tool claude\|gemini\|codex\|copilot` | Register the MCP server with that app and launch it; `--type`, `--focus` |
| `visio-ai doctor` | Check Visio, provider, icons, previews |
| `visio-ai themes` | The themes with their palettes |
| `visio-ai kinds [--provider azure\|aws\|gcp]` | Shape kinds |
| `visio-ai rules TYPE [--provider …]` | Ground rules for a diagram type |
| `visio-ai examples` | Draw every example spec |
| `visio-ai mcp` | Run the MCP server on stdio |

Output flags (studio, `draw`, `render`, `examples`):

| Flag | |
|---|---|
| `--theme NAME` | `professional`, `azure`, `aws`, `gcp`, `c4`, `blueprint`, `dark`, `monochrome` |
| `--out DIR` | output folder (default `Documents/visio-mcp`, or `VISIO_MCP_OUT`) |
| `--attach` | draw into the Visio window you already have open |
| `--no-live` | use a hidden Visio instead of drawing in front of you |
| `--native` | never use Visio; write `.vsdx` + previews |
| `--format F` | extra exports, repeatable: `png`, `svg`, `pdf`, `html` |
| `--no-open` | don't open the preview afterwards |

Exit codes: `0` success, `1` a readable error (printed with a hint), `2` the studio needs an
interactive terminal, `130` cancelled.

## AI providers

`visio-ai setup` asks for the provider, credentials and model, offers to test the connection with
a one-word request, and saves to your user config file:

| OS | Config file |
|---|---|
| Windows | `%APPDATA%\visio-mcp\config.toml` |
| macOS | `~/Library/Application Support/visio-mcp/config.toml` |
| Linux | `$XDG_CONFIG_HOME/visio-mcp/config.toml` (or `~/.config/…`) |

The file is written with owner-only permissions. A key from the environment is never copied into
it.

| Provider | Environment | Default model | Notes |
|---|---|---|---|
| Claude (Anthropic) | `ANTHROPIC_API_KEY` | `claude-opus-5-5` | Also offered: `claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-fable-5-1`. Adaptive thinking, prompt caching. |
| Google Gemini | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | `gemini-2.5-pro` | |
| Azure OpenAI | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, optional `AZURE_OPENAI_API_VERSION`; `AZURE_OPENAI_API_KEY`, or none to use your Azure sign-in | your deployment | No key? It signs in with Entra ID (`az login`, VS Code, managed identity); your account needs the **Cognitive Services OpenAI User** role. The portal's `…/openai/v1` endpoint URL works as-is. |
| OpenAI | `OPENAI_API_KEY` | `gpt-5` | |
| Ollama | a local server on `localhost:11434` (`OLLAMA_HOST`) | `qwen3:latest` | Pick any pulled model with tool calling. |

What the agent can do: list folders, read files, search with regex and find files, all inside the
folders you chose. Path traversal and symlinks out of the repo are refused, private keys and
binaries are never read, and secret-looking values (keys, tokens, passwords, connection strings,
`.env` values) are masked before the model sees them. It never writes files or runs code.

## Hand off to your AI coding app

```powershell
visio-ai handoff C:\code\shop --tool claude --type cloud --focus "the ingestion path"
```

| App | Where the server is registered |
|---|---|
| Claude Code | `claude mcp add -s user visio -- …` |
| Gemini CLI | `~/.gemini/settings.json` → `mcpServers.visio` |
| OpenAI Codex CLI | `~/.codex/config.toml` → `[mcp_servers.visio]` |
| GitHub Copilot CLI | `~/.copilot/mcp-config.json` → `mcpServers.visio` |

Existing settings are kept; only the `visio` entry is replaced. The app then starts in your repo
with a prompt that tells it to explore, read the ground rules and draw with the visio tools.

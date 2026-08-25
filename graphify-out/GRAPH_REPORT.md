# Graph Report - ARJUN  (2026-08-26)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 399 nodes · 807 edges · 20 communities (17 shown, 3 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 55 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `407a8d6b`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- orchestrator.py
- VercelService
- telegram_handler.py
- Orchestrator
- MemoryService
- SecretStore
- ._get_repository
- TelegramHandler
- .generate_text
- GitHubService
- Settings
- ProjectRegistry
- BaseAgent
- github_service.py
- ProjectRoute
- main.py
- ChatResponse
- agents/__init__.py
- services/__init__.py
- utils/__init__.py

## God Nodes (most connected - your core abstractions)
1. `Orchestrator` - 36 edges
2. `BaseAgent` - 35 edges
3. `VercelService` - 27 edges
4. `GitHubService` - 27 edges
5. `TelegramHandler` - 26 edges
6. `MemoryService` - 25 edges
7. `ProjectManager` - 24 edges
8. `Settings` - 23 edges
9. `SecretStore` - 22 edges
10. `build_application()` - 17 edges

## Surprising Connections (you probably didn't know these)
- `Orchestrator` --uses--> `VercelError`  [INFERRED]
  agents/orchestrator.py → services/vercel_service.py
- `Orchestrator` --uses--> `VercelService`  [INFERRED]
  agents/orchestrator.py → services/vercel_service.py
- `VercelService` --uses--> `Settings`  [INFERRED]
  services/vercel_service.py → config/settings.py
- `BaseAgent` --uses--> `Settings`  [INFERRED]
  agents/base.py → config/settings.py
- `GitHubService` --uses--> `Settings`  [INFERRED]
  services/github_service.py → config/settings.py

## Import Cycles
- None detected.

## Communities (20 total, 3 thin omitted)

### Community 0 - "orchestrator.py"
Cohesion: 0.07
Nodes (38): CoderAgent, CoderOutput, CommitMessage, GeneratedFile, BaseModel, Implementation/code-generation agent., A complete repository file emitted by the coder., Single-line commit summary for the generated files. (+30 more)

### Community 1 - "VercelService"
Cohesion: 0.08
Nodes (24): EnvironmentSyncResult, Any, RuntimeError, Make an API request and turn provider errors into safe exceptions., Find the configured project or create/link it to the GitHub repository., Normalize a Vercel project response., Convert a GitHub repository name into a valid stable Vercel project name., Normalize a GitHub URL or full name to the Vercel owner/repository format. (+16 more)

### Community 2 - "telegram_handler.py"
Cohesion: 0.07
Nodes (23): LLMAgentError, Raised when the LLM cannot produce a usable response., Interpret an in-memory OGG voice note., InteractionBroker, InteractionTimeout, PendingQuestion, Small per-user question broker for Telegram human-in-the-loop decisions., Raised when the user does not answer a blocking build question in time. (+15 more)

### Community 3 - "Orchestrator"
Cohesion: 0.09
Nodes (24): OrchestrationError, OrchestrationResult, Orchestrator, AskUserCallback, Run the actual workflow after the repository queue grants access., Raised when a task cannot safely reach GitHub., GitHub delivery plus the optional Vercel deployment result., Coordinate the specialized agents and GitHub service. (+16 more)

### Community 4 - "MemoryService"
Cohesion: 0.11
Nodes (16): MemoryService, _now(), Connection, Durable task history and verified lessons for Arjun. The memory store is…, Persist the terminal result without storing generated source code., Create a stable, secret-safe fingerprint for a recurring failure., Upsert one verified failure lesson, increasing its recurrence count., Return a sortable UTC timestamp. (+8 more)

### Community 5 - "SecretStore"
Cohesion: 0.13
Nodes (15): Fernet, Connection, RuntimeError, Encrypted storage for user-supplied application environment variables., Read a key, preferring a runtime environment value over encrypted storage., Return only requested values; never expose the complete secret store., Encrypt and persist a validated allow-list of user-supplied values., Parse only requested KEY=value lines without logging their values. (+7 more)

### Community 6 - "._get_repository"
Cohesion: 0.08
Nodes (18): GitHubPromotionResult, GitHubWriteResult, Any, Reject absolute or parent-traversing repository paths., Fetch current refs and create the agent branch from the configured base if…, Write files sequentially, refreshing the branch and each file SHA before…, Verify repository access without touching any remote state., Links returned after a successful GitHub write. (+10 more)

### Community 7 - "TelegramHandler"
Cohesion: 0.17
Nodes (15): DEFAULT_TYPE, Message, Handle .txt file uploads — read the file and treat its content as a coding…, Run orchestration and edit one progress message through each phase., Authenticate users, report progress in-place, and route tasks., Send a blocking question and wait for the user's next authorized message., Route a message to a waiting task instead of accidentally starting a new task., Log framework-level errors without leaking secrets to Telegram. (+7 more)

### Community 8 - ".generate_text"
Cohesion: 0.15
Nodes (13): Any, RuntimeError, Generate text with exponential backoff and jitter for transient failures., Generate, extract, and validate a JSON response against a Pydantic model., Shrink reserved completion tokens so prompt + max_tokens fits the TPM limit., BaseException, ModelT, parse_json_response() (+5 more)

### Community 9 - "GitHubService"
Cohesion: 0.13
Nodes (14): GitHubService, Open a PR from the agent branch, when an operator explicitly requests it., Release the PyGithub HTTP client., Perform safe branch creation and file updates without blocking Telegram., ProjectManager, ProjectRecord, ProjectRuntime, AskUserCallback (+6 more)

### Community 10 - "Settings"
Cohesion: 0.14
Nodes (11): Application configuration package., get_settings(), BaseModel, Validated environment-backed application settings., Runtime configuration for the Telegram developer bot., Return the process-wide immutable-by-convention settings object., Require the GitHub owner/repository format., Load and validate settings from the process environment. (+3 more)

### Community 11 - "ProjectRegistry"
Cohesion: 0.21
Nodes (7): ProjectRegistry, Connection, Return all registered project identities., Insert or update a project mapping., Remember the Vercel identity created/found for a project., Store project aliases and deployment identities in the durable state DB., Normalize a human project name into a safe alias/repository name.

### Community 12 - "BaseAgent"
Cohesion: 0.22
Nodes (8): BaseAgent, Shared LLM client wrapper and structured-response primitives., Base class for agents with retrying text and multimodal generation., Close the underlying async client., ProjectRouterAgent, Project-intent routing for new builds and edits to registered projects., Select a registered project or derive a new project name from user intent., Persistent project registry and per-project runtime construction.

### Community 13 - "github_service.py"
Cohesion: 0.20
Nodes (7): GitHubRepositoryCreation, Non-blocking wrapper around PyGithub branch and file operations., Create and initialize a repository under the configured GitHub owner., Create a new initialized repository without blocking the Telegram loop., List bounded repository metadata visible to the authenticated GitHub user., Discover existing repositories without changing GitHub state., Identity of a repository created for a new Arjun project.

### Community 14 - "ProjectRoute"
Cohesion: 0.29
Nodes (5): ProjectRoute, BaseModel, LLM classification of the requested project target., Route before planning so repository and Vercel context are correct., Match a router key/name against freshly discovered GitHub repositories.

### Community 15 - "main.py"
Cohesion: 0.33
Nodes (6): Application, build_application(), main(), Application entry point for the autonomous Telegram developer bot., Construct the Telegram application and all dependency-injected services., Validate configuration and start long-polling.

### Community 16 - "ChatResponse"
Cohesion: 0.67
Nodes (3): ChatResponse, RuntimeError, Raised when the user makes conversation instead of a coding task.

## Knowledge Gaps
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Orchestrator` connect `Orchestrator` to `orchestrator.py`, `VercelService`, `telegram_handler.py`, `MemoryService`, `SecretStore`, `TelegramHandler`, `GitHubService`, `main.py`?**
  _High betweenness centrality (0.192) - this node is a cross-community bridge._
- **Why does `GitHubService` connect `GitHubService` to `orchestrator.py`, `Orchestrator`, `._get_repository`, `Settings`, `BaseAgent`, `github_service.py`, `main.py`?**
  _High betweenness centrality (0.160) - this node is a cross-community bridge._
- **Why does `TelegramHandler` connect `TelegramHandler` to `telegram_handler.py`, `Orchestrator`, `MemoryService`, `Settings`, `main.py`, `ChatResponse`?**
  _High betweenness centrality (0.151) - this node is a cross-community bridge._
- **Are the 17 inferred relationships involving `Orchestrator` (e.g. with `CoderAgent` and `CoderOutput`) actually correct?**
  _`Orchestrator` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `BaseAgent` (e.g. with `Settings` and `CoderAgent`) actually correct?**
  _`BaseAgent` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `VercelService` (e.g. with `Orchestrator` and `ProjectManager`) actually correct?**
  _`VercelService` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `GitHubService` (e.g. with `Orchestrator` and `Settings`) actually correct?**
  _`GitHubService` has 4 INFERRED edges - model-reasoned connections that need verification._
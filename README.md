# LLM-Powered NPCs with Persistent Memory

A capstone prototype in which Arthur, a medieval village guard, remembers player-provided facts across conversations and backend restarts. Python and FastAPI serve a local chat API and a buildless browser interface. Ollama runs `qwen3:8b` locally; SQLite stores conversations and explicitly generated memory summaries. No API key or hosted model service is required.


## Architecture and implementation status

For each chat request, the backend reads the exact player/NPC pair's latest 10 messages, relevant older user excerpts, and optional saved summaries from one SQLite snapshot. It closes the read transaction before calling Ollama, applies narrow source-based reply safeguards, and saves both sides of the successful exchange atomically.


| Component | Implementation |
| --- | --- |
| backend/main.py | FastAPI /, /health, /chat; unchanged chat JSON format |
| backend/memory_store.py | Persistent history, isolation, historical keyword retrieval, consistent context reads |
| backend/summary_store.py, summarizer.py | Versioned, source-validated extractive summaries; explicit developer CLI |
| backend/retention_policy.py, reply_safety.py | Personal-fact eligibility, bounded attributed overviews, narrow conflict safeguards |
| backend/demo.py, web/, run_demo.ps1 | Opt-in localhost browser demo and read-only memory inspector |
| backend/summary_audit.py | Read-only eligibility audit; no repair/delete mode |
| backend/tests/ | Automated tests with disposable databases and mocked model responses |

Historical retrieval, explicit summaries, and the browser prototype are implemented. The Unity village client has been added and run successfully; Unity has communicated with the documented FastAPI `/chat` endpoint and displayed an NPC response. Persistent memory remains the responsibility of the backend. Aftab's separate evaluation work remains outstanding. Controlled forgetting and semantic/vector retrieval are not implemented.


## Software requirements

- Python **3.12** (validated with 3.12.10), including `venv` and SQLite support.
- Git, Ollama, the `qwen3:8b` model, and a modern browser such as Chrome.
- Windows PowerShell for the supplied demo launcher. The Python backend can also be launched directly with Uvicorn.
- Enough local memory/disk for Qwen3 8B; the model download is several GB and generation speed depends on your hardware. Tests do not require the model.

The five direct Python dependencies are pinned in `backend/requirements.txt`. SQLite, the test runner, and the frontend need no additional packages or Node build step.


## Install and start Ollama

Install Ollama from [ollama.com](https://ollama.com/). Then use PowerShell:


```
ollama list
# If qwen3:8b is absent, download it explicitly:
ollama pull qwen3:8b
```

Check `http://127.0.0.1:11434/api/version`. If Ollama is not already serving, run `ollama serve` in a separate terminal and leave it running. Do not start a second server when the Ollama desktop service is already available.


## Install the backend

From the directory in which you want the checkout:


```
git clone https://github.com/karangit-hub/npc-memory-capstone.git
Set-Location .\npc-memory-capstone\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

For an ordinary backend instance, from `backend`:


```
.\.venv\Scripts\python.exe -B -m uvicorn main:app --host 127.0.0.1 --port 8000
```

This uses or creates `backend/conversation_memory.sqlite3` unless `NPC_DATABASE_PATH` is explicitly set. It preserves existing messages. Summary context and demo routes default to off. For safe personal testing, use the separate demo database below rather than an existing conversation database.

`POST /chat` accepts `{"player_id":"karan","npc_id":"Arthur","message":"Hello"}` and returns `{"npc_id":"Arthur","reply":"..."}`. IDs are case-sensitive.


## Run the isolated browser demo

From `backend`, with Ollama running:


```
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1
Start-Process "http://127.0.0.1:8001/demo"
```

The URL is **[http://127.0.0.1:8001/demo](http://127.0.0.1:8001/demo)**. Run `Start-Process` in another terminal while the launcher is running. The launcher binds only to loopback, enables summary context, and creates/reuses `npc-memory-browser-demo/demo.sqlite3` beside the checkout. It never resets history or migrates the original database. An explicit alternative is `-DatabasePath "C:\path\to\demo.sqlite3" -Port 8002`.

Select Karan, Rajan, or a custom player and Arthur or another NPC ID. Use Send or Enter; Shift+Enter adds a newline. Clear view only clears the displayed bubbles. The connection indicator reports backend/Ollama availability.

Open **Memory inspector** and refresh the preview to see actual recent message IDs, keyword excerpts, persisted summary entries, source IDs, eligibility decisions, and effective summary context. This previews the next request using the draft; it is not a trace of the previous model call. The inspector is read-only and provides no database-reset or summary-generation API.


## Historical retrieval and explicit summary generation

Older user messages remain in SQLite after leaving the recent 10-message window. Keyword retrieval ranks shared normalized, non-stopword tokens and returns at most three excerpts, with a 1,500-character total excerpt budget. It requires shared words and does not implement semantic search.

To test summaries, tell Arthur personal facts, then have at least six unrelated exchanges after the last fact. In another PowerShell terminal, from `backend`:


```
$demoDb = Join-Path (Split-Path (Get-Location).Path -Parent) '..\npc-memory-browser-demo\demo.sqlite3'
.\.venv\Scripts\python.exe -B .\summarizer.py --db $demoDb --player-id karan --npc-id Arthur
```

Use the exact custom path instead if you supplied `-DatabasePath`. Repeat until the result is `status: noop`, then refresh the inspector and ask about the facts. Generation is **explicit only**; ordinary chat never creates summaries. The CLI adds summary tables only to an existing disposable database and refuses the original database path. Stored statements are complete user messages with source IDs and hashes, not invented model paraphrases. Application rules reject general questions such as the blacksmith question even if the model labels them personal memories.

Stop the backend with Ctrl+C. Restart the same launcher and reuse the same database to verify persistence; switch players to verify isolation. Stop Ollama with Ctrl+C only if you started that separate process yourself.


## Run automated validation

From `backend`:


```
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B -m pip check
```

Tests use temporary SQLite databases and mocked Ollama responses. They cover persistence, isolation, retrieval, source validation, summary publication, concurrent reads, attribution, API compatibility, and browser routes. A passing suite is not a guarantee of live-model answer accuracy.


## Known limitations and data safety

- Qwen3 sometimes abstains even when a supporting home-location fact is in summary context. This remains unresolved. Source-based overview safeguards do not repair every specific-fact answer.
- Keyword retrieval misses synonyms and some paraphrases. Personal-fact eligibility uses conservative English grammar rules, with false negatives and possible misinterpretations of complex language.
- Speaker/conflict safeguards cover bounded overviews, exact copied user statements, and simple conflicting claims. Complex paraphrases, conflicts, hallucination, and prompt injection remain model-behavior limitations.
- Summaries retain at most 16 complete source messages, 600 characters each, and 4,000 serialized context characters. Capacity errors do not evict data; ignored sources are not automatically replayed. No forgetting is performed.
- Local demo routes are development tools, not production authentication. Player IDs scope data but are not authenticated identities. Keep the server on `127.0.0.1`; this is not a public multiplayer service.
- Databases, logs, environments, secrets, and local reports are excluded from Git. Existing invalid summary rows are filtered and auditable; they are not physically repaired or deleted automatically.

See the backend guide for full algorithms, configuration, schema, test coverage, safe audit commands, and the approval-based proposal for correcting a previously misclassified derived summary entry.

## Unity game environment and FastAPI integration

The Unity front end and the existing FastAPI backend are connected. In the local integration, Unity sent a player message to FastAPI and displayed the NPC's response successfully. Unity handles the game world, movement, interaction, and dialogue display; FastAPI, SQLite, and Ollama continue to handle NPC replies and persistent memory.

### What the Unity scene contains

The village scene includes Arthur's home, the Lantern Inn, a blacksmith workshop, paths and a square, a fountain, benches, trees, porches, a forge, an anvil, a notice board, and an inn table. Its editor builder creates persistent materials under `Assets/Materials`, chooses a shader compatible with the active Built-in or URP renderer, and sets a procedural sky, ambient color gradient, and directional lighting.

The scene also includes a third-person player controller, orbit camera, dialogue panel, interaction prompt, inspectable objects, and overhead NPC name labels. Use **WASD** to move, point at a nearby NPC and press **E** or left-click to talk, press **E** near a prop to inspect, hold right mouse and drag to orbit the camera, and press **Escape** to close dialogue.

| Character | Stable `npc_id` | Role |
| --- | --- | --- |
| Arthur | `Arthur` | Village elder |
| Mira the Smith | `Blacksmith` | Blacksmith |
| Tomas | `TavernKeeper` | Innkeeper |
| Lena | `VillageGuard` | Guard |

NPCs wander locally and pause between walks. The NPC being spoken to stops while the dialogue panel is open, including while it waits for the backend response, then resumes when the panel closes. The supplied figures are 3D humanoid blockout meshes built from Unity primitives; they do not include rigged human models or animation clips.

### Start from GitHub and create/open the Unity project

The Unity `Assets` files are now included in this repository. They are source assets, not a standalone Unity project. Follow the path that matches the files committed to the repository:

- **If the Unity folder contains `Assets`, `Packages`, and `ProjectSettings`:** clone/download the repository, open Unity Hub, choose **Add/Open project**, and select that Unity project folder.
- **If the repository contains only the Unity `Assets` folder:** install Unity Hub and a compatible Unity Editor, then in Unity Hub choose **New project → 3D (URP)**. Give it a project name such as `NPCMemoryVillage`. Copy the repository's Unity `Assets` folder into the new project's root and merge it with the template `Assets` folder. Do not open the `Assets` folder itself as a Unity project. See Unity's [create-a-project guide](https://docs.unity3d.com/Manual/create-first-project.html) and [URP setup guide](https://docs.unity3d.com/Packages/com.unity.render-pipelines.universal@17.0/manual/creating-a-new-project-with-urp.html).

Wait for Unity to import and compile. The controller scripts use the legacy Input Manager API. In **Edit → Project Settings → Player → Active Input Handling**, select **Both** or **Input Manager (Old)**, then restart Unity if it requests it. See Unity's [input handling guide](https://docs.unity3d.com/Manual/UIE-Runtime-Event-System.html).

If `Assets/Scenes/Village.unity` is already in the repository, open it. If it is absent, choose **NPC Memory → Build Demo Village** from Unity's menu; the builder creates and saves `Assets/Scenes/Village.unity` and the materials. Save the scene after generation.

### Connect the scene to FastAPI

1. In the Unity Project window, choose **Assets → Create → NPC Memory → Backend Config** and name the asset `BackendConfig`.
2. Set its URL, route, field names, and player ID. For the isolated browser demo, use the values below. The documented API request is `POST /chat` with `{"player_id":"karan","npc_id":"Arthur","message":"Hello"}`; the API returns `{"npc_id":"Arthur","reply":"..."}`.

   | `BackendConfig` field | Value |
   | --- | --- |
   | `baseUrl` | `http://127.0.0.1:8001` |
   | `chatPath` | `/chat` |
   | `playerIdField` | `player_id` |
   | `npcIdField` | `npc_id` |
   | `messageField` | `message` |
   | `replyField` | `reply` |
   | `playerId` | `karan` for the prior Karan/Arthur test |

   These settings must match the request schema in FastAPI `/docs`. The Unity client has a reply-field fallback, but setting `replyField` to `reply` matches the documented response directly.
3. In the Unity Hierarchy, select **NPC Backend Client** and drag `BackendConfig` into its **Config** field. The startup player-ID screen needs this asset assigned, even when you only want to explore. The FastAPI server can stay stopped until you want backend replies.
4. At Play, the startup screen is prefilled with the last player ID used on this computer or the `BackendConfig` value. Click the field, enter the desired ID, and choose **Enter Village**. The chosen ID is sent with every chat request and saved locally for the next run.

### Start Ollama and FastAPI

1. Start Ollama and confirm the `qwen3:8b` model is installed with `ollama list`. If it is missing, run `ollama pull qwen3:8b`. Ensure the service is available at `http://127.0.0.1:11434`.
2. Start the backend in a separate terminal. On Windows, from the repository's `backend` directory, run the demo launcher and leave it running:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1
   ```

   This starts the isolated demo API at port 8001 and uses `npc-memory-browser-demo/demo.sqlite3`. Confirm it is available at `http://127.0.0.1:8001/docs`.
3. On macOS, the repository's direct Uvicorn option can be used from `backend` if the Windows-only demo launcher is unavailable:

   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```

   For this direct launch, set Unity's `baseUrl` to `http://127.0.0.1:8000`. It uses the regular configured backend database (by default `backend/conversation_memory.sqlite3`); it is separate from the isolated browser-demo database on port 8001, and summary context may be disabled. Use the same API/database where the memories to test were recorded.
4. Keep Unity and the backend on the same computer when using `127.0.0.1`. Press **Play**, enter `karan`, approach Arthur, and send a message. The Unity chat panel displays FastAPI's returned reply. The backend's SQLite memory persists independently of Unity sessions.

### Test player and NPC memory scopes

To reuse Karan's earlier test, connect Unity to the same backend database and enter the exact case-sensitive player ID `karan`; talk to Arthur, whose `npc_id` is `Arthur`. Unity sends both IDs with every request. The backend scopes the conversation by the player/NPC pair. A different player ID selects a separate memory scope. Mira, Tomas, and Lena use separate NPC IDs and therefore separate histories; facts told to Arthur are not automatically shared with them. IDs are memory keys, not authentication, and Unity does not infer them from a real-world name or sign-in.

The local Unity-to-FastAPI chat round trip has been completed successfully: a message sent in Unity received and displayed an NPC response from FastAPI. The backend's persistence and player-isolation tests are documented above. To verify a particular memory in Unity, use the same backend database, player ID, and NPC ID that contain that memory, then ask the NPC about it after reopening the conversation.

### Troubleshooting and project notes

- **404:** confirm the route is `/chat` and that Unity's `baseUrl` uses the port of the running backend.
- **422:** compare `playerIdField`, `npcIdField`, and `messageField` with FastAPI `/docs`.
- **Connection refused or timeout:** start FastAPI and Ollama; confirm Unity and the server use the same machine/address.
- **The NPC answers “I don't know”:** check that the player ID, NPC ID, database, and summary-context mode match the memory test.
- **Input errors:** set Active Input Handling to **Both** or **Input Manager (Old)**.
- Unity UI uses standard Unity UI `Text`, not TextMeshPro. A `Can't Generate Mesh, No Font Asset has been assigned` warning from `UnityEditor.HandleUtility.BeginHandles` does not indicate a FastAPI failure when the scene builds and UI text displays. `URP Global Settings Asset has been created` is informational.

Keep Unity source such as `Assets`, `Packages`, and `ProjectSettings` in GitHub; exclude generated `Library`, `Temp`, `Obj`, and build output folders. Preserve Unity `.meta` files so asset references remain stable.

### Suggested status paragraph for Architecture and implementation status

> A Unity village client and scene builder have been added and run successfully. The Unity client has successfully communicated with the documented FastAPI `/chat` endpoint and displayed an NPC response. Dialogue memory remains in the existing backend, scoped by player ID and NPC ID. Aftab's separate evaluation work remains outstanding. Controlled forgetting and semantic/vector retrieval are not implemented.

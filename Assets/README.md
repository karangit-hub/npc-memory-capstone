# Unity Assets — persistent-memory NPC village

This is the Unity `Assets` folder for the village client. It includes a generated playable scene, source scripts, NPC backend config, materials, URP settings/profile assets, and Unity `.meta` files. It is not a complete Unity project; create a Unity project first and import/merge this folder into the project root.

## Requirements

- Unity Hub and a Unity Editor compatible with the APIs used by the scripts.
- A project created with the **3D (URP)** template, including the Unity UI package.
- FastAPI and Ollama for live NPC replies. The Unity environment and local NPC wandering can run without the backend, but live dialogue requires the backend services.

## Import and open the village

1. Create or open a 3D URP Unity project.
2. Close Unity. Copy this `Assets` folder into the Unity project root and merge it with the project's `Assets` folder. Preserve all `.meta` files so scene references and asset GUIDs remain stable.
3. Reopen Unity and wait for asset import and script compilation.
4. If Unity reports input API issues, open **Edit → Project Settings → Player → Active Input Handling**, choose **Both** or **Input Manager (Old)**, then restart Unity if prompted.
5. Open `Assets/Scenes/Village.unity` and press **Play**. The scene is included in this package. The **NPC Backend Client** already references `Assets/Config/BackendConfig.asset`.
6. If you need to regenerate the scene, choose **NPC Memory → Build Demo Village**. The builder creates or reuses the config asset and assigns it to the new client.

## Backend setup

The client posts to FastAPI `POST /chat` using this request:

```json
{"player_id":"karan","npc_id":"Arthur","message":"Hello"}
```

The backend returns a reply in this format:

```json
{"npc_id":"Arthur","reply":"..."}
```

The included `Assets/Config/BackendConfig.asset` contains the matching field names:

| Config field | Included value |
|---|---|
| `chatPath` | `/chat` |
| `playerIdField` | `player_id` |
| `npcIdField` | `npc_id` |
| `messageField` | `message` |
| `replyField` | `reply` |
| `playerId` | `karan` |
| `baseUrl` | `http://127.0.0.1:8001` |

The base URL must match the server and database you intend to use. For the ordinary local FastAPI server on port 8000, select `BackendConfig.asset` and set Base URL to `http://127.0.0.1:8000`. The Windows browser-demo launcher uses port 8001 and an isolated demo database. These servers can contain different conversation histories.

From the backend directory, the ordinary local server can be started on macOS/Linux with:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Start Ollama separately, ensure the backend's `qwen3:8b` model is available, and leave both services running while testing live NPC dialogue. On Windows, the isolated browser demo can be started using `run_demo.ps1`; its default API port is 8001. Consult the main repository README for the full backend installation and demo instructions.

When Play starts, enter the player ID on the Unity screen. Use the exact same case-sensitive ID, NPC ID, and backend database to continue a previous conversation. The player ID selects a memory namespace; it is not authentication. The Unity config is assigned in the included scene, so no manual asset creation is required.

## NPCs and controls

| Character | Backend `npc_id` | Unity role |
|---|---|---|
| Arthur | `Arthur` | Village elder |
| Mira the Smith | `Blacksmith` | Blacksmith |
| Tomas | `TavernKeeper` | Innkeeper |
| Lena | `VillageGuard` | Guard |

Each NPC wanders locally and pauses while their dialogue panel is open. WASD moves the player; point at a nearby NPC and press **E** or left-click to talk; **E** also selects the nearest NPC in range; hold the right mouse button and drag to orbit the camera; Escape closes the dialogue. The figures are blockout meshes made from Unity primitives, not rigged human models.

## Test coverage and boundaries

The live Unity client has been used to send a chat message to FastAPI and display the returned reply. Unity can exercise the backend's normal chat path, continued messages, and memory separation by player/NPC ID. It can consume saved summaries when the backend is configured to use them, but summary generation is an explicit backend CLI operation and is not triggered by Unity.

The backend's automated tests separately cover malformed requests, model-error handling, database persistence and isolation, retrieval and summary edge cases, reply-safety rules, and browser-demo routes. Those backend-only test fixtures and internal scenarios are not all actions exposed by the Unity interface. The backend currently uses a friendly-guard system prompt for every NPC ID; IDs still isolate memory, but distinct NPC role/persona fields are not sent to FastAPI yet.

## Troubleshooting

- **Connection refused or timeout:** start FastAPI and Ollama; check Base URL and port in `BackendConfig.asset`.
- **HTTP 404:** check the host, port, and `/chat` route.
- **HTTP 422:** confirm the three request field names match FastAPI's `/docs`.
- **No old memory:** verify the exact player ID and NPC ID and connect to the same database used earlier. `Arthur` and `Blacksmith` are separate histories.
- **No movement/input:** set Active Input Handling to Both or Input Manager (Old).
- **Pink materials or missing URP components:** open the Assets folder in a 3D URP project with the Universal Render Pipeline package installed.
- **Backend unavailable in chat:** the player screen can still open the village if the config asset is assigned, but generated dialogue requires FastAPI and Ollama.

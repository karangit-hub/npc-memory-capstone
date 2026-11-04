# NPC Memory Village — complete Unity Assets package

This package contains the Unity `Assets` folder, including the generated `Village.unity` scene, materials, scripts, backend configuration asset, and Unity `.meta` files. Create or open a Unity project first; this package is not a complete Unity project.

## Import and run

1. In Unity Hub, create a 3D (URP) project or open your existing project.
2. Close Unity, then copy this package's `Assets` folder into the project root and merge it with the project's existing `Assets` folder.
3. Reopen Unity and wait for import/compilation to finish. In **Edit → Project Settings → Player → Active Input Handling**, choose **Both** or **Input Manager (Old)** if movement/input does not respond, then restart Unity if prompted.
4. Open `Assets/Scenes/Village.unity` and press **Play**. The Backend Config asset is included and already linked to **NPC Backend Client**.
5. The included config defaults to `http://127.0.0.1:8001/chat`, player ID `karan`, and JSON fields `player_id`, `npc_id`, `message`, with response field `reply`. If you use the ordinary FastAPI server on port 8000, select `Assets/Config/BackendConfig.asset` and change Base URL to `http://127.0.0.1:8000`. Keep the selected port pointed at the database with the memories you want to test.
6. Start FastAPI and its model service (for this backend, Ollama) to test live NPC replies. You can enter the scene and explore with the backend stopped, but chat requests will fail until it is available.

If you rebuild the scene, choose **NPC Memory → Build Demo Village**. The builder preserves/creates `Assets/Config/BackendConfig.asset` and assigns it to the new NPC Backend Client.

## Controls and NPC IDs

- WASD to move; right mouse button + drag to orbit the camera.
- Point at a nearby NPC and press E or left-click to talk; Escape closes dialogue.
- Arthur uses `Arthur`; Mira uses `Blacksmith`; Tomas uses `TavernKeeper`; Lena uses `VillageGuard`. The backend scopes memory by the exact player ID and NPC ID pair. Use the same values and backend database to continue a conversation.
- NPCs wander locally and the person currently in dialogue pauses. Characters are primitive blockouts, not rigged human models.

The Unity source sends `POST /chat` with `player_id`, `npc_id`, and `message`. The project README documents the FastAPI request and reply format.

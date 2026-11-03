using UnityEngine;
[CreateAssetMenu(menuName="NPC Memory/Backend Config")]
public class BackendConfig : ScriptableObject
{
    public string baseUrl="http://127.0.0.1:8001", chatPath="/chat", playerId="karan";
    public string playerIdField="player_id", npcIdField="npc_id", messageField="message", replyField="response";
    public int timeoutSeconds=120;
}

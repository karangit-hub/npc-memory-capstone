using UnityEngine;
using UnityEngine.UI;
public class WorldInteractor : MonoBehaviour
{
    public Camera viewCamera;
    public float range = 4f;
    public DialoguePanel dialogue;
    public Text prompt;
    NPCIdentity pointed;
    void Update()
    {
        if (!PlayerIdPrompt.Ready) { if (prompt) prompt.text = ""; return; }
        if (dialogue && dialogue.IsOpen) { if (prompt) prompt.text = ""; return; }
        pointed = GetPointedNpc();
        NPCIdentity nearby = GetNearestNpc();
        if (prompt) prompt.text = nearby ? "E  Talk to " + nearby.displayName + "    •    Click to talk" : "";
        if (Input.GetKeyDown(KeyCode.E))
        {
            if (pointed && InRange(pointed)) { dialogue.Open(pointed); return; }
            if (nearby) { dialogue.Open(nearby); return; }
            WorldProp prop = GetPointedProp();
            if (prop) dialogue.ShowNotice(prop.displayName + ": " + prop.description);
        }
        if (Input.GetMouseButtonDown(0) && pointed && InRange(pointed)) dialogue.Open(pointed);
    }
    NPCIdentity GetPointedNpc()
    {
        if (!viewCamera || !Physics.Raycast(viewCamera.ScreenPointToRay(Input.mousePosition), out var hit, 100f)) return null;
        return hit.collider.GetComponentInParent<NPCIdentity>();
    }
    WorldProp GetPointedProp()
    {
        if (!viewCamera || !Physics.Raycast(viewCamera.ScreenPointToRay(Input.mousePosition), out var hit, 100f)) return null;
        return hit.collider.GetComponentInParent<WorldProp>();
    }
    NPCIdentity GetNearestNpc()
    {
        NPCIdentity best = null; float bestDistance = range;
        foreach (var npc in FindObjectsByType<NPCIdentity>(FindObjectsSortMode.None))
        {
            float d = Vector3.Distance(transform.position, npc.transform.position);
            if (d < bestDistance) { best = npc; bestDistance = d; }
        }
        return best;
    }
    bool InRange(NPCIdentity npc) => npc && Vector3.Distance(transform.position, npc.transform.position) <= range;
}

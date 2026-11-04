using UnityEngine;
public class NPCNameTag : MonoBehaviour
{
    public NPCIdentity identity;
    Camera view;
    GUIStyle style;
    Texture2D background;
    void Awake()
    {
        view = Camera.main;
        background = new Texture2D(1, 1);
        background.SetPixel(0, 0, new Color(.035f, .045f, .055f, .88f));
        background.Apply();
    }
    void OnGUI()
    {
        if (!identity) return;
        if (!view) view = Camera.main;
        if (!view) return;
        if (style == null)
        {
            style = new GUIStyle(GUI.skin.box)
            {
                alignment = TextAnchor.MiddleCenter,
                fontSize = 15,
                fontStyle = FontStyle.Bold,
                padding = new RectOffset(10, 10, 4, 4)
            };
            style.normal.textColor = Color.white;
            style.normal.background = background;
        }
        Vector3 p = view.WorldToScreenPoint(transform.position + Vector3.up * 2.85f);
        if (p.z <= 0) return;
        GUI.Label(new Rect(p.x - 75, Screen.height - p.y - 14, 150, 28), identity.displayName, style);
    }
    void OnDestroy() { if (background) Destroy(background); }
}

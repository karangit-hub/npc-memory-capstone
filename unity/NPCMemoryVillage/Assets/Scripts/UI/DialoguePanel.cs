using System.Text;
using UnityEngine;
using UnityEngine.UI;

public class DialoguePanel : MonoBehaviour
{
    public GameObject panel;
    public Text title, transcript, status;
    public InputField input;
    public Button sendButton;
    public ScrollRect scroll;

    NPCIdentity current;
    readonly StringBuilder log = new StringBuilder();

    public bool IsOpen => panel && panel.activeSelf;
    public static bool ChatOpen { get; private set; }
    public static NPCIdentity CurrentNPC { get; private set; }

    void Awake()
    {
        panel.SetActive(false);
        ChatOpen = false;
        sendButton.onClick.AddListener(Send);
    }

    void Update()
    {
        if (!panel.activeSelf) return;
        if (Input.GetKeyDown(KeyCode.Escape)) Close();
        else if (input != null && input.isFocused &&
                 (Input.GetKeyDown(KeyCode.Return) || Input.GetKeyDown(KeyCode.KeypadEnter))) Send();
    }

    public void Open(NPCIdentity npc)
    {
        current = npc;
        CurrentNPC = npc;
        log.Clear();
        title.text = npc.displayName + "  •  " + npc.role;
        status.text = "Conversation ready";
        panel.SetActive(true);
        ChatOpen = true;
        SetTranscript("Welcome.\n\nShare something with " + npc.displayName + ", or ask about a past conversation.");
        input.ActivateInputField();
        input.Select();
    }

    public void ShowNotice(string message)
    {
        panel.SetActive(true);
        current = null;
        CurrentNPC = null;
        title.text = "Village";
        status.text = "Explore the village";
        ChatOpen = true;
        SetTranscript(message);
    }

    public void Close()
    {
        panel.SetActive(false);
        ChatOpen = false;
        CurrentNPC = null;
        current = null;
    }

    public void Send()
    {
        if (input == null || string.IsNullOrWhiteSpace(input.text)) return;
        string message = input.text.Trim();
        input.text = "";
        log.AppendLine("You: " + message);
        SetTranscript(log.ToString());
        sendButton.interactable = false;
        status.text = "Waiting for reply…";

        if (current && NpcBackendClient.Instance && NpcBackendClient.Instance.config)
        {
            NPCIdentity speaking = current;
            NpcBackendClient.Instance.Send(speaking.npcId, message,
                answer => Finish(speaking.displayName + ": " + answer),
                error => Finish("Connection problem. Check FastAPI and the Backend Config URL.\n" + error));
        }
        else
        {
            string name = current ? current.displayName : "Villager";
            Finish(name + " (offline preview): I heard you. Connect the memory backend when you want to test persistent recall.");
        }
    }

    void Finish(string answer)
    {
        log.AppendLine(answer);
        SetTranscript(log.ToString());
        status.text = "Ready";
        sendButton.interactable = true;
        if (panel.activeSelf && input != null)
        {
            input.ActivateInputField();
            input.Select();
        }
    }

    void SetTranscript(string value)
    {
        transcript.text = value;
        if (scroll == null) return;
        Canvas.ForceUpdateCanvases();
        if (scroll.content != null) LayoutRebuilder.ForceRebuildLayoutImmediate(scroll.content);
        Canvas.ForceUpdateCanvases();
        scroll.verticalNormalizedPosition = 0f;
    }
}

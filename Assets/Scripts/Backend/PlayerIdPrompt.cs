using UnityEngine;
using UnityEngine.UI;
public class PlayerIdPrompt : MonoBehaviour
{
    public GameObject panel;
    public InputField playerIdInput;
    public Button confirmButton;
    public Text errorText;
    public static bool Ready { get; private set; }
    const string PreferenceKey = "NPCMemoryVillage.PlayerId";
    void Awake()
    {
        Ready = false;
        if (confirmButton) confirmButton.onClick.AddListener(Confirm);
    }
    void Start()
    {
        string configured = NpcBackendClient.Instance && NpcBackendClient.Instance.config
            ? NpcBackendClient.Instance.config.playerId : "karan";
        playerIdInput.text = PlayerPrefs.GetString(PreferenceKey, configured);
        panel.SetActive(true);
        playerIdInput.Select();
        playerIdInput.ActivateInputField();
    }
    public void Confirm()
    {
        string id = playerIdInput ? playerIdInput.text.Trim() : "";
        if (string.IsNullOrEmpty(id)) { errorText.text = "Enter a player ID to continue."; return; }
        if (!NpcBackendClient.Instance || !NpcBackendClient.Instance.config)
        { errorText.text = "Assign BackendConfig to NPC Backend Client first."; return; }
        NpcBackendClient.Instance.config.playerId = id;
        PlayerPrefs.SetString(PreferenceKey, id);
        PlayerPrefs.Save();
        errorText.text = "";
        Ready = true;
        panel.SetActive(false);
    }
}

using System.Text;using UnityEngine;using UnityEngine.UI;
public class DialoguePanel:MonoBehaviour
{
 public GameObject panel;public Text title,transcript,status;public InputField input;public Button sendButton;NPCIdentity current;readonly StringBuilder log=new StringBuilder();public bool IsOpen=>panel&&panel.activeSelf;public static bool ChatOpen {get;private set;}public static NPCIdentity CurrentNPC {get;private set;}
 void Awake(){panel.SetActive(false);ChatOpen=false;sendButton.onClick.AddListener(Send);}void Update(){if(panel.activeSelf&&Input.GetKeyDown(KeyCode.Escape))Close();}
 public void Open(NPCIdentity npc){current=npc;CurrentNPC=npc;log.Clear();title.text=npc.displayName+" — "+npc.role;transcript.text="They are here and ready to talk.\n\n";status.text="Connected to NPC memory";panel.SetActive(true);ChatOpen=true;input.ActivateInputField();}
 public void ShowNotice(string s){panel.SetActive(true);current=null;CurrentNPC=null;title.text="Village";transcript.text=s;status.text="Explore the village";ChatOpen=true;}
 public void Close(){panel.SetActive(false);ChatOpen=false;CurrentNPC=null;current=null;}
 public void Send(){if(string.IsNullOrWhiteSpace(input.text))return;string msg=input.text.Trim();input.text="";log.AppendLine("You: "+msg);transcript.text=log.ToString();sendButton.interactable=false;status.text="Thinking…";if(current&&NpcBackendClient.Instance&&NpcBackendClient.Instance.config){NpcBackendClient.Instance.Send(current.npcId,msg,a=>Finish(current.displayName+": "+a),e=>Finish("Backend unavailable. Start FastAPI and configure the client to use persistent NPC memory.\n"+e));}else{string who=current?current.displayName:"Villager";Finish(who+" (offline preview): I heard you. Connect the memory backend when you want to test persistent recall.");}}
 void Finish(string answer){log.AppendLine(answer);transcript.text=log.ToString();status.text="Ready";sendButton.interactable=true;input.ActivateInputField();}
}

using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
public class NpcBackendClient : MonoBehaviour
{
    public static NpcBackendClient Instance {get;private set;} public BackendConfig config;
    [Serializable] class Reply {public string response,reply,answer,message;}
    void Awake(){if(Instance&&Instance!=this){Destroy(gameObject);return;}Instance=this;DontDestroyOnLoad(gameObject);}
    public void Send(string npc,string message,Action<string> ok,Action<string> fail){StartCoroutine(Post(npc,message,ok,fail));}
    IEnumerator Post(string npc,string message,Action<string> ok,Action<string> fail)
    {
        if(!config){fail?.Invoke("Backend config is not assigned.");yield break;}
        var values=new Dictionary<string,string>{{config.playerIdField,config.playerId},{config.npcIdField,npc},{config.messageField,message}};
        string body="{"+string.Join(",",values.Select(x=>"\""+Esc(x.Key)+"\":\""+Esc(x.Value)+"\""))+"}";
        using(var req=new UnityWebRequest(config.baseUrl.TrimEnd('/')+"/"+config.chatPath.TrimStart('/'),"POST"))
        {req.uploadHandler=new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));req.downloadHandler=new DownloadHandlerBuffer();req.timeout=config.timeoutSeconds;req.SetRequestHeader("Content-Type","application/json");yield return req.SendWebRequest();if(req.result!=UnityWebRequest.Result.Success){fail?.Invoke(req.error+"\n"+req.downloadHandler.text);yield break;}string answer=Read(req.downloadHandler.text,config.replyField);if(string.IsNullOrEmpty(answer)){try{var r=JsonUtility.FromJson<Reply>(req.downloadHandler.text);answer=r.response??r.reply??r.answer??r.message;}catch{answer=req.downloadHandler.text;}}ok?.Invoke(string.IsNullOrEmpty(answer)?req.downloadHandler.text:answer);}
    }
    static string Esc(string s)=>s.Replace("\\","\\\\").Replace("\"","\\\"").Replace("\n","\\n").Replace("\r","\\r");
    static string Read(string j,string p){if(string.IsNullOrEmpty(p))return null;int i=j.IndexOf("\""+p+"\"",StringComparison.Ordinal);if(i<0)return null;i=j.IndexOf(':',i);if(i<0)return null;i++;while(i<j.Length&&char.IsWhiteSpace(j[i]))i++;if(i>=j.Length||j[i++]!='\"')return null;var b=new StringBuilder();bool e=false;for(;i<j.Length;i++){char c=j[i];if(e){b.Append(c=='n'?'\n':c);e=false;}else if(c=='\\')e=true;else if(c=='\"')return b.ToString();else b.Append(c);}return null;}
}

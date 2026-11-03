#if UNITY_EDITOR
using UnityEditor;using UnityEditor.SceneManagement;using UnityEngine;using UnityEngine.UI;using UnityEngine.EventSystems;using UnityEngine.Rendering;
public static class VillageBuilder
{
 static Material grass,wood,stone,roof,skin,iron,water,leaf;
 static string materialFolder="Assets/Materials";
 [MenuItem("NPC Memory/Build Demo Village")]
 public static void Build(){var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
  grass=Mat("Grass",new Color(.25f,.43f,.23f));wood=Mat("Timber",new Color(.38f,.22f,.12f));stone=Mat("Stone",new Color(.48f,.48f,.44f));roof=Mat("Roof",new Color(.55f,.22f,.16f));skin=Mat("Skin",new Color(.78f,.56f,.4f));iron=Mat("Iron",new Color(.16f,.18f,.2f));water=Mat("Water",new Color(.15f,.48f,.65f));leaf=Mat("Leaves",new Color(.2f,.4f,.2f));
  var g=Cube("Village ground",new Vector3(0,-.3f,0),new Vector3(42,.5f,42),grass);Prop(g,"Village green","A quiet village green. The residents wander here between conversations.");Cube("Main path",new Vector3(0,-.02f,0),new Vector3(4,.08f,34),stone);Cube("Cross path",new Vector3(0,.02f,0),new Vector3(28,.08f,3.5f),stone);
  House("Arthur's home",new Vector3(-10,0,-9));House("The Lantern Inn",new Vector3(10,0,-9));House("Blacksmith workshop",new Vector3(-10,0,10));
  Fountain();Bench(new Vector3(-3,0,-3));Bench(new Vector3(3,0,-3));Tree(new Vector3(-17,0,3));Tree(new Vector3(17,0,4));Tree(new Vector3(15,0,15));Tree(new Vector3(-17,0,-15));
  PropObj("Anvil",new Vector3(-7,.45f,9),new Vector3(1.3f,.75f,.8f),iron,"Mira's anvil. Ask what she is making, then return later to test recall.");PropObj("Forge",new Vector3(-13,.65f,11),new Vector3(1.8f,1.3f,1.2f),roof,"The blacksmith's forge.");PropObj("Notice board",new Vector3(0,1,5),new Vector3(1.6f,2,.2f),wood,"Village notices and requests.");PropObj("Inn table",new Vector3(8,.7f,-5),new Vector3(2,.15f,1.3f),wood,"A table outside the inn.");
  MakeNPC("Arthur","Arthur","Village elder",new Vector3(0,0,1),new Color(.48f,.28f,.18f),5);
  MakeNPC("Blacksmith","Mira the Smith","Blacksmith",new Vector3(-7,0,7),new Color(.62f,.22f,.12f),2.4f);
  MakeNPC("TavernKeeper","Tomas","Tavern keeper",new Vector3(8,0,-4),new Color(.22f,.4f,.25f),2.4f);
  MakeNPC("VillageGuard","Lena","Village guard",new Vector3(2,0,-2),new Color(.3f,.28f,.5f),4);
  var player=GameObject.CreatePrimitive(PrimitiveType.Capsule);player.name="Player";player.transform.position=new Vector3(0,1,-7);player.GetComponent<Renderer>().sharedMaterial=Mat("Player tunic",new Color(.16f,.34f,.62f));UnityEngine.Object.DestroyImmediate(player.GetComponent<CapsuleCollider>());player.AddComponent<CharacterController>();player.AddComponent<ThirdPersonController>();
  var camObj=new GameObject("Main Camera");camObj.tag="MainCamera";var cam=camObj.AddComponent<Camera>();camObj.AddComponent<AudioListener>();var orbit=camObj.AddComponent<OrbitCamera>();orbit.target=player.transform;player.GetComponent<ThirdPersonController>().cameraTransform=cam.transform;
  new GameObject("NPC Backend Client").AddComponent<NpcBackendClient>();BuildUI(cam,player);
  var sun=new GameObject("Sun").AddComponent<Light>();sun.type=LightType.Directional;sun.intensity=.85f;sun.color=new Color(1f,.9f,.76f);sun.transform.rotation=Quaternion.Euler(42,-32,0);RenderSettings.ambientMode=AmbientMode.Trilight;RenderSettings.ambientSkyColor=new Color(.58f,.72f,.88f);RenderSettings.ambientEquatorColor=new Color(.67f,.63f,.52f);RenderSettings.ambientGroundColor=new Color(.29f,.36f,.27f);SetupSky();RenderSettings.fog=true;RenderSettings.fogMode=FogMode.Linear;RenderSettings.fogColor=new Color(.68f,.76f,.82f);RenderSettings.fogStartDistance=32;RenderSettings.fogEndDistance=65;
  AssetDatabase.SaveAssets();EditorSceneManager.SaveScene(scene,"Assets/Scenes/Village.unity");Selection.activeGameObject=player;Debug.Log("Village built. Assign BackendConfig to NPC Backend Client. Backend is needed for memory dialogue; wandering works offline.");}
 static void SetupSky(){
  Shader shader=Shader.Find("Skybox/Procedural");if(!shader)return;
  if(!AssetDatabase.IsValidFolder(materialFolder))AssetDatabase.CreateFolder("Assets","Materials");
  const string path="Assets/Materials/VillageSky.mat";var sky=AssetDatabase.LoadAssetAtPath<Material>(path);
  if(!sky){sky=new Material(shader);sky.name="VillageSky";AssetDatabase.CreateAsset(sky,path);}else sky.shader=shader;
  if(sky.HasProperty("_SkyTint"))sky.SetColor("_SkyTint",new Color(.72f,.82f,.94f));
  if(sky.HasProperty("_GroundColor"))sky.SetColor("_GroundColor",new Color(.46f,.48f,.43f));
  if(sky.HasProperty("_AtmosphereThickness"))sky.SetFloat("_AtmosphereThickness",1.15f);
  if(sky.HasProperty("_Exposure"))sky.SetFloat("_Exposure",1.05f);
  EditorUtility.SetDirty(sky);RenderSettings.skybox=sky;
  RenderSettings.defaultReflectionMode=DefaultReflectionMode.Skybox;DynamicGI.UpdateEnvironment();
 }
 static Material Mat(string n,Color c){
  if(!AssetDatabase.IsValidFolder(materialFolder))AssetDatabase.CreateFolder("Assets","Materials");
  string safe=n.Replace(" ","_").Replace("/","_");string path=materialFolder+"/"+safe+".mat";
  Shader s=null;
  if(GraphicsSettings.currentRenderPipeline!=null){s=Shader.Find("Universal Render Pipeline/Lit");if(!s)s=Shader.Find("Universal Render Pipeline/Simple Lit");if(!s)s=Shader.Find("Universal Render Pipeline/Unlit");}
  else{s=Shader.Find("Standard");if(!s)s=Shader.Find("Diffuse");if(!s)s=Shader.Find("Unlit/Color");}
  if(!s)throw new System.InvalidOperationException("No compatible shader found. Install/configure URP or use the built-in render pipeline.");
  var m=AssetDatabase.LoadAssetAtPath<Material>(path);if(!m){m=new Material(s);m.name=n;AssetDatabase.CreateAsset(m,path);}else m.shader=s;
  m.color=c;if(m.HasProperty("_BaseColor"))m.SetColor("_BaseColor",c);if(m.HasProperty("_Color"))m.SetColor("_Color",c);if(m.HasProperty("_Smoothness"))m.SetFloat("_Smoothness",.18f);EditorUtility.SetDirty(m);return m;
 }
 static GameObject Cube(string n,Vector3 p,Vector3 scale,Material m){var o=GameObject.CreatePrimitive(PrimitiveType.Cube);o.name=n;o.transform.position=p;o.transform.localScale=scale;if(m)o.GetComponent<Renderer>().sharedMaterial=m;return o;}
 static void House(string n,Vector3 p){
  Cube(n+" walls",p+new Vector3(0,1.6f,0),new Vector3(7,3.2f,5.5f),wood);
  var roofA=Cube(n+" roof left",p+new Vector3(0,3.55f,-1.35f),new Vector3(7.8f,.3f,3.5f),roof);roofA.transform.rotation=Quaternion.Euler(25,0,0);
  var roofB=Cube(n+" roof right",p+new Vector3(0,3.55f,1.35f),new Vector3(7.8f,.3f,3.5f),roof);roofB.transform.rotation=Quaternion.Euler(-25,0,0);
  Cube(n+" door",p+new Vector3(0,.95f,-2.79f),new Vector3(1.1f,1.9f,.12f),iron);
  Cube(n+" window left",p+new Vector3(-2,2,-2.8f),new Vector3(1,.8f,.1f),water);Cube(n+" window right",p+new Vector3(2,2,-2.8f),new Vector3(1,.8f,.1f),water);
  Cube(n+" porch",p+new Vector3(0,.18f,-3.2f),new Vector3(3.2f,.3f,1.2f),stone);
 }
 static void Prop(GameObject o,string n,string d){var p=o.AddComponent<WorldProp>();p.displayName=n;p.description=d;}
 static void PropObj(string n,Vector3 p,Vector3 s,Material m,string d){var o=Cube(n,p,s,m);Prop(o,n,d);}
 static void Fountain(){var b=GameObject.CreatePrimitive(PrimitiveType.Cylinder);b.name="Fountain";b.transform.position=new Vector3(0,.35f,0);b.transform.localScale=new Vector3(2.7f,.35f,2.7f);b.GetComponent<Renderer>().sharedMaterial=stone;Prop(b,"Village fountain","A calm meeting point in the village square.");var w=GameObject.CreatePrimitive(PrimitiveType.Cylinder);w.name="Fountain water";w.transform.position=new Vector3(0,.75f,0);w.transform.localScale=new Vector3(1.8f,.2f,1.8f);w.GetComponent<Renderer>().sharedMaterial=water;}
 static void Bench(Vector3 p){Cube("Bench",p,new Vector3(2,.18f,.55f),wood);Cube("Bench back",p+new Vector3(0,.5f,.18f),new Vector3(2,.7f,.15f),wood);}
 static void Tree(Vector3 p){var t=GameObject.CreatePrimitive(PrimitiveType.Cylinder);t.name="Tree trunk";t.transform.position=p+Vector3.up;t.transform.localScale=new Vector3(.5f,1.8f,.5f);t.GetComponent<Renderer>().sharedMaterial=wood;var c=GameObject.CreatePrimitive(PrimitiveType.Sphere);c.name="Tree crown";c.transform.position=p+Vector3.up*3;c.transform.localScale=Vector3.one*2.6f;c.GetComponent<Renderer>().sharedMaterial=leaf;}
 static void MakeNPC(string id,string label,string role,Vector3 pos,Color shirt,float radius){var root=new GameObject(label);root.transform.position=pos;var who=root.AddComponent<NPCIdentity>();who.npcId=id;who.displayName=label;who.role=role;var tag=root.AddComponent<NPCNameTag>();tag.identity=who;var cc=root.AddComponent<CharacterController>();cc.height=2;cc.radius=.36f;cc.center=Vector3.up;
  Part(root,"Body",PrimitiveType.Capsule,new Vector3(0,1,0),new Vector3(.65f,.78f,.42f),Mat(label+" clothes",shirt));Part(root,"Head",PrimitiveType.Sphere,new Vector3(0,2.02f,0),new Vector3(.47f,.52f,.45f),skin);Part(root,"Hair",PrimitiveType.Sphere,new Vector3(0,2.25f,-.04f),new Vector3(.48f,.25f,.47f),wood);Part(root,"Left arm",PrimitiveType.Capsule,new Vector3(-.48f,1.08f,0),new Vector3(.22f,.5f,.22f),skin);Part(root,"Right arm",PrimitiveType.Capsule,new Vector3(.48f,1.08f,0),new Vector3(.22f,.5f,.22f),skin);Part(root,"Left leg",PrimitiveType.Capsule,new Vector3(-.18f,.34f,0),new Vector3(.22f,.48f,.23f),iron);Part(root,"Right leg",PrimitiveType.Capsule,new Vector3(.18f,.34f,0),new Vector3(.22f,.48f,.23f),iron);
  var hit=GameObject.CreatePrimitive(PrimitiveType.Capsule);hit.name="Talk target";hit.transform.SetParent(root.transform);hit.transform.localPosition=Vector3.up;hit.transform.localScale=new Vector3(.9f,1.15f,.9f);UnityEngine.Object.DestroyImmediate(hit.GetComponent<Renderer>());var w=root.AddComponent<NPCWander>();w.wanderRadius=radius;w.speed=1.15f;}
 static void Part(GameObject parent,string n,PrimitiveType type,Vector3 p,Vector3 s,Material m){var o=GameObject.CreatePrimitive(type);o.name=n;o.transform.SetParent(parent.transform);o.transform.localPosition=p;o.transform.localScale=s;o.GetComponent<Renderer>().sharedMaterial=m;UnityEngine.Object.DestroyImmediate(o.GetComponent<Collider>());}
 static void BuildUI(Camera cam,GameObject player){var canvasObj=new GameObject("Game UI",typeof(Canvas),typeof(CanvasScaler),typeof(GraphicRaycaster));var canvas=canvasObj.GetComponent<Canvas>();canvas.renderMode=RenderMode.ScreenSpaceOverlay;canvasObj.GetComponent<CanvasScaler>().uiScaleMode=CanvasScaler.ScaleMode.ScaleWithScreenSize;canvasObj.GetComponent<CanvasScaler>().referenceResolution=new Vector2(1920,1080);
  var cross=Txt(canvasObj.transform,"Crosshair","+",22,new Vector2(.5f,.5f),new Vector2(40,40));cross.alignment=TextAnchor.MiddleCenter;var prompt=Txt(canvasObj.transform,"Interaction Prompt","",18,new Vector2(.5f,.15f),new Vector2(800,42));prompt.alignment=TextAnchor.MiddleCenter;Txt(canvasObj.transform,"Controls","WASD move  •  Move mouse to point  •  E or click to talk  •  Right mouse drag to look",16,new Vector2(.5f,.035f),new Vector2(1100,36)).alignment=TextAnchor.MiddleCenter;
  var panel=new GameObject("Dialogue Panel",typeof(Image));panel.transform.SetParent(canvasObj.transform,false);var pr=panel.GetComponent<RectTransform>();pr.anchorMin=new Vector2(.54f,.08f);pr.anchorMax=new Vector2(.98f,.9f);pr.offsetMin=Vector2.zero;pr.offsetMax=Vector2.zero;panel.GetComponent<Image>().color=new Color(.05f,.07f,.08f,.95f);
  var title=Txt(panel.transform,"Title","",24,new Vector2(.5f,.92f),new Vector2(700,48));var text=Txt(panel.transform,"Transcript","",19,new Vector2(.5f,.55f),new Vector2(700,440));text.alignment=TextAnchor.UpperLeft;var status=Txt(panel.transform,"Status","",14,new Vector2(.5f,.14f),new Vector2(700,30));
  var input=UI<InputField>(panel.transform,"Input",new Vector2(.42f,.07f),new Vector2(520,48));input.GetComponent<Image>().color=Color.white;var placeholder=Txt(input.transform,"Placeholder","Type a message",17,new Vector2(.5f,.5f),new Vector2(480,40));placeholder.color=Color.gray;input.textComponent=Txt(input.transform,"Input Text","",17,new Vector2(.5f,.5f),new Vector2(480,40));input.placeholder=placeholder;
  var button=UI<Button>(panel.transform,"Send",new Vector2(.87f,.07f),new Vector2(120,48));button.GetComponent<Image>().color=new Color(.2f,.42f,.3f);Txt(button.transform,"Send Text","Send",18,new Vector2(.5f,.5f),new Vector2(110,40)).alignment=TextAnchor.MiddleCenter;
  var close=UI<Button>(panel.transform,"Close",new Vector2(.95f,.94f),new Vector2(40,40));Txt(close.transform,"Close Text","X",18,new Vector2(.5f,.5f),new Vector2(36,36)).alignment=TextAnchor.MiddleCenter;
  var dlg=canvasObj.AddComponent<DialoguePanel>();dlg.panel=panel;dlg.title=title;dlg.transcript=text;dlg.status=status;dlg.input=input;dlg.sendButton=button;close.onClick.AddListener(dlg.Close);var inter=player.AddComponent<WorldInteractor>();inter.viewCamera=cam;inter.dialogue=dlg;inter.prompt=prompt;
  var idPanel=new GameObject("Player ID Panel",typeof(Image));idPanel.transform.SetParent(canvasObj.transform,false);var ir=idPanel.GetComponent<RectTransform>();ir.anchorMin=Vector2.zero;ir.anchorMax=Vector2.one;ir.offsetMin=Vector2.zero;ir.offsetMax=Vector2.zero;idPanel.GetComponent<Image>().color=new Color(.035f,.055f,.075f,.94f);
  Txt(idPanel.transform,"Player ID Title","Who is playing?",30,new Vector2(.5f,.66f),new Vector2(650,55));var help=Txt(idPanel.transform,"Player ID Help","Enter the same player ID used in your backend tests to load that player's memories.",17,new Vector2(.5f,.57f),new Vector2(850,45));help.color=new Color(.82f,.86f,.9f);
  var idInput=UI<InputField>(idPanel.transform,"Player ID Input",new Vector2(.5f,.47f),new Vector2(440,56));idInput.GetComponent<Image>().color=new Color(.95f,.95f,.92f);var idPlaceholder=Txt(idInput.transform,"Player ID Placeholder","e.g. karan",20,new Vector2(.5f,.5f),new Vector2(410,46));idPlaceholder.color=Color.gray;idInput.textComponent=Txt(idInput.transform,"Player ID Text","",20,new Vector2(.5f,.5f),new Vector2(410,46));idInput.placeholder=idPlaceholder;
  var idError=Txt(idPanel.transform,"Player ID Error","",16,new Vector2(.5f,.38f),new Vector2(800,36));idError.color=new Color(1f,.55f,.45f);var start=UI<Button>(idPanel.transform,"Enter Village",new Vector2(.5f,.30f),new Vector2(240,56));start.GetComponent<Image>().color=new Color(.25f,.48f,.34f);Txt(start.transform,"Enter Village Text","Enter Village",20,new Vector2(.5f,.5f),new Vector2(230,48)).alignment=TextAnchor.MiddleCenter;
  var idPrompt=canvasObj.AddComponent<PlayerIdPrompt>();idPrompt.panel=idPanel;idPrompt.playerIdInput=idInput;idPrompt.confirmButton=start;idPrompt.errorText=idError;
  new GameObject("EventSystem",typeof(EventSystem),typeof(StandaloneInputModule));}
 static Text Txt(Transform parent,string n,string value,int size,Vector2 anchor,Vector2 dims){var o=new GameObject(n,typeof(RectTransform),typeof(Text));o.transform.SetParent(parent,false);var r=o.GetComponent<RectTransform>();r.anchorMin=r.anchorMax=anchor;r.anchoredPosition=Vector2.zero;r.sizeDelta=dims;var t=o.GetComponent<Text>();t.text=value;t.font=Font.CreateDynamicFontFromOSFont("Arial",size);if(!t.font)t.font=Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");t.fontSize=size;t.color=Color.white;t.alignment=TextAnchor.MiddleCenter;return t;}
 static T UI<T>(Transform parent,string n,Vector2 anchor,Vector2 dims)where T:Component{var o=new GameObject(n,typeof(RectTransform),typeof(Image),typeof(T));o.transform.SetParent(parent,false);var r=o.GetComponent<RectTransform>();r.anchorMin=r.anchorMax=anchor;r.anchoredPosition=Vector2.zero;r.sizeDelta=dims;return o.GetComponent<T>();}
}
#endif

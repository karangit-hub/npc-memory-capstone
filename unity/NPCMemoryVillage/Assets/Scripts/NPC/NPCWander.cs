using UnityEngine;
[RequireComponent(typeof(CharacterController))]
public class NPCWander : MonoBehaviour
{
    public float wanderRadius=4f, speed=1.25f, turnSpeed=5f, arriveDistance=.45f;
    CharacterController controller; Vector3 home,target; float wait,vertical;
    void Start(){controller=GetComponent<CharacterController>();home=transform.position;PickTarget();}
    void Update(){if(!PlayerIdPrompt.Ready){ApplyGravity();return;}if(DialoguePanel.CurrentNPC==GetComponent<NPCIdentity>()){ApplyGravity();return;}if(wait>0){wait-=Time.deltaTime;ApplyGravity();return;}Vector3 delta=target-transform.position;delta.y=0;if(delta.magnitude<=arriveDistance){wait=Random.Range(1.5f,4f);PickTarget();ApplyGravity();return;}Vector3 dir=delta.normalized; bool blocked=false;foreach(var h in Physics.SphereCastAll(transform.position+Vector3.up*.6f,.25f,dir,.6f,Physics.DefaultRaycastLayers,QueryTriggerInteraction.Ignore)){if(h.transform!=transform&&!h.transform.IsChildOf(transform)){blocked=true;break;}}if(blocked){wait=.7f;PickTarget();ApplyGravity();return;}transform.rotation=Quaternion.Slerp(transform.rotation,Quaternion.LookRotation(dir),turnSpeed*Time.deltaTime);controller.Move((dir*speed+Vector3.up*Gravity())*Time.deltaTime);}
    float Gravity(){if(controller.isGrounded&&vertical<0)vertical=-2;vertical+=-18*Time.deltaTime;return vertical;}
    void ApplyGravity(){controller.Move(Vector3.up*Gravity()*Time.deltaTime);}
    void PickTarget(){Vector2 p=Random.insideUnitCircle*wanderRadius;target=home+new Vector3(p.x,0,p.y);}
}

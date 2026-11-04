using UnityEngine;
[RequireComponent(typeof(CharacterController))]
public class ThirdPersonController:MonoBehaviour
{
 public Transform cameraTransform;public float speed=4.5f,turnSpeed=12,gravity=-20;CharacterController c;float y;
 void Awake(){c=GetComponent<CharacterController>();}void Update(){if(DialoguePanel.ChatOpen||!PlayerIdPrompt.Ready)return;float x=Input.GetAxis("Horizontal"),z=Input.GetAxis("Vertical");Vector3 f=cameraTransform.forward,r=cameraTransform.right;f.y=0;r.y=0;f.Normalize();r.Normalize();Vector3 d=Vector3.ClampMagnitude(f*z+r*x,1);if(d.sqrMagnitude>.001f)transform.rotation=Quaternion.Slerp(transform.rotation,Quaternion.LookRotation(d),turnSpeed*Time.deltaTime);if(c.isGrounded&&y<0)y=-2;y+=gravity*Time.deltaTime;c.Move((d*speed+Vector3.up*y)*Time.deltaTime);}
}

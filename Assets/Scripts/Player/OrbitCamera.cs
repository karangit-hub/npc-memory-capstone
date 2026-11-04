using UnityEngine;
public class OrbitCamera:MonoBehaviour
{
 public Transform target;public float distance=6,height=1.8f,sensitivity=2.2f;float yaw,pitch=15;
 void LateUpdate(){if(!target||DialoguePanel.ChatOpen||!PlayerIdPrompt.Ready)return;if(Input.GetMouseButton(1)){yaw+=Input.GetAxis("Mouse X")*sensitivity;pitch=Mathf.Clamp(pitch-Input.GetAxis("Mouse Y")*sensitivity,-15,65);}Quaternion q=Quaternion.Euler(pitch,yaw,0);Vector3 focus=target.position+Vector3.up*height;transform.position=focus+q*new Vector3(0,0,-distance);transform.rotation=q;}
}

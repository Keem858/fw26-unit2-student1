import logging
import time
from uuid import uuid4

import yaml
from kubernetes import client, config


config.load_kube_config()
pod_api = client.CoreV1Api()

# Desc: Function that removes a pod for reconciliation test.
def pod_subtraction_test(num_pods_to_subtract: int):
    if num_pods_to_subtract < 1:
        raise ValueError("Choose at least one Pod to remove.")

    namespace = "default"
    resource_name = "echo-service"
    resource = client.CustomObjectsApi().get_namespaced_custom_object(
        group="cosc3657.tu.ca",
        version="v1alpha1",
        namespace=namespace,
        plural="resilientdeployments",
        name=resource_name,
    )
    owner_uid = resource["metadata"]["uid"]

    response = pod_api.list_namespaced_pod(
        namespace=namespace,
        label_selector=f"app.kubernetes.io/managed-by={resource_name}",
        field_selector="status.phase=Running",
    )
    owned_pods = [
        pod for pod in response.items
        if pod.metadata.deletion_timestamp is None
        and any(
            ref.uid == owner_uid and ref.controller is True
            for ref in (pod.metadata.owner_references or [])
        )
    ]
    if num_pods_to_subtract > len(owned_pods):
        raise ValueError(f"Only {len(owned_pods)} owned Pods are running.")

    for pod in owned_pods[:num_pods_to_subtract]:
        pod_api.delete_namespaced_pod(
            name=pod.metadata.name,
            namespace=namespace,
            body=client.V1DeleteOptions(
                grace_period_seconds=0,
                preconditions=client.V1Preconditions(uid=pod.metadata.uid),
            ),
        )
        print(f"Requested force deletion of {pod.metadata.name} (UID {pod.metadata.uid})")


# Desc: Function that adds a pod for reconciliation test.
def pod_addition_test(num_pods_to_add: int):
    if num_pods_to_add < 1:
        raise ValueError("Choose at least one Pod to add.")

    from reconciler import create_pod

    resource_name = "echo-service"
    resource = client.CustomObjectsApi().get_namespaced_custom_object(
        group="cosc3657.tu.ca",
        version="v1alpha1",
        namespace="default",
        plural="resilientdeployments",
        name=resource_name,
    )

    for _ in range(num_pods_to_add):
        pod = create_pod(
            pod_api,
            resource,
            pod_name=f"{resource_name}-test-{uuid4().hex[:8]}",
            container_args=["-text=Hello from COSC3657"],
        )
        print(f"Created extra Pod {pod.metadata.name}")





"""
NOTE: This command resets the desired replicas to 3.

kubectl --context kind-cosc3657-unit2 -n default patch resilientdeployment echo-service \
  --type=merge -p '{"spec":{"replicas":3}}'
"""



"""
if __name__ == "__main__":
    print("REMOVING Pod from cluster.")
    pod_subtraction_test(1)
"""



if __name__ == "__main__":
    print("ADDING Pod to cluster.")
    pod_addition_test(1)





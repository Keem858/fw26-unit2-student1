# Put your code here if python is chosen for this project.
"""
Part 1: Understanding the Contract
Def: yaml = A serialization/deserialization format.
Def: echo-resource = A Kubernetes API object of type ResilientDeployent that tells reconciler how many pods to maintain.
Def: Docker = Containerization software.
Def: Kind = A tool for running clusters.
Def: Kubernetes = A platform that automates container deployment, scaling, and management.
Def: Kubectl = The command line interface for cluster deployment.
Def: Container = A lightweight, self-contained software package.
Def: Pods = Kubernetes smallest deployable unit which can hold 1 or more containers.
Def: CRD = Defines what you can ask for - It allows for the creation of additional resources (ie, DB, pods, containers).
Def: Custom Resources = The instance of what is created from CRD.
Def: Reconciler = A controller.
Def: Controller = A program that watches over a cluster and reconciles actual state with desired state.

Objective: The creation of a Python Controller that Reconciles system state to converge actual pod
count to desired pod count.

Project Specifications:
1. spec.replicas = An integer between 1 and 10
2. spec.image = A string
3. echo-service = Requests 3 pods running hashicorp/http-echo:latest
"""


"""
Part 2: Environment Check
docker info -> ALL GOOD
kind --version -> ALL GOOD
kubectl version --client -> ALL GOOD
source .venv/bin/activate -> ALL GOOD
"""


"""
Part 3: Registering Desired State
Desc: Applying CRD definitions, ensuring they are available, applying desired-state manifest,
and inspecting stored resources.

kubectl apply -f crd_definition.yaml -> ALL GOOD
kubectl wait --for=condition=Established crd/resilientdeployments.cosc3657.tu.ca --timeout=60s -> ALL GOOD
kubectl apply -f sample_cr.yaml -> ALL GOOD
kubectl get resilientdeployment echo-service -n default -o yaml -> ALL GOOD
"""

"""
Part 4: Controller Design
"""
import logging
import time
import yaml
from kubernetes import client, config

logger = logging.getLogger(__name__)

"""
Doc: https://k8s-python.readthedocs.io/en/stable/kubernetes.config.html
Desc: config.load_kube_config() loads the API server and address into this context.
Desc: pod_api is the object that allows us to communicate with Kubernetes.
"""
config.load_kube_config()
pod_api = client.CoreV1Api()

"""
Desc: Function that acquires desired num of replicas from sample_cr.yaml,
number of actual pods from "list_namespaced_pod()".
"""
def get_drift():
    with open("sample_cr.yaml") as f:
        data = yaml.safe_load(f)

    resource_name = data["metadata"]["name"]
    namespace = data["metadata"]["namespace"]

    resource = client.CustomObjectsApi().get_namespaced_custom_object(
        group="cosc3657.tu.ca",
        version="v1alpha1",
        namespace=namespace,
        plural="resilientdeployments",
        name=resource_name,
    )
    owner_uid = resource["metadata"]["uid"]
    desired = resource["spec"]["replicas"]

    response = pod_api.list_namespaced_pod(
        namespace=namespace,
        label_selector=f"app.kubernetes.io/managed-by={resource_name}",
    )

    owned_pods = [
        pod for pod in response.items
        if any(
            ref.uid == owner_uid and ref.controller is True
            for ref in (pod.metadata.owner_references or [])
        )
    ]

    active_pods = [
        pod for pod in owned_pods
        if pod.metadata.deletion_timestamp is None
        and pod.status.phase in ("Pending", "Running")
    ]

    return desired - len(active_pods), resource, active_pods


"""
Desc: Function that uses Kubernetes to create pods composed of ints and strings.
"""
def create_pod(pod_api, resource, pod_name, container_args=None):
    resource_metadata = resource["metadata"]

    # owners are Kubernetes objects that manage pod lifecycles
    owner = client.V1OwnerReference(
        api_version=resource["apiVersion"],
        kind=resource["kind"],
        name=resource_metadata["name"],
        uid=resource_metadata["uid"],
        controller=True,
    )

    container = client.V1Container(
        name="echo",
        image=resource["spec"]["image"],
        args=container_args,
    )

    pod = client.V1Pod(
        api_version="v1",
        kind="Pod",
        metadata=client.V1ObjectMeta(
            name=pod_name,
            labels={
                "app.kubernetes.io/managed-by": resource_metadata["name"],
            },
            owner_references=[owner],
        ),
        spec=client.V1PodSpec(containers=[container]),
    )

    return pod_api.create_namespaced_pod(
        namespace=resource_metadata["namespace"],
        body=pod,
    )


"""
Desc: Function that logs active pods to the concole.
"""
def log_active_pods(resource, drift, active_pods):
    """Log the Pods and replica counts observed before reconciliation."""
    ready_count = 0
    pod_lines = []

    for pod in active_pods:
        ready = any(
            condition.type == "Ready" and condition.status == "True"
            for condition in (pod.status.conditions or [])
        )
        if ready:
            ready_count += 1

        containers = ", ".join(
            f"{container.name} ({container.image})"
            for container in pod.spec.containers
        )
        pod_lines.append(
            f"  {pod.metadata.name}: phase={pod.status.phase}, "
            f"ready={ready}, containers={containers}"
        )

    metadata = resource["metadata"]
    summary = (
        f"Before reconciliation for {metadata['namespace']}/{metadata['name']}: "
        f"desired={resource['spec']['replicas']}, active={len(active_pods)}, "
        f"ready={ready_count}, drift={drift:+d}"
    )
    if not pod_lines:
        pod_lines.append("  No active Pods")

    logger.info("\n".join([summary, *pod_lines]))


"""
Desc: Function reconcile that observes drift then reconciles by creating and/or
deleting pods.
"""
def reconcile():
    drift, resource, active_pods = get_drift()
    log_active_pods(resource, drift, active_pods)

    if drift > 0:
        namespace = resource["metadata"]["namespace"]
        resource_name = resource["metadata"]["name"]
        desired = resource["spec"]["replicas"]

        pods_in_namespace = pod_api.list_namespaced_pod(namespace=namespace).items
        occupied_names = {pod.metadata.name for pod in pods_in_namespace}

        free_names = []
        for i in range(desired):
            name = f"{resource_name}-{i}"
            if name not in occupied_names:
                free_names.append(name)

        for name in free_names[:drift]:
            pod = create_pod(
                pod_api, resource, pod_name=name,
                container_args=["-text=Hello from COSC3657"],
            )
            logger.info("Created %s", pod.metadata.name)
    elif drift < 0:
        namespace = resource["metadata"]["namespace"]
        extra_pods = abs(drift)

        for pod in active_pods[:extra_pods]:
            pod_api.delete_namespaced_pod(
                name=pod.metadata.name,
                namespace=namespace,
                body=client.V1DeleteOptions(
                    preconditions=client.V1Preconditions(uid=pod.metadata.uid),
                ),
            )
            logger.info("Requested deletion of %s", pod.metadata.name)




if __name__ == "__main__":
    print("=== COSC 3657 Custom Kubernetes Reconciler Started ===")
    while True:
        # Logging deift and action messages
        logging.basicConfig(level=logging.INFO)

        reconcile()
        time.sleep(5)


"""
PRESENTATION

1. Present AI Assisted PROJECT_PLAN.md

2. Present Terms & Definitions

3. Present reconciler and related checks

4. Present protocols
    Kubernetes REST API over HTTPS
        GET/POST/DELETE/PATCH

"""









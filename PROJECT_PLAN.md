# Unit 2: objective and one-day learning plan

Prepared for November 9, 2026. Budget: **about 5 focused hours**, including a 30-minute troubleshooting buffer. These are planning estimates; installation and image downloads may take longer.

## Declaration of objective

> My objective is to build and explain a Python controller for the Kubernetes `ResilientDeployment` custom resource. It will read the declared replica count, observe the Pods belonging to that resource, and create or delete Pods until the counts converge. New Pods will use the declared container image. I will demonstrate automatic recovery after forced Pod deletion, scaling in both directions, and repeated reconciliation without unnecessary changes. I will submit working code, evidence of recovery, and a recorded explanation of my design, challenges, and use of AI.

The learning objective is to explain **why each decision leads to convergence**, including when observations are delayed or API operations fail.

## Starting point

- `crd_definition.yaml` already defines the API type and constrains replicas to integers from 1 to 10.
- `sample_cr.yaml` already declares `echo-service` in `default`, with 3 replicas and image `hashicorp/http-echo:latest`.
- `reconciler.py` contains only a placeholder comment. The controller is the main implementation task.
- Docker, kubectl, Python, and Homebrew commands are on this machine's PATH. `kind` was not found on PATH. Docker daemon availability and cluster access have not been tested.
- The README examples use `echo-cluster`; this plan consistently uses the actual manifest name, **`echo-service`**.

## The objects you are designing around

| Object | Role in this project | What you should be able to explain |
| --- | --- | --- |
| CRD (`crd_definition.yaml`) | Registers the `ResilientDeployment` API type and schema | A type definition is different from an instance |
| Custom resource (`sample_cr.yaml`) | Stores the user's desired count and image | Applying this object declares intent |
| Pod | Runs one instance of the echo container | Pods have identities, lifecycle states, and startup delays |
| Python controller | Reads intent and current Pods, then corrects drift | Behavior comes from the reconciliation logic |

A custom resource stores structured configuration; adding a controller gives it automated behavior. See the official [custom resources explanation](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/).

```text
sample_cr.yaml -> API server stores desired state
                            |
                            v
              Observe owned Pods -> Calculate drift -> Create/delete
                      ^                                      |
                      +-------------- repeat ----------------+
```

This follows the Kubernetes [controller pattern](https://kubernetes.io/docs/concepts/architecture/controller/).

## Today's parts

Work in order. At each checkpoint: **predict the result, run it, inspect it, explain it**. Keep a short note about anything surprising.

| Part | Budget | Work product | Checkpoint before moving on |
| --- | --- | --- | --- |
| 1. Understand the contract | 15 min | A short explanation of CRD, custom resource, Pod, and controller | Explain what should happen when desired = 3 and observed = 1 |
| 2. Prepare the environment | 45 min | Python environment and a running kind cluster | All cluster nodes report `Ready` |
| 3. Register and inspect intent | 20 min | Applied CRD and readable `echo-service` resource | Retrieve `spec.replicas` and `spec.image`; explain why the CRD alone creates no Pods |
| 4. Implement one reconciliation pass | 60 min | Observation, drift calculation, Pod creation/deletion | Reach 3 Pods; repeating the pass makes no further changes |
| 5. Add continuous operation | 45 min | Watch handling, periodic resync, error handling, useful logs | A desired-count change and a Pod deletion are both detected without restarting |
| 6. Demonstrate and capture evidence | 45 min | Recorded results for the verification matrix below | Recovery, scale-up, scale-down, and stable repetition all pass |
| 7. Explain and package | 40 min | Run instructions, reflection, presentation, submitted repository | Another person can run it and you can explain every major function |

Total: 4 hours 30 minutes of planned work + 30 minutes of buffer. Protect the last 40 minutes for recording and submission.

## Part 2: environment checklist

Start Docker Desktop. From the repository directory, run these commands one at a time and inspect their output:

```bash
docker info
brew install kind
kind --version
kubectl version --client
python3 -m venv .venv
source .venv/bin/activate
python -m pip install kubernetes rich pyyaml
```

The README calls for a multi-node cluster, but its plain creation command does not configure extra nodes. Create `kind-config.yaml` with:

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
  - role: worker
  - role: worker
```

Then:

```bash
kind create cluster --name cosc3657-unit2 --config kind-config.yaml
kubectl config current-context
kubectl get nodes
```

Keep kubectl and the Python client pointed at `kind-cosc3657-unit2`. This topology comes from the official [kind multi-node instructions](https://kind.sigs.k8s.io/docs/user/quick-start/#multi-node-clusters).

**Learning check:** What does Docker provide, what does kind create, and what does kubectl talk to?

## Part 3: register and read the desired state

```bash
kubectl apply -f crd_definition.yaml
kubectl wait --for=condition=Established crd/resilientdeployments.cosc3657.tu.ca --timeout=60s
kubectl apply -f sample_cr.yaml
kubectl get resilientdeployment echo-service -n default -o yaml
```

Read the group (`cosc3657.tu.ca`), version (`v1alpha1`), plural (`resilientdeployments`), namespace, resource name, replicas, and image. These must agree with the Python API calls.

**Learning check:** Why can Kubernetes accept this object even though your controller has not been written yet?

## Parts 4–5: controller design

Build a small working pass first, then surround it with continuous operation. Suggested responsibilities:

| Function/responsibility | Input | Result |
| --- | --- | --- |
| Connect to the cluster | Local kubeconfig and cluster context | `CustomObjectsApi` and `CoreV1Api` clients |
| Read desired resources | Namespace and custom API identifiers | Current resource objects |
| Observe owned Pods | Resource namespace, name, and UID | Pods this resource controls |
| Build a Pod request | Resource image, owner, label, and Pod name | A consistent Pod definition |
| Reconcile one resource | Current resource and fresh Pod observation | Necessary creates/deletes plus a log entry |
| Run continuously | Watch events and resync deadlines | Repeated calls to the same reconciliation function |

The official [Python client](https://github.com/kubernetes-client/python) includes kubeconfig, API-client, and `watch.Watch()` examples.

Use these implementation rules:

1. Read `spec.replicas`; calculate `drift = desired - observed`. Positive means create, negative means delete, and zero means no count change.
2. Work in the resource's namespace. Use `app.kubernetes.io/managed-by=echo-service` for the sample, deriving the value from the resource name. Add an owner reference and verify the owner's UID before modifying a Pod.
3. Count non-terminating `Pending` and `Running` Pods toward capacity so slow startup does not trigger repeated creation. Exclude terminal Pods and Pods with a deletion timestamp. Treat an unknown phase conservatively and log it. Report running/ready counts separately from capacity.
4. Use predictable Pod names for replica slots and serialize reconciliation in one controller process. Delete terminal Pods that occupy needed slots, and wait for deletion to finish before reusing a name. On a create conflict, re-observe; on an already-absent Pod during deletion, continue. After uncertain API outcomes, re-list before deciding what to do next.
5. Use the resource's image in new Pods. For the sample echo image, supply a container argument such as `-text=Hello from COSC3657`; see the [image's usage example](https://github.com/hashicorp/http-echo).
6. Log resource name, desired count, observed capacity, ready count, drift, action, and errors. Say the replica count matches while Pods start; reserve a healthy-equilibrium message for the readiness check.
7. On startup, list and reconcile existing resources. Handle custom-resource `ADDED` and `MODIFIED` watch events. On `DELETED`, stop reconciling that resource; owner references allow dependent-Pod cleanup.
8. Also resync periodically, targeting about 2 seconds under normal local conditions. A watch of custom resources alone does not notify you when a Pod is deleted. Use a bounded watch and a time-based resync deadline so continuous events cannot postpone that resync indefinitely.
9. Reconnect after watch timeouts or transient failures. If a resource version expires, re-list and resume watching. Log errors and retry with a delay; avoid a tight failure loop or a broad exception handler that hides the problem.

These are proposed design choices to verify during implementation. Pending Pods can already exist while images are downloading, and `Running` is not a complete health assessment; see [Pod lifecycle and phases](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/).

**Learning checks:** Why can counting only Running Pods over-create? Why must a second pass at equilibrium do nothing? If an API request times out, do you know whether it succeeded? Why is desired count different from ready count?

## Part 6: verification and evidence

Use one terminal for the controller and another for commands. Create `evidence/` before recording output. For example, run the controller with:

```bash
python -u reconciler.py 2>&1 | tee evidence/controller.log
```

Run the following cases in order. Wait for each case to settle before starting the next.

| Case | Action | Required observation |
| --- | --- | --- |
| Initial convergence | Run controller with sample resource present | Exactly 3 owned Pods eventually become ready |
| Repeat safety | Let several passes run without changing anything | Same Pod UIDs; no additional create/delete actions |
| Forced deletion | Delete one owned Pod with force | Controller creates a replacement; return to 3 ready Pods |
| Scale up | Patch desired count from 3 to 5 | Converge to 5 ready Pods |
| Scale down | Patch desired count from 5 to 2 | Converge to 2 ready Pods; unrelated Pods untouched |
| Restart recovery | Stop controller, delete one owned Pod, restart controller | Startup observation restores the declared count |

Useful demo commands, using the actual resource name:

```bash
kubectl get pods -n default -l app.kubernetes.io/managed-by=echo-service -o wide
kubectl get pods -n default -l app.kubernetes.io/managed-by=echo-service -o custom-columns=NAME:.metadata.name,UID:.metadata.uid,PHASE:.status.phase

DEMO_POD=$(kubectl get pods -n default -l app.kubernetes.io/managed-by=echo-service -o jsonpath='{.items[0].metadata.name}')
kubectl delete pod "$DEMO_POD" -n default --grace-period=0 --force

kubectl patch resilientdeployment echo-service -n default --type=merge -p '{"spec":{"replicas":5}}'
kubectl patch resilientdeployment echo-service -n default --type=merge -p '{"spec":{"replicas":2}}'
```

Run the two patches separately, observing convergence between them. Capture Pod listings before and after forced deletion, the controller's replacement action, and the recovered ready count. A replacement has a new UID even if its slot name is reused.

The README's two-second recovery statement is a useful detection target. Measure actual detection and readiness times separately; scheduling and image pulls can delay readiness. The forced-deletion demo demonstrates recovery from Pod removal. Broader node-failure and network-partition behavior requires separate experiments.

If a case fails, inspect `kubectl describe pod POD_NAME -n default` and `kubectl logs POD_NAME -n default`, then repeat that case after the fix.

## Part 7: explanation and submission

Suggested presentation outline, about 4–6 minutes unless your course specifies otherwise:

1. State the objective and distinguish the CRD from the custom resource.
2. Trace one resource through observe, calculate drift, and reconcile in your code.
3. Show forced deletion and automatic recovery; show scaling if time permits.
4. Explain one challenge you actually encountered, the evidence, and the fix.
5. Explain idempotence and eventual convergence using your demo.
6. Describe AI assistance accurately: what it helped produce, what you changed, and how you checked it.

Keep a short learning log as you work: **prediction → observation → explanation/fix**. Use actual experiences in the presentation; do not invent challenges or claim tests you did not run.

Before submission:

- [ ] `reconciler.py` implements watch handling, drift calculation, and repeat-safe scaling.
- [ ] CRD, sample resource, cluster configuration, and dependency information are included.
- [ ] README gives the commands needed to reproduce your working run.
- [ ] Screenshot or logs clearly demonstrate forced deletion and replacement.
- [ ] Presentation recording is accessible in the course-required location.
- [ ] Challenges, limitations, and AI assistance are documented.
- [ ] Changes are committed and pushed, and the repository link is submitted as required.

Save optional enhancements—image-change rollouts, status-subresource updates, leader election, dashboards, and in-cluster controller deployment—for after the required demonstration and submission are complete.

**First action:** start Docker Desktop, then complete Part 2's environment checks. After each part, explain its checkpoint aloud before moving on.

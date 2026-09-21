# Scenario 2 — remove the network boundary and watch it stop mattering

The broker's allowlist is the visible control. It is not the load-bearing one.

```bash
task breach
```

(`task demo-agent` after a breach shows the same thing with a model driving.)

This deletes every NetworkPolicy in the namespace and re-runs the agent.

Look at what changes and what doesn't:

- **The broker's decisions are identical.** Same two allows, same four denies,
  same audit records. The policy engine is working exactly as before.
- **The bypass attempts now succeed.** The agent opens a socket straight to
  `claims-api` and `payments-api` and gets data back.

```
bypass attempts (agent tries to reach tools directly):
       http://claims-api:8080/claims              REACHED (boundary failed) 200
       http://payments-api:8080/balance           REACHED (boundary failed) 200
```

Confirm it from the other side:

```bash
kubectl -n agent-boundary logs -l app=payments-api | grep REACHED
```

`payments-api` logs every request it should never have received. In the
constrained run, that grep returns nothing.

Put it back:

```bash
task restore
```

## The point

An allowlist enforced only at the application layer is a request, not a
control, whenever the caller can route around the thing doing the enforcing.
Your agent's authorisation is only as strong as the network's willingness to
refuse the alternative path.

This is also why "we'll add guardrails in the agent framework" is not an
answer. The framework is in the blast radius. The network is not.

## A second, quieter failure

`kind`'s default CNI accepts NetworkPolicy objects and doesn't enforce them.
Run this project on a default kind cluster and `kubectl get networkpolicy`
shows six healthy policies while the bypass succeeds every time — a control
that exists in the cluster, in the repo, and in the architecture diagram, and
nowhere in the packet path.

`task cluster` installs Calico for exactly this reason. When you port these
policies to your own cluster, the first question is not "did they apply" but
"did anything change when they did".

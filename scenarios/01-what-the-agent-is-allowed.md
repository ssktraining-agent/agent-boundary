# Scenario 1 — what the agent is allowed to do

```bash
task demo
```

This is the fixed-sequence run: six hardcoded calls, no model, no API key.
It exists so the boundary can be examined on its own, without the model's
variability in the way. For the run where a model decides what to call, see
[scenario 3](03-the-document-that-gives-orders.md).

The agent is bound to account `ACC-77` and holds the principal `claims-agent`.
Its allowlist, in `k8s/30-broker.yaml` under the `tool-policy` ConfigMap:

```json
"claims-agent": {
  "allow": [
    {"tool": "claims.read", "scope": "account"},
    {"tool": "claims.list", "scope": "account"}
  ]
}
```

Two calls succeed. Four are refused, for three different reasons:

| Attempt | Outcome | Why |
|---|---|---|
| `claims.list` for `ACC-77` | allow | in the allowlist, in scope |
| `claims.read` `CLM-1001` (`ACC-77`) | allow | in the allowlist, in scope |
| `claims.read` `CLM-1003` (`ACC-91`) | **deny** | in the allowlist, **out of scope** |
| `payments.read` | **deny** | tool exists, not in this principal's allowlist |
| `payments.execute` | **deny** | tool exists, not in this principal's allowlist |
| `secrets.read` | **deny** | no such tool — deny is the default |

The third row is the interesting one. A naive allowlist would have permitted
it: `claims.read` is a tool the agent is entitled to call. The refusal comes
from the *scope* attached to the grant, checked against the session binding.

That distinction — entitled to the tool, not entitled to this instance of the
resource — is where most agent authorisation designs fail.

## Then look at the record

```bash
task audit
```

Every line is a decision, structured, with the principal, the tool, the
arguments, the session binding, and the reason. Not "the agent ran". What it
asked for, and what it was told.

```bash
task denials
```

Refusals only. This is the view a risk or compliance function asks for, and
the one almost no agent pilot can produce.

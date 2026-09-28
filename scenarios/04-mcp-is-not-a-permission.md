# Scenario 4 — the catalogue is not a permission

```bash
task mcp-tools
task demo-agent
```

The tools now sit behind an MCP server. The agent no longer has them
hardcoded: it asks the broker what exists, and the broker asks the MCP
server.

This is how most teams are wiring agents up right now, so it is worth being
precise about what it changes. It changes where the tools live. It does not
change where the boundary is.

## What the catalogue says

```
$ task mcp-tools
claims.list        ALLOW  allowed by policy
claims.read        ALLOW  allowed by policy
payments.read      DENY   not in allowlist for principal 'claims-agent'
payments.execute   DENY   not in allowlist for principal 'claims-agent'
secrets.read       DENY   unknown tool
```

Five tools advertised. Two permitted. And `secrets.read` — a tool this
server offers that appears in no policy, that no one approved, and that the
broker refuses on the grounds that it has never heard of it.

That last row is the interesting one, because nothing about MCP prevents it.
A server publishes its own catalogue. The one in this repo is ours, so the
extra tool is a deliberate joke; next quarter the server may be a vendor's,
and the catalogue becomes a list that changes without a review.

**Deny by default is what makes that survivable.** An allowlist that names
what is permitted is unaffected by a server adding entries. A design that
derives permissions from the catalogue has handed authorship of its security
policy to whoever runs the server.

## Why the agent sees tools it cannot call

The broker hands the agent the entire catalogue, unfiltered, and the model is
told nothing about which calls will succeed. That looks careless and is
deliberate.

Filtering the list would be tidier and would protect nothing. An agent that
can compose a tool call does not need the list to have suggested it —
prompt injection supplies names directly, as scenario 3 shows, and a model
will happily invent a plausible one. A curated list is ergonomics. The
refusal at `/invoke` is the control.

Keeping them separate also keeps the audit honest. Because the model is
allowed to ask for things it cannot have, the deny log records what the agent
*attempted*, which is the question a risk review actually asks. Filter the
catalogue and those attempts disappear from the record — the system looks
cleaner and you have lost the evidence.

## The network, again

The agent has no route to the MCP server. Only the broker does.

```
bypass attempts (agent tries to reach the tools directly):
       http://claims-api:8080/claims              blocked at the network: URLError
       http://payments-api:8080/balance           blocked at the network: URLError
       http://tools-mcp:8085/mcp                  blocked at the network: URLError
```

That third line matters more than it looks. If an agent can reach the MCP
server directly, the broker is decoration: MCP has no opinion about who is
calling it, so every tool in the catalogue is available to anyone who can
open the socket.

Run `task breach` and watch that line change.

## Porting this

In your environment the MCP server is probably a vendor's, or several. Three
questions transfer:

1. **Who can reach it?** If the answer is "any workload in the namespace",
   your tool authorisation is advisory.
2. **Who decides what a principal may call?** If the answer is "the catalogue",
   that decision is being made by the server's author.
3. **What is recorded?** A tool call that succeeds inside an MCP session, with
   no record of the ones that were refused, is not an audit trail.

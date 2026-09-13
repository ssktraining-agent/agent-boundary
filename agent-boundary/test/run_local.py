"""Local test rig: run the real ConfigMap sources as plain processes.

No Kubernetes here, so this does NOT test NetworkPolicy or RBAC (unchanged
from the version that was already verified in-cluster). It tests the new
part: a model-driven agent loop, the injection reaching the model's context,
and the broker refusing what the model was talked into asking for.
"""
import json, os, subprocess, sys, time, urllib.request, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.environ.get("WORKDIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".run")
os.makedirs(WORK, exist_ok=True)
SRC = os.path.join(WORK, "src")
os.makedirs(SRC, exist_ok=True)

CLAIMS_PORT, PAYMENTS_PORT, BROKER_PORT, MODEL_PORT = 18080, 18082, 18081, 18090


def extract(path, cm_name, key, out):
    for doc in yaml.safe_load_all(open(os.path.join(ROOT, path))):
        if doc and doc.get("kind") == "ConfigMap" and doc["metadata"]["name"] == cm_name:
            open(os.path.join(SRC, out), "w").write(doc["data"][key])
            return
    raise SystemExit("could not find ConfigMap %s in %s" % (cm_name, path))


extract("k8s/20-services.yaml", "claims-api-src", "app.py", "claims_api.py")
extract("k8s/20-services.yaml", "payments-api-src", "app.py", "payments_api.py")
extract("k8s/30-broker.yaml", "broker-src", "broker.py", "broker.py")
extract("k8s/41-agent-llm.yaml", "agent-llm-src", "agent_llm.py", "agent_llm.py")

# policy is identical to the shipped one, with upstreams pointed at localhost
policy = None
for doc in yaml.safe_load_all(open(os.path.join(ROOT, "k8s/30-broker.yaml"))):
    if doc and doc.get("kind") == "ConfigMap" and doc["metadata"]["name"] == "tool-policy":
        policy = json.loads(doc["data"]["policy.json"])
for spec in policy["tools"].values():
    spec["upstream"] = (spec["upstream"]
                        .replace("claims-api:8080", "127.0.0.1:%d" % CLAIMS_PORT)
                        .replace("payments-api:8080", "127.0.0.1:%d" % PAYMENTS_PORT))
policy_path = os.path.join(SRC, "policy.json")
json.dump(policy, open(policy_path, "w"), indent=2)

procs = []


def start(name, argv, env=None):
    e = dict(os.environ)
    e.update(env or {})
    log = open(os.path.join(WORK, name + ".log"), "w")
    p = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, env=e)
    procs.append((name, p))
    return p


def wait_http(url, tries=40):
    for _ in range(tries):
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.25)
    return False


start("claims-api", [sys.executable, "-u", os.path.join(SRC, "claims_api.py")],
      {"PORT": str(CLAIMS_PORT)})
start("payments-api", [sys.executable, "-u", os.path.join(SRC, "payments_api.py")],
      {"PORT": str(PAYMENTS_PORT)})
start("broker", [sys.executable, "-u", os.path.join(SRC, "broker.py")],
      {"PORT": str(BROKER_PORT), "POLICY_PATH": policy_path,
       "AUDIT_PATH": os.path.join(WORK, "decisions.jsonl")})
start("fake-model", [sys.executable, "-u", os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_model.py")],
      {"PORT": str(MODEL_PORT), "NOTES_PATH": os.path.join(WORK, "notes.txt")})

ok = all([
    wait_http("http://127.0.0.1:%d/healthz" % CLAIMS_PORT),
    wait_http("http://127.0.0.1:%d/healthz" % PAYMENTS_PORT),
    wait_http("http://127.0.0.1:%d/healthz" % BROKER_PORT),
    wait_http("http://127.0.0.1:%d/healthz" % MODEL_PORT),
])
if not ok:
    for name, _ in procs:
        print("--- %s ---" % name)
        print(open(os.path.join(WORK, name + ".log")).read())
    raise SystemExit("services did not come up")

print("### services up\n")

r = subprocess.run(
    [sys.executable, "-u", os.path.join(SRC, "agent_llm.py")],
    env=dict(os.environ,
             BROKER_URL="http://127.0.0.1:%d/invoke" % BROKER_PORT,
             MODEL_BASE_URL="http://127.0.0.1:%d/v1" % MODEL_PORT,
             MODEL_NAME="fake-test-model",
             STAY_ALIVE="0"),
    capture_output=True, text=True, timeout=180)
print(r.stdout)
if r.returncode != 0:
    print("AGENT STDERR:\n" + r.stderr)

print("\n### broker audit stream")
try:
    for line in open(os.path.join(WORK, "decisions.jsonl")):
        print("  " + line.rstrip())
except OSError:
    print("  (none)")

print("\n### payments-api log (anything here means a boundary failed)")
pl = open(os.path.join(WORK, "payments-api.log")).read()
print("  " + ("\n  ".join(l for l in pl.splitlines() if "REACHED" in l) or "(clean)"))

print("\n### fake model assertions")
print(open(os.path.join(WORK, "notes.txt")).read())
print(open(os.path.join(WORK, "fake-model.log")).read())

for name, p in procs:
    p.terminate()

audit = [json.loads(l) for l in open(os.path.join(WORK, "decisions.jsonl"))]
allows = [a for a in audit if a["decision"] == "ALLOW"]
denies = [a for a in audit if a["decision"] == "DENY"]
reasons = sorted(d["reason"].split(":")[0] for d in denies)
breached = "REACHED" in open(os.path.join(WORK, "payments-api.log")).read()

print("\n### result")
ok = (len(allows) == 1 and len(denies) == 4 and not breached and
      reasons == ["not in allowlist for principal 'claims-agent'",
                  "not in allowlist for principal 'claims-agent'",
                  "out of scope", "unknown tool"])
print("  allowed %d, denied %d, payments reached: %s" % (len(allows), len(denies), breached))
print("  " + ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)

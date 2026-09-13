NS      := agent-boundary
CLUSTER := agent-boundary
CALICO  := https://raw.githubusercontent.com/projectcalico/calico/v3.28.2/manifests/calico.yaml

# Where the model lives, for `make demo-agent`. Defaults to Ollama on this
# machine; the address is detected because a pod cannot say "localhost" and
# mean your laptop. Override any of these on the command line:
#
#   make demo-agent MODEL_BASE_URL=https://api.example.com/v1 \
#                   MODEL_NAME=some-model MODEL_API_KEY=sk-...
HOST_IP        ?= $(shell ip route get 1.1.1.1 2>/dev/null | awk '{print $$7; exit}' \
                    || ipconfig getifaddr en0 2>/dev/null \
                    || echo host.docker.internal)
MODEL_BASE_URL ?= http://$(HOST_IP):11434/v1
MODEL_NAME     ?= llama3.2:3b
MODEL_API_KEY  ?= not-needed

.DEFAULT_GOAL := help

help: ## show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

cluster: ## create the kind cluster and install Calico (NetworkPolicy enforcement)
	kind create cluster --config kind-config.yaml
	kubectl apply -f $(CALICO)
	@echo "waiting for Calico..."
	kubectl -n kube-system rollout status daemonset/calico-node --timeout=300s
	kubectl wait --for=condition=Ready nodes --all --timeout=300s

deploy: ## apply the platform, tools, broker and agent
	kubectl apply -f k8s/
	kubectl -n $(NS) rollout status deploy/claims-api   --timeout=180s
	kubectl -n $(NS) rollout status deploy/payments-api --timeout=180s
	kubectl -n $(NS) rollout status deploy/tool-broker  --timeout=180s
	kubectl -n $(NS) rollout status deploy/claims-agent --timeout=180s

demo: ## run the fixed-sequence agent — no model, no API key, deterministic
	kubectl -n $(NS) delete pod -l app=claims-agent --ignore-not-found
	kubectl -n $(NS) rollout status deploy/claims-agent --timeout=180s
	@sleep 12
	@kubectl -n $(NS) logs -l app=claims-agent --tail=-1

model-check: ## check a model endpoint is reachable before running demo-agent
	@echo "looking for a model at $(MODEL_BASE_URL)"
	@curl -sS -m 5 -o /dev/null -w "  HTTP %{http_code}\n" $(MODEL_BASE_URL)/models \
		|| (echo "  not reachable."; \
		    echo "  For a free local one:  OLLAMA_HOST=0.0.0.0 ollama serve"; \
		    echo "                         ollama pull $(MODEL_NAME)"; exit 1)

demo-agent: ## run with a REAL model deciding the tool calls (see model-check)
	@echo "model: $(MODEL_NAME) at $(MODEL_BASE_URL)"
	kubectl -n $(NS) create configmap model-config \
		--from-literal=MODEL_BASE_URL=$(MODEL_BASE_URL) \
		--from-literal=MODEL_NAME=$(MODEL_NAME) \
		--from-literal=MODEL_API_KEY=$(MODEL_API_KEY) \
		--dry-run=client -o yaml | kubectl apply -f -
	kubectl -n $(NS) scale deploy/claims-agent-llm --replicas=0
	kubectl -n $(NS) scale deploy/claims-agent-llm --replicas=1
	kubectl -n $(NS) rollout status deploy/claims-agent-llm --timeout=180s
	@echo "waiting for the model to work through the task..."
	@sleep 30
	@kubectl -n $(NS) logs -l app=claims-agent-llm --tail=-1

test: ## run the whole flow as local processes, no cluster and no model needed
	python3 test/run_local.py

audit: ## show the broker's audit stream — every decision, allow and deny
	@kubectl -n $(NS) logs -l app=tool-broker --tail=-1 | grep '^AUDIT ' | sed 's/^AUDIT //'

denials: ## show only the refusals
	@kubectl -n $(NS) logs -l app=tool-broker --tail=-1 | grep '^AUDIT ' | sed 's/^AUDIT //' | grep '"DENY"'

rbac: ## prove the agent's service account cannot read secrets
	@echo "can claims-agent read secrets?"
	@kubectl -n $(NS) auth can-i get secrets \
		--as=system:serviceaccount:$(NS):claims-agent || true
	@echo "can claims-agent list pods?"
	@kubectl -n $(NS) auth can-i list pods \
		--as=system:serviceaccount:$(NS):claims-agent || true

breach: ## remove the network boundary and re-run — watch the bypass succeed
	kubectl -n $(NS) delete networkpolicy --all
	@$(MAKE) demo

restore: ## put the network boundary back
	kubectl apply -f k8s/50-networkpolicy.yaml

clean: ## delete the cluster
	kind delete cluster --name $(CLUSTER)

.PHONY: help cluster deploy demo model-check demo-agent test audit denials rbac breach restore clean

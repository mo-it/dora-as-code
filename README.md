# DORA-as-Code

**A Comparative Evaluation of Policy-as-Code Tools for Automated EU Regulatory Compliance in GitOps-Managed Kubernetes Environments**

MSc DevOps dissertation research artefact
Mohit Kumar Somashekar, Student ID A00047340
Technological University Dublin, Tallaght Campus
Supervisor: Mark Lynch

---

## What this project is, in plain English

The EU has a financial regulation called **DORA** (the Digital Operational Resilience Act, Regulation (EU) 2022/2554). It has been law since January 2025. It tells banks and their technology suppliers things like "you must control who has access to systems" and "you must keep data confidential". It is written as legal text, not as computer instructions.

Kubernetes has a feature called an **admission controller**. Think of it as the door staff at a restaurant. Every time someone asks Kubernetes to create something, the request has to walk past the door staff first. The door staff can say yes or no before anything is actually let in.

This project asks a simple question: **can you take the legal rules from DORA and turn them into door staff instructions that a computer enforces automatically?**

To find out, every requirement was written twice, once for each of the two most popular tools that do this job:

- **Kyverno**, which writes its rules in YAML, the same file format Kubernetes already uses
- **OPA Gatekeeper**, which writes its rules in a special language called Rego

Both sets were then deployed the same way, through a GitOps tool called **ArgoCD**, and measured head to head.

---

## What was found

Three of the four things measured came out **identical** between the two tools.

| What was measured | Kyverno | OPA Gatekeeper | Verdict |
|---|---|---|---|
| Requirements expressible at all | 86.2% (25 of 29) | 86.2% (25 of 29) | Tied |
| Requirements genuinely enforced | 58.6% (17 of 29) | 58.6% (17 of 29) | Tied |
| Detection accuracy (precision, recall, F1) | 1.000 | 1.000 | Tied |
| Extra time added to admission | about 14.5 ms | about 9.4 ms | No meaningful difference |

The headline conclusion is therefore **not** the one the proposal expected. Choosing between these two tools is not a speed decision or an accuracy decision. It is a decision about **how safe they are to write policies in, and how visibly they fail when something goes wrong.**

### The two coverage numbers, and why there are two

This is the most important number in the project, so it is worth slowing down.

- **Binary coverage (86.2%)** answers "can the tool express this rule at all?"
- **Effective coverage (58.6%)** answers "does the rule actually inspect the real thing?"

The 27.6 point gap between them is the finding. Eight of the requirements can only be checked by reading a **label that the user themselves wrote**, claiming they are compliant.

The clearest example is image signing. The policy checks for a label saying `dora.io/image-signature-verified: "true"`. But anyone can type that label onto an unsigned image. The policy checks that a claim was made. It does not check that the claim is true.

Put in restaurant terms: it is the difference between the door staff checking your ID, and the door staff accepting a note you wrote yourself saying "I am over 18".

So roughly a quarter of the DORA requirements here are automated in a **paperwork** sense, not in a **technical** sense. That distinction matters a great deal for anyone claiming regulatory compliance.

### Six findings about silent failure

Every one of these is a case where something looked healthy and was not.

1. **The same mistake breaks the two tools in opposite directions.** Seven policies in each tool checked for container settings in the wrong place. Kyverno reacted by blocking everything, including the things that were fine. Gatekeeper reacted by quietly allowing everything, including the things that were broken. Same author error, opposite results, and one of them makes no noise at all.

2. **A safety component was destroyed and nobody noticed for three weeks.** An early version of a helper script deleted the component that connects Gatekeeper to the door. Kyverno rebuilds that connection by itself within seconds. Gatekeeper does not, so its connection stayed gone. About ten hours of measurements were recorded against a tool that was completely disconnected. Every status screen reported healthy the entire time.

3. **The two tools manage that connection in opposite ways.** Kyverno constantly rebuilds its own. Gatekeeper installs its once and leaves it. That means no single technique for temporarily switching one tool off works on both, which quietly breaks any simple A/B test setup.

4. **A blocked deployment can look like a capacity problem instead of a compliance problem.** Where Gatekeeper checks the pod but not the deployment that creates it, the deployment is accepted and the pod is rejected. The command line reports success, ArgoCD reports Synced, and the app just sits there at zero copies. A compliance breach shows up as "the app did not start", which is the wrong incident category entirely.

5. **A wildcard character was read as a pattern, not as text.** One policy used `*` in a way Kyverno treats as "match anything". The result was a policy that rejected every single role, including harmless ones. It was not detecting violations. It was refusing everything.

6. **That bug survived because there was nothing safe to test against.** The test suite had no example of a *correct* role, only a broken one. A test suite made only of bad examples can prove a tool says no. It can never prove the tool ever says yes.

The general lesson running through all six: **"25 policies deployed" and "86% coverage" are not evidence that anything is being enforced.**

---

## What is in this repository

```
dora-as-code/
  requirements/       The DORA requirements register (the master list)
  policies/
    kyverno/          25 policies written in YAML
    gatekeeper/
      templates/      25 rule definitions written in Rego
      constraints/    25 instructions that switch each rule on
  manifests/
    compliant/        22 test files that should be allowed
    non-compliant/    21 test files that should be blocked
    benchmark/        19 files used only for speed testing
    expected-results.csv    The answer key
  argocd/             ArgoCD setup, plus the evidence hook
  scripts/            Automation and analysis tools
  results/            Measurements and statistical analysis
  figures/            Generated charts used in the write-up
  evidence/           Forensic records, backups, and earlier runs
  requirements.txt    Python packages needed by the scripts
```

Two folders carry an index worth reading before anything else.
`results/README.md` says which measurement file supports which claim, and which
files are retained only as a record of what went wrong.
`evidence/forensics/invalid-results/README.md` explains why the superseded
detection sweep must not be cited.

### The requirements register

`requirements/dora-requirements-register.csv` is the spine of the whole project. It has 29 rows, one per requirement pulled out of DORA Articles 5 to 15. Each row records which article it came from, what it means in technical terms, which Kubernetes object it applies to, and which policy enforces it in each tool.

Each requirement is sorted into one of four groups:

| Group | Count | Meaning |
|---|---|---|
| Fully automatable | 12 | A policy can check the real setting |
| Partially automatable | 13 | A policy can check that something was declared, but not that it is true |
| Not automatable | 3 | This is a human process, such as risk assessment |
| Not implemented | 1 | Honestly recorded as a gap, not quietly dropped |

The single not-implemented item is REQ-008, network segmentation. It was originally claimed as covered. When the register was checked mechanically, the policies it named turned out not to exist. It is recorded as a gap rather than removed, because hiding it would be the more serious error.

### The test suite

The design rule is **one problem per file**.

- Every compliant file satisfies all 25 policies at once
- Every non-compliant file satisfies 24 of them and breaks exactly one

That way, when a file is rejected, you know exactly which policy did it. An earlier version of the suite got this wrong, and every single test file failed for reasons unrelated to what it was testing, which made the results meaningless.

---

## How to run this yourself

### 1. What you need

| Component | Version used | Why this one |
|---|---|---|
| WSL2 Ubuntu | 24.04 | The whole project runs in a Linux terminal |
| K3s | v1.35.5 | A small Kubernetes that fits on a laptop |
| Kyverno | v1.18.1 | Policy engine A |
| OPA Gatekeeper | v3.22.2 | Policy engine B |
| ArgoCD | v3.4.4 | The GitOps controller |

This was all run on an 8 GB laptop with 6 GB given to WSL2. That is deliberate. It represents a small or medium sized company, not a data centre.

**Important memory note.** At the WSL2 default of about 3.8 GB, Kyverno cannot start and the cluster deadlocks. On Windows, edit `C:\Users\<YourName>\.wslconfig` and add:

```ini
[wsl2]
memory=6GB
swap=2GB
```

Then run `wsl --shutdown` in PowerShell and reopen your terminal.

### 2. Python packages

The analysis scripts need these:

```bash
pip install -r requirements.txt --break-system-packages
```

The `--break-system-packages` flag is needed on Ubuntu 24.04 because it protects the system Python by default. If you prefer to keep things separate, use a virtual environment instead:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Starting the cluster

K3s does not survive a laptop restart, so run this every time:

```bash
sudo systemctl start k3s
sleep 25
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
kubectl get nodes
```

### 4. Check before you measure anything

This step exists because of Finding 2 above. Status screens lie. Check the actual behaviour.

```bash
# Should return 8 (7 belonging to Kyverno, 1 belonging to Gatekeeper)
kubectl get validatingwebhookconfigurations --no-headers | wc -l

# Should show 24 Enforce and 1 Audit
kubectl get clusterpolicies \
  -o custom-columns='A:.spec.validationFailureAction' --no-headers \
  | sort | uniq -c

# All four Kyverno pods should read 1/1
kubectl get pods -n kyverno
```

If Gatekeeper's entry is missing, restore it from `evidence/forensics/all-webhooks-20260726-131348.yaml`.

### 5. Check the policies before deploying them

```bash
python3 scripts/validate-policies.py
```

This catches two mistakes that otherwise fail silently. It should report zero errors. Two warnings are expected and are safe, because they refer to storage and network rules that do not apply to the object type the warning is about.

### 6. Run the benchmark

```bash
./scripts/benchmark-rcbd.sh
python3 scripts/analyse-benchmarks.py \
  --results-dir results \
  --run-id <your-run-id> \
  --out results/analysis-rcbd
```

If the cluster gets stuck and refuses all changes, run `./scripts/benchmark-rcbd.sh recover`.

### 7. Rebuild the figures

This step needs no cluster. It reads the committed result files and rewrites every chart used in the write-up:

```bash
python3 scripts/generate-figures.py
```

### 8. Clean up afterwards

```bash
kubectl delete deployments --all -n dora-test
```

Leaving about 40 test pods running is what triggers the memory deadlock described above.

---

## How the speed test was designed

Measuring "which tool is faster" sounds easy and is not. The first attempt was wrong, and understanding why is part of the contribution.

**The problem.** If you run baseline first, then Kyverno, then Gatekeeper, the laptop is not in the same state each time. It warms up, background jobs come and go, and whichever tool ran first gets unfairly measured. In the first attempt, the tool order and the results were strongly correlated, which means the ordering was affecting the answer.

**The fix.** A **randomised complete block design**. The measurement runs in 12 rounds. Within each round, all three configurations run, but the order changes. There are exactly six possible orders for three items, and each order is used exactly twice. That means each configuration runs first exactly four times, second four times, and third four times. Any advantage from position cancels out.

Each round repeats four times, giving 48 measurements per configuration and 144 in total.

**Statistics.** The timing data is not shaped like a normal bell curve, which was tested and confirmed. Standard t-tests assume a bell curve, so non-parametric methods were used instead: the Friedman test to check whether any difference exists, then paired Wilcoxon tests with a Holm correction to see which pairs differ, then Cliff's delta to measure how big any difference actually is.

**The most useful thing this revealed.** Admission time is only about 17 to 18 percent of a full ArgoCD sync. ArgoCD's own natural variation is bigger than the policy engine signal, so it drowns it out. The same two engines show a clear, statistically significant difference when measured at the admission point, and no difference at all when measured through ArgoCD. Measuring sync time is simply the wrong instrument for this question, and the original proposal had planned to use exactly that.

---

## Known limitations, stated honestly

- **Speed was measured with zero-copy workloads.** Deployments still walk past the door staff, but no containers actually start. This correctly isolates door checking time, but it says nothing about workloads that really run.
- **The encrypted storage is simulated, not real.** The original design named an Amazon storage type that cannot work on K3s. A local substitute was created for the lab. It behaves like encrypted storage for policy purposes but does not actually encrypt anything.
- **Only one machine was tested.** Single node, resource constrained. Results may differ on a real cluster.
- **Every test file breaks only one rule.** Deliberately tricky cases were not tested, such as a file saying "do not run as root" while also naming the root user, or setting a minimum without a maximum. These are named here rather than left for a reader to discover.
- **The perfect 1.000 accuracy scores describe this test suite**, not all possible inputs. A test suite can only find false alarms for an object type if it contains a correct example of that object type. See Finding 6.
- **42 files are scored, 43 exist.** `manifests/compliant/req003-compliant.yaml` was added later, during the fix for Finding 5, and was verified directly rather than through the automated scoring loop. It is therefore not listed in `expected-results.csv`. This is a deliberate, recorded decision, not an oversight.
- **The PreSync validation hook was not built.** The original proposal described checking policies before ArgoCD applies anything. Enforcement here happens at the cluster door instead. Finding 4 is the argument for why the earlier check would be valuable, so this is treated as future work rather than a quiet omission.

---

## A note on reading the results folder

`results/` holds the final measurements. `evidence/` holds the record of how the project got there, including things that went wrong. Both are kept on purpose.

`evidence/forensics/` contains the earlier, broken versions of the policies, manifests and scripts. They are kept because the failures they caused are findings in the dissertation. They are not meant to be run.

---

## Licence

Released under the MIT Licence. See the LICENSE file for the full text.

In short: you may use, copy, modify and redistribute this work, including
commercially, provided you keep the copyright notice. It is supplied with no
warranty. The MIT Licence was chosen because the research proposal committed to
publishing this as an open artefact for practitioners to reuse, and without an
explicit licence default copyright law would forbid exactly that.

## Citation

If you refer to this work, please cite the dissertation:

Somashekar, M. K. (2026) *DORA-as-Code: A Comparative Evaluation of Policy-as-Code Tools for Automated EU Regulatory Compliance in GitOps-Managed Kubernetes Environments*. MSc thesis. Technological University Dublin.

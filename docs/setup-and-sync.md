# Setup and GitHub syncing

The repository contains the assistant's code, tests, documentation, dependency constraints, and resource registration templates. It does not contain an IFs installation, result databases, downloaded wiki pages, embedding weights, conversations, API keys, or generated analyses.

## First installation on another Windows machine

Use Python 3.12 and Git. Once the private repository has been published and your account has access:

```powershell
git clone https://github.com/quciet/ifs-research-assistant.git
cd ifs-research-assistant
.\scripts\setup.ps1 -Agent
.\scripts\start-agent.ps1
```

Open http://127.0.0.1:8765. In Settings, provide your own IFs development folder and model connection. Refresh the wiki to prepare the documentation cache. On a new machine, do not leave the IFs folder blank: the bundled default manifest describes the original pilot's relative folder layout.

Code research supports the layouts listed in the [agent guide](agent-guide.md). Numerical tools are enabled automatically only for byte-identical reviewed saved-result profiles. Other saved results need compatibility review.

## Optional semantic retrieval

After connecting your installation, locate its generated research.json under workspace/agent/installations/. Install the optional dependencies, then index that configuration:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[agent,semantic]' -c requirements-semantic.lock.txt --cache-dir workspace/pip-cache
.\.venv\Scripts\python.exe -m ifs_agent index --config 'workspace/agent/installations/YOUR-INSTALLATION-ID/research.json' --semantic --download-model
```

Replace YOUR-INSTALLATION-ID with the actual directory name. Initial preparation downloads model weights and can take substantial CPU time. Subsequent indexing can omit --download-model. The setup.ps1 -Semantic shortcut uses the default pilot configuration, so use the explicit config command for a different installation.

## Receive updates

Stop the assistant before updating its code, then:

```powershell
git status
git pull --ff-only
.\scripts\setup.ps1 -Agent
.\scripts\start-agent.ps1
```

If you use semantic retrieval, reinstall with the semantic extra and constraints as above. Rebuild affected indexes when the source or index format changes. Restarting clears the in-memory API key. Git does not synchronize your local workspace or IFs files.

If git status shows edits, commit or deliberately resolve them before pulling. A fast-forward-only pull stops on divergent history instead of silently creating a merge.

## Send your changes

Configure your preferred Git author identity once on your machine. Review changes and stage only intended files:

```powershell
git status
git diff
git add docs/how-it-works.md
git diff --cached
git commit -m 'Clarify the investigation workflow'
git push
```

The first publication uses git push -u origin main. Later pushes use the configured upstream. Git authenticates through your own GitHub account or credential manager; never put a token in a remote URL or tracked file. Sync is explicit, not an automatic background process.

## Local-only files

The ignore rules exclude workspace outputs, virtual environments, caches, .env files, local override files, credentials, and common database/model files. Only workspace/README.md is tracked from that directory. Keep machine-specific registrations and settings in workspace/. The bundled resources/*.json files are reviewed templates and metadata, not private copies of the result databases.

A private repository controls who can view the published project. It does not grant a redistribution license for IFs sources or data, and no open-source license is added by this setup.

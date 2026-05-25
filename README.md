# agentcost

Token attribution for AI agents — know who spent what and why.

## The problem

Your AI bill is $47K. You have no idea if it's the junior dev running Claude Code all day, the nightly batch job, or the new feature your team shipped. By the time you find out, the money's gone.

## Install

```bash
pip install agentcost
```

## SDK — two lines

```python
import agentcost
agentcost.init()  # patches anthropic, openai, litellm automatically

# your existing code unchanged
client = anthropic.Anthropic()
response = client.messages.create(...)  # tracked
```

## See your spend

```bash
agentcost report                   # last 7 days, grouped by PR
agentcost report --by user         # by developer
agentcost report --by team         # by team
agentcost report --by model        # by model
agentcost report --days 30         # last 30 days
```

Output:
```
Last 7d — grouped by pr

                                   tokens in   tokens out        cost   calls
────────────────────────────────────────────────────────────────────────────
                          PR #1234      2.4M         0.6M    $10.8000      47
                          PR #1189      0.8M         0.2M     $3.6000      12
                    (no PR)  main       0.3M         0.1M     $1.2000       8
────────────────────────────────────────────────────────────────────────────
                         TOTAL          3.5M         0.9M    $15.6000      67
```

## Add labels manually

```python
with agentcost.label(team="platform", task="code-review"):
    client.messages.create(...)   # attributed to team=platform, task=code-review
```

## Proxy — zero code changes, works for entire org

Set one env var in your platform defaults:

```bash
ANTHROPIC_BASE_URL=http://your-proxy:8080/anthropic
OPENAI_BASE_URL=http://your-proxy:8080/openai
```

Run the proxy:

```bash
docker run -p 8080:8080 agentcost/proxy
```

Label calls with headers:
```
X-Cost-Team: platform
X-Cost-PR: 1234
X-Cost-User: ken@company.com
```

Register API keys → teams (`agentcost-keys.yaml`):
```yaml
keys:
  sk-platform-prod: {team: Platform, env: production}
  sk-mobile-dev:    {team: Mobile, env: development}
```

## What gets tracked

| Signal | Source | Always? |
|--------|--------|---------|
| User | git config / CI actor | When in git repo |
| Branch / PR | git / GitHub Actions env vars | When in CI |
| Team | API key registry | When key registered |
| Custom labels | `agentcost.label(...)` | When you add them |
| Model | API response | Always |
| Token counts | API response | Always |
| Cost (USD) | Public pricing table | Always |

## Supported clients

- `anthropic` — patched at `init()`
- `openai` — patched at `init()`
- `litellm` — registered as callback at `init()`
- Proxy — works with any client that supports `base_url`

## Privacy

- Prompt content is **never** recorded or sent anywhere
- Only token counts, model names, and labels are stored
- Local log: `~/.agentcost/events.jsonl`
- Self-host the proxy: data stays in your VPC

# 06 · The mixed swarm — LangChain, PydanticAI, CrewAI, Claude and Bedrock on one record

**Profile** `scientific` · **toolkits** files, python · **instrument** on

| seat | role | held by |
|---|---|---|
| analyst | worker | a **LangChain / LangGraph** agent (`hypswarm.bridges.langchain`) |
| stats | worker | a **PydanticAI** agent (`hypswarm.bridges.pydantic_ai`) |
| critic | reviewer | a **CrewAI** crew — one agent, one task (`hypswarm.bridges.crewai`) |
| lead | lead | **Claude** over the Anthropic API, or any model over **Amazon Bedrock**, or an OpenAI-compatible model |
| *you* | reviewer | optional, `--human nicolas`: over MCP from your coding agent |

None of them knows about the others. They share one record: the scheduler issues each an order; the record
refuses the same overclaims from each of them in the same words; the instrument re-runs whatever they register.

```bash
pip install --pre "hypswarm[langgraph,pydantic-ai,crewai,anthropic,bedrock]"
python run.py --fresh                                     # every framework on a scripted model: free, offline
python run.py --real --model deepseek-ai/DeepSeek-V4.1-Flash --fresh
    # env: OPENAI_BASE_URL, OPENAI_API_KEY (the three framework agents)
    #      ANTHROPIC_API_KEY → the lead runs on Claude;  or BEDROCK_MODEL + AWS_REGION → the lead runs on Bedrock
python run.py --human nicolas                             # adds you as a reviewer; waits for your review over MCP
```

## What you see

```
=== SETTLED in 12.7s — 14 calls ===
  Q1   settled      CL1 (checked by critic)
  Q2   settled      CL2 (checked by critic)
reproduced  result=RS1 run=RUN4 confirmed=['acc_a']
reproduced  result=RS2 run=RUN5 confirmed=['a', 'b', 'p']
seats and what held them:
  analyst   worker    agent:langchain_agent
  stats     worker    agent:pydantic_ai_agent
  critic    reviewer  agent:crewai_agent
  lead      lead      scripted-lead
```

The LangChain agent counted and registered Q1; the PydanticAI agent ran the z-test and registered Q2; the CrewAI
crew reviewed both — through its own native tool-calling loop; the instrument re-ran both workers' code. The
run's budget counts the calls each framework reported (`usage_metadata`, `result.usage()`, `crew.usage_metrics`).

## How a framework agent becomes a seat

```python
from hypswarm.bridges.langchain import langchain_agent
Seat("analyst", "worker", agent=langchain_agent(lambda tools: create_react_agent(llm, tools)))
```

The bridge gets the record's tools as hypswarm `Tool`s, translates them to the framework's native tool shape
(`StructuredTool`, `pydantic_ai.Tool`, `crewai.tools.BaseTool`), runs the agent on the order with the seat's system
prompt, and returns what it used. If the agent doesn't call `return_work` itself, the bridge returns the order with
the agent's final answer as the note. Everything else — done, refusals, reproduction, provenance — is the record's,
exactly as for a native seat. Your own framework is one `async def agent(order: AgentOrder) -> AgentOutcome` away;
see `10-custom-seat-and-toolkit`.

## The scripted models

`scripted.py` holds a scripted `BaseChatModel`, a PydanticAI `FunctionModel` and a CrewAI `BaseLLM` that answer
through each framework's real tool-calling path. They show every framework meeting the same record; they cannot
show a model reasoning badly — run `--real` for that.

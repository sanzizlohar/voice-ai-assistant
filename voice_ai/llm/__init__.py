"""LLM brain: OpenAI-compatible chat engines + a ReAct-style tool loop.

One adapter covers Ollama (local, free), Groq, OpenAI, OpenRouter,
LM Studio — anything speaking the ``/v1/chat/completions`` protocol:

    # local & free (auto-detected when Ollama is running)
    ollama pull llama3.2
    # or point at any cloud provider
    export VIA_LLM_BASE_URL=https://api.groq.com/openai/v1
    export VIA_LLM_API_KEY=gsk_...
    export VIA_LLM_MODEL=llama-3.1-8b-instant

The agent loop is deliberately simple and model-agnostic (no vendor
function-calling needed): the model may reply with a JSON tool call,
the ActionCenter executes it, the observation goes back in — up to 3
rounds — then the final text is spoken aloud.
"""

# Rica

**Runtime Intelligent Coding Assistant**

Autonomous coding agent for the ALARA system.

## Setup

  cd C:\Users\Anubhav Gupta\Desktop\Projects\Rica
  pip install -e . --break-system-packages

## Usage from ALARA

  from rica import RicaAgent

  agent = RicaAgent({
      "api_key": "YOUR_GEMINI_KEY",
      "model": "gemini-2.5-flash"
  })
  result = agent.run(
      "build a flask REST API with /health endpoint"
  )

## Standalone CLI

  rica run --goal "build hello world" \
    --api-key YOUR_KEY

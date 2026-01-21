**Architecture**

Simple ASCII diagram:

```
 +----------------+      +----------+      +-----------+
 |   FastAPI App  | <--> |  GitHub  | <--> | new_ansible|
 | (agent logic)  |      +----------+      +-----------+
 |  - AWX client  |      +----------+
 |  - LangChain   | <--> |  Ollama  |
 |  - Teams webhook|     +----------+
 +----------------+
        |
        v
    +-------+
    |  DB   |  (Postgres)
    +-------+
```

Problem statement, tools, and deployment steps are in README and the root docs folder.

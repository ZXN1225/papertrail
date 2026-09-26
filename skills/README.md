# Developer Workflow Skills

This directory contains human-facing workflow guides for contributors and coding assistants working on the PaperTrail repository. These files are not part of the PaperTrail runtime and are never read by the Agent.

The runtime research skills live only in `backend/app/agent/skills.json`. They contain bounded task instructions and fixed tool names; the harness validates them and limits the model to the declared, currently enabled tool subset. Do not move runtime definitions into this directory or load developer guides into model prompts.

Keep workflow guides procedural and repository-focused. They may describe review and verification steps, but must not contain credentials, paper full text, local databases, or private evaluation labels.

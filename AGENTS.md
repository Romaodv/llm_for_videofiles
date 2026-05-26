# AGENTS.md

## Overview

This repository follows a pragmatic engineering approach focused on:
- fast iteration;
- clear architecture;
- local-first development;
- extensibility;
- maintainability;
- minimal unnecessary abstraction;
- practical MVP delivery before overengineering.

The project is an AI-powered local knowledge/navigation system that indexes technical documents, transcripts, snippets and codebases using manual indexing workflows and RAG concepts.

The user is a senior SAP technical/fullstack developer with strong architecture and integration background. Development decisions should prioritize:
- clarity;
- extensibility;
- debuggability;
- modularity;
- cost awareness;
- local execution when possible.

---

# Core Principles

## 1. MVP First

Always implement the simplest working version first.

Avoid:
- premature abstractions;
- enterprise patterns without need;
- microservices;
- Kubernetes;
- complex orchestration;
- excessive DDD/CQRS layers.

Prefer:
- modular monolith;
- clear separation of concerns;
- simple local execution;
- SQLite initially;
- local vector database.

---

# Development Style

## Preferred Characteristics

Code should be:
- explicit;
- readable;
- pragmatic;
- strongly structured;
- easy to debug;
- easy to replace later.

Avoid:
- magical frameworks;
- hidden side effects;
- overuse of decorators/metaprogramming;
- unnecessary generics;
- deeply nested abstractions.

Prefer:
- service-oriented modules;
- explicit interfaces;
- small focused files;
- typed models where possible;
- isolated providers.

---

# Architecture Preferences

## Backend

Preferred:
- Python + FastAPI
- SQLAlchemy or lightweight ORM
- Pydantic models
- clear service layer
- repository layer only if needed

Avoid:
- excessive enterprise boilerplate
- unnecessary async complexity
- premature event-driven architecture


---

# Frontend

Preferred:
- React
- clean UI
- functional components
- minimal dependencies
- local state first

Avoid:
- Redux unless necessary
- overly complex UI systems
- excessive animations

UI philosophy:
- tool-like;
- technical;
- efficient;
- information dense;
- desktop-oriented.

---

# AI / RAG Philosophy

## Important

This is NOT a generic chatbot project.

The project should behave like:
- a technical knowledge navigator;
- a semantic explorer;
- a local technical assistant.

Responses MUST:
- cite sources;
- show file names;
- show timestamps when available;
- explain where information came from.

Transparency is more important than sounding intelligent.

---

# Indexing Philosophy

## Manual Indexing

The application MUST NOT automatically index files.

Indexing should happen only:
- when the user explicitly clicks "Index";
- when the user explicitly clicks "Reindex".

The user wants full control over:
- processing;
- costs;
- storage;
- LLM usage.

---

# File Processing Guidelines

## Supported files

Priority support:
1. .srt
2. .txt
3. .md
4. source code
5. .pdf

## SRT Handling

SRT files are extremely important.

Requirements:
- preserve timestamps;
- preserve chunk boundaries;
- support timeline navigation;
- generate summaries with approximate timestamps;
- allow source tracing.

---

# Chunking Philosophy

Prefer:
- semantic chunks;
- medium-sized chunks;
- overlap between chunks.

Avoid:
- tiny fragmented chunks;
- excessively large chunks.

Typical chunk size:
- 500–1500 characters
- depending on content type

Code chunks should respect:
- functions;
- classes;
- logical blocks.

---

# LLM Strategy

## Local-first capable

The architecture MUST support:
- local LLMs via Ollama;
- cloud LLMs via Bedrock.

Never tightly couple the system to a single provider.

Always implement provider abstraction.

Example:
- BaseLLMProvider
- OllamaProvider
- BedrockProvider

---

# Preferred AI Models

## Local Models

Preferred local models:
- qwen2.5
- llama3.x
- mistral
- gemma

## Embeddings

Preferred:
- nomic-embed-text
- bge-m3
- multilingual-e5

## Cloud Models

Preferred Bedrock setup:
- Claude Haiku for summaries/general use
- Claude Sonnet for complex reasoning
- Titan Embeddings V2 for embeddings

---

# Performance Philosophy

This project should run comfortably on:
- consumer laptops;
- 16GB RAM systems.

Avoid:
- giant local models;
- unnecessary GPU requirements;
- memory-heavy pipelines.

Indexing can be slower.
Querying should feel responsive.

---

# Database Philosophy

## Primary DB

Use SQLite initially.

Avoid PostgreSQL unless clearly needed.

## Vector DB

Preferred:
- ChromaDB
- LanceDB

Keep storage local-first.

---

# UX Philosophy

The app should feel like:
- a developer tool;
- a local knowledge explorer;
- a technical workstation utility.

Prefer:
- dense information;
- quick navigation;
- filesystem-like experience;
- searchable interfaces.

Avoid:
- excessive whitespace;
- mobile-first constraints;
- consumer-app aesthetics.

---

# Error Handling

Always:
- fail clearly;
- log meaningful messages;
- expose useful debug information.

Avoid:
- silent failures;
- generic exceptions;
- hidden retries.

---

# Logging

Use structured logging.

Important events:
- indexing started;
- indexing completed;
- chunk generation;
- embedding generation;
- LLM requests;
- cache hits;
- skipped files;
- hash changes.

---

# File Hashing

The system should:
- hash files;
- detect modifications;
- avoid unnecessary reprocessing.

Preferred metadata:
- file hash
- modified date
- indexed date
- chunk count
- embedding version

---

# Code Quality

Prioritize:
- maintainability;
- readability;
- debuggability.

Prefer:
- explicit naming;
- straightforward functions;
- simple flows.

Avoid:
- clever code;
- overengineering;
- unnecessary abstractions.

---

# Documentation

Every important module should include:
- purpose;
- flow;
- responsibilities.

README should explain:
- architecture;
- setup;
- indexing flow;
- providers;
- local model setup;
- Bedrock integration.

---

# Iteration Strategy

Development should happen incrementally:

1. Basic folder navigation
2. Manual indexing
3. SQLite metadata
4. Chunk generation
5. Embeddings
6. Vector search
7. LLM summaries
8. Question answering
9. Source citations
10. UI improvements

Never attempt everything at once.

---

# Technical Taste Notes

The project owner values:
- practical architecture;
- cost/performance balance;
- modularity;
- extensibility;
- local-first capability;
- clean UX;
- strong debugging visibility.

The owner frequently works with:
- SAP;
- integrations;
- technical documentation;
- transcriptions;
- code snippets;
- architecture analysis.

The app should eventually work very well for:
- SAP KT sessions;
- CPI discussions;
- RAP/Fiori references;
- code explanation;
- architecture notes;
- technical knowledge retrieval.

---

# Final Rule

Always prefer:
- simple and extensible
over
- complex and theoretically perfect.

A working, maintainable MVP is more valuable than an overengineered architecture.
# Project Goals

This project has two purposes:

1. **Product:** build an RSS sorter that collects AI news only and scores each article against my interests.
2. **Learning:** practice AI-assisted development by trying new tools and workflows to code as efficiently as possible.


## Success criteria

- I score 30 articles by hand on a 1–10 scale, then the sorter scores the same 30 articles.
- The project succeeds if, for each article, the sorter's score is within ±3 points of mine.


# Technologies, Concepts & Everything I've learned 

- Using Claude Code within Cursor
- Grilling (an interview where the AI asks questions to clarify and refine SPEC.md)
- Writing very simple files myself that explain my needs in natural language, then asking Claude to refine them based on a grilling session.
- Using an AGENTS.md file (CLAUDE.md in my case) as a set of guidelines and rules for development 
- Changing context for each task saves costs, increases speed, and avoids noise and self-confirmation
- To keep a good knowledge of the codebase and efficiently review the AI's work, I want it to systematically give me a list of every file created/modified/deleted.
- Agents and their usefulness.
  - I created a dedicated "Spec-Reviewer" agent to inspect code with a fresh, critical eye. It helped me find CI errors that the writing agent hadn't seen (CI ran twice, on both push and pull request).
  - I also created a "Security-Auditor" agent to check that no personal information or keys were public in the project.
- Using a proper plan and documentation so that every agent is on the same page and can easily follow it once it has been written.


# Journal

| Task | Estimated time without AI | Actual time with AI | AI mistakes / Notes |
|-------|----------------------|--------------------|-----------------|
|Setting up the full project | 1h | ~1h| Roughly the same time, but much higher quality than if I hadn't used AI. The AI tends to be too verbose in some files; I'm worried it may saturate the context a bit, to be checked.|
|Writing the SPEC | 20 min | 10 min | Used grilling to write an effective spec that the AI can understand. |
|Finding feeds | 1h | 10 min | Searching and sorting that would have taken me hours. Maybe slightly less precise than a human, but mixing the two is probably the best solution, so I'm adding a few personal sources to the set.|
|Setting up the CI (lint, basic GitHub Action...) | 40 min | 10 min| Since GitHub lets us roll back efficiently, I added a rule forcing the AI to ask me before running any Git command.|
|Write a plan for the project | 20 min | 2 min | To prevent a single prompt from tackling too large a part of the project at once, I added rules forbidding any (substantial) work without first creating a plan, or without following an existing one. |
|Phase 1: Input validation | 30 min | 20 min | A tendency to be both too verbose and not clear enough in its answers; I'm planning a rule in CLAUDE.md to change that. The Spec-reviewer agent reports small errors I wouldn't have seen otherwise. |
|Phase 2: Feed fetching and candidates | 45 min | 20 min | To fulfill the plan, it writes what may be too many tests for this project, which consumes a lot of tokens; I'm writing a rule to stick to tests suited to the project's scope. |
|Phase 3: Keyword pre-filter and deterministic ranking | 1h | 10 min | The review it gives of its own work doesn't quite suit me and lacks readability, so I'm creating a rule. I want to be able to test more often, so I ask it to explain how I can test its work myself. |
|Phase 4: LLM layer | 3h | 30 min | I'm adding security rules ahead of adding API keys to the project, plus a new agent that makes sure no sensitive data leaks. Selected the first LLM using a separate context. |
|Phase 5: Digest and state | 1h | 20 min | Some inconsistency in how results are explained across contexts; my CLAUDE.md should be more precise. |
|Phase 6: CLI and end-to-end pipeline | 1h | 30 min | Surprising mix of French and English in the answers; I'm updating the rules. |
| Phase 7: eval subcommand | 4h | 2h | Set up a benchmark to test several models. Problem: benchmarking is hard, because it's hard to make an AI understand a human's scoring choices... |
|Phase 8: Scheduling and v1 release | 1h | 30 min | Small mix-up regarding the main branches, but quickly resolved!|

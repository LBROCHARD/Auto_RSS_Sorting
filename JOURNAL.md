# Project Goals

This project has two purposes:

1. **Product:** build an RSS sorter that collects AI news only and scores each article against my interests.
2. **Learning:** practice AI-assisted development by trying new tools and workflows to code as efficiently as possible.


## Success criteria

- I score 30 articles by hand on a 1–10 scale, then the sorter scores the same 30 articles.
- The project succeeds if, for each article, the sorter's score is within ±3 points of mine.


# Technologies, Concepts & Everything I've learned 

- Usage of Claude Code within Cursor
- Grilling (an interview, where the IA asks questions to precise and refine the SPEC.md)
- To redact very simples files myself explaining my needs in natural language, and ask claude to refine it, based on a grilling session.
- Using an AGENTS.md (or CLAUDE.md in my case) file, as a guideline and set of rules for development 
- Changing contexte for each tasks helps you save costs, augments speed, and avoid noise or auto-confirmation
- To keep an good knowledge of the codebase, and efficiently review the AI's work, I want it to systematically give me a list of every files created/modified/deleted.
- Agents, and their utility.
  - I created a special "Spec-Reviewer" agent, to inspect code with a fresh and critical viewpoint. It helped me find CI errors that the writing agent didn't saw (CI launched 2 times both during push and in pull request).
  - I also created a "Security-Auditor" agent, to check that no personal informations / keys where public in the project.
- Using a proper plan/documentation, so that every agent is on the same page, and once it has been written, they can easiely follow it.


# Journal

| Tâche | Temps estimé sans IA | Temps réel avec IA | Erreurs de l'IA / Remarques |
|-------|----------------------|--------------------|-----------------|
|Setting up the full project | 1h | ~1h| a peu près le même temps mais beaucoup plus qualitatif que si je n'avais pas utilisé l'IA. L'IA a tendance a être trop verbeuse sur certains fichiers, j'ai peur de saturer un peu le contexte, à vérifier.|
|Writing the SPEC | 20 min | 10 min | utilisation du grilling pour rédiger une spec efficace et compréhensible par l'IA |
|Finding Feeds | 1h | 10 minutes | recherche et tri qui m'aurait pris des heures, peut être un petit peu moins précis qu'un humain, mais faire un mélange des 2 est surement la meilleur solution, j'injecte quelques sources perso dans l'ensemble.|
|Setting up the CI (Lint, Basic GitHub action...)  | 40 min | 10 min| Comme github nous permet efficacement de faire des retours en arrière, j'ai ajouté une règle pour obliger l'IA a me demander avant d'effectuer toute commande Git.|
|Write a plan for the project | 20 min | 2 min | Pour éviter qu'un prompt essaie de s'ocupper d'une trop grosse part du projet d'un coup, j'ai ajouté des règles initerdisant d'effectuer un travail (conséquent) sans créer un plan auparavant, ou sans suivre un plan qui existe déjà. |
|Phase 1 : inputs validation | 30 min | 20 min | Une tendance à être à la fois trop verbeux et pas assez compréhensible dans ses réponse, je prévois une règle dans CLAUDE.md pour modifier cela. L'agent Spec-reviewer remonte des petites erreurs que je n'aurais pas vu sinon. |
|Phase 2: Feed fetching and candidates | 45 min | 20 min | Il écrits une quantitée de tests peut être trop élevé pour le projet pour remplir le plan, cela consomme beaucoup de tokens, j'écris une règle pour se contenter des tests adaptées au scope du projet. |
|Phase 3: Keyword pre-filter and deterministic ranking | 1h | 10 min | La review qu'il me donne de son travail ne me convient pas tout a fait, et manque de lisibilitée, je crée une règle. Je veux pouvoir tester plus souvent, je lui demande de m'expliquer comment tester ce qu'il fait par moi même. |
|Phase 4: LLM layer | 3h | 30 min | J'ajoute des règles de sécurité en prévision de l'ajout de clé d'API dans le projet, + un nouvel agent qui s'assure qu'il n'y a pas de fuite de donées senseibles. Selection du premier LLM avec un autre contexte. |
|Phase 5: Digest and state | 1h | 20 min | Une certaines incohérence d'explications des resultats entre les contextes, il faudrait que mon CLAUDE.md soit plus précis. |
|Phase 6: CLI and end-to-end pipeline | 1h | 30 min | Mélange étonnant de français et d'anglais dans les réponses, je mets à jour. |
| Phase 7: eval subcommand | 4h | 1h | Benchmark, Difficile de faire un benchmark entre un humain et une machine avec un prompt. |
| | | | |

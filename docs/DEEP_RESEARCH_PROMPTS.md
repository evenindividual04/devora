# Deep Research Prompts

Prompts designed for Gemini Deep Research / Perplexity / similar tools that do multi-source
synthesis. Each prompt is scoped to a specific open question in this project.

---

## Prompt 1: GitHub README Quality — Deep Dive

**Use when**: Improving narrative generation quality, archetype templates, or output evaluation.

---

```
Research question: What specifically makes a GitHub developer profile README exceptional,
and how do the best examples achieve their effect?

I am building an AI tool that auto-generates GitHub profile READMEs from a developer's
GitHub activity data (commit history, repo metadata, language usage, PR/issue counts, stars).
I want to understand the gap between what current AI generation produces (structured, complete,
generic) and what the best human-authored profiles achieve (specific, alive, memorable).

Please research the following with depth and specificity:

## 1. Real Examples Analysis
Find and analyze 10-15 of the most widely cited "exceptional" GitHub profile READMEs.
For each, identify:
- What specific structural or narrative device makes it memorable
- What data or evidence it cites about the developer
- How it handles the tension between humility and confidence
- What a reader learns about this person that they couldn't learn from the repo list alone

Look specifically for profiles from: torvalds, simonw, sindresorhus, nickvdyck, midudev,
cassidoo, bdougie, dan-abramov, gaearon, antirez, jonschlinkert, tj, substack, and any
others your research surfaces as exemplary.

## 2. What Technical Hiring Managers Actually Look For
Research what senior engineers and technical hiring managers actually look for when visiting
a developer's GitHub profile (not what they say they look for — what the evidence shows):
- Do they read the README at all, or go straight to pinned repos?
- What signals from a README increase the probability of a follow-up action (email, interview)?
- What immediately disqualifies a profile?
- How do senior engineers evaluate a junior vs senior profile differently?
- What is the "30-second test" — what can a skilled reader infer about a developer in 30 seconds?

## 3. Archetype-Specific Structure Research
For each of these developer archetypes, find 3-5 real exemplary profiles and identify the
specific structural and narrative patterns that work for that archetype:
- OSS maintainer (maintainer of a widely-used project)
- ML researcher / experimenter
- Systems / infrastructure engineer
- Hobbyist / learner (many small projects, exploration-oriented)
- Tooling developer (builds dev tools for other developers)
- Product engineer (ships end-to-end features)
- Academic researcher with public code

For each archetype: What sections work? What tone works? What evidence is most credible?
What framing mistakes are common?

## 4. The "Currently Working On" Pattern
Research the "currently working on" or "now" section specifically:
- How do the best profiles frame current work?
- What level of specificity is optimal?
- How do profiles that update this section dynamically (GitHub Actions) compare to static ones?
- What does leaving this section blank signal?
- How should a hobbyist vs a professional frame their current focus differently?

## 5. Language and Voice Patterns
Conduct a close reading analysis of the language patterns in exceptional vs mediocre profiles:
- What sentence structures signal authenticity vs AI generation?
- What is the optimal ratio of technical specificity to general framing?
- How do the best profiles handle admitting gaps or weaknesses?
- What specific vocabulary choices signal a senior engineer vs a junior?
- How does first person vs third person vs second person affect perception?

## 6. The Pinned Repository Narrative
Research how exceptional developers use their 6 pinned repositories as a narrative:
- What selection criteria produce a coherent identity vs a random showcase?
- How should the pinned repos relate to the README text?
- What does the ordering of pinned repos signal?
- How do maintainers vs explorers use pinned repos differently?

## 7. Quantitative/Empirical Evidence
Find any empirical research or data on:
- Does profile quality correlate with collaboration invitations or job offers?
- Are there A/B tests or natural experiments comparing profile approaches?
- What GitHub profile elements get the most clicks/engagement?
- Any academic research on developer identity presentation or open source participation signals

## 8. Anti-patterns Taxonomy
Create a comprehensive taxonomy of README anti-patterns beyond the obvious clichés:
- Structural anti-patterns (section order, length, density)
- Voice anti-patterns (tone, person, register)
- Evidence anti-patterns (what kinds of evidence backfire)
- Visual anti-patterns (badge overload, emoji overload, wall of text)
- Signal anti-patterns (what data points are overrepresented but low-signal)

## Output Format
For each section, provide:
1. The key findings with specific examples (name actual GitHub usernames and quote actual text)
2. The principle being illustrated
3. How to apply this in an automated generation system (what prompt guidance, what structural
   rules, what evaluation criteria)

Also provide a scoring rubric: given a generated README, what dimensions would you evaluate
it on, and what does a 1/5 vs 5/5 look like on each dimension? Make this specific enough
to use as a benchmark for an LLM-as-judge evaluation system.
```

---

## Prompt 2: GitHub Signal Analysis — What Data Actually Predicts Developer Identity

**Use when**: Improving `analysis_service.py` signal computation or archetype classification.

---

```
Research question: Which GitHub activity signals are actually predictive of developer type,
quality, or career stage, and how should they be weighted in a classification system?

I am building a GitHub profile analyzer that computes ~35 signals from a developer's public
GitHub activity (commit history, repo metadata, language patterns, PR/issue counts, star counts,
fork ratios, commit message quality, temporal patterns). These signals feed into an archetype
classifier that assigns developers to types like "OSS Maintainer", "ML Experimenter",
"Systems Builder", "Hobbyist Explorer", etc.

Please research the following deeply:

## 1. Academic and Industry Research on GitHub Mining
Find and synthesize research on GitHub data mining as a signal for developer skills/identity:
- MSR (Mining Software Repositories) conference papers on developer classification
- Papers on using GitHub activity to predict expertise, seniority, or specialization
- Research on commit patterns as signals (frequency, size, message quality)
- Research on the "bus factor" and maintainer identification
- Any studies validating automated developer profiling

Key papers to look for (and their findings):
- Research on commit message quality as a proxy for software engineering skill
- Studies on language diversity vs depth as a developer signal
- Work on social coding patterns (PRs, issues, forks) as identity signals
- Research distinguishing "authors" from "contributors" in OSS

## 2. Commit Signals: What's Actually Predictive
For each of these commit-derived signals, research what is actually known about
their predictive validity:

- Commit frequency (commits/week) — what does high vs low actually indicate?
- Average churn per commit (lines changed) — large vs small commits as a signal
- Commit message quality — how to measure it, what it predicts
- Feature/fix/refactor ratio — how to classify, what each ratio means
- Weekend vs weekday activity — what does this actually signal?
- Time-of-day patterns — any evidence this means something?
- Commit streak (consecutive active days/months) — predictive of what?

## 3. Repository Signals: Depth vs Breadth
Research what repository-level signals actually mean:
- Star count: what does it actually measure vs what people assume it measures?
- Fork ratio: what does having many forks (own repos) vs few forks mean?
- Repo age and maintenance signals: how to distinguish active vs abandoned projects?
- Language diversity: what's the right way to measure and interpret this?
- README presence/quality as a signal
- The "toy project" vs "production project" distinction: can it be detected automatically?
- How do "coursework" repos differ in detectable ways from other repos?

## 4. Social Signals: PRs, Issues, and Collaboration
Research what cross-repo activity signals mean:
- PR count authored: what thresholds are meaningful? What does high PR count indicate?
- Issue count: reporters vs fixers, what does each signal?
- Code review participation: available from GitHub? What does it signal?
- Fork-and-extend behavior vs original authorship
- Being forked by others vs forking others

## 5. Temporal Signals: Trajectory and Consistency
Research temporal activity patterns:
- What does a "growing" trajectory actually indicate vs "declining"?
- How long a window is needed for reliable trajectory detection?
- Seasonality: developers in education have different patterns than professionals
- Language shift over time: what does adopting a new primary language indicate?
- Burst patterns vs sustained activity: what does each indicate about developer type?

## 6. The Archetype Classification Problem
Research automated developer classification specifically:
- Are there existing developer taxonomy frameworks (beyond "junior/mid/senior")?
- How do OSS ecosystem roles map to detectable signals? (maintainer, contributor, consumer)
- Research on the "Developer persona" concept in the developer relations field
- How do self-identified developer "types" from surveys compare to signal-detected types?
- What is the false positive/negative rate typically achievable in rule-based vs ML classification?

## 7. What Signals Are Most Misused or Misunderstood
Research the common pitfalls in GitHub signal analysis:
- Why star count is a misleading signal and what to use instead
- The "contribution graph" gaming problem
- Why commits/day can be inversely correlated with code quality in some contexts
- The "small repo count, high quality" vs "large repo count, mixed quality" distinction
- How bots, automated commits, and CI noise affect signal calculation

## Output Format
For each signal category, provide:
1. What the research says it reliably indicates (if anything)
2. What thresholds or distributions are meaningful (if known)
3. What it is commonly misinterpreted as indicating
4. How it should be weighted relative to other signals
5. Any ground truth validation approaches

Also provide: a recommended set of 10-15 highest-validity signals (from this set or new ones)
ranked by their predictive value for developer identity/archetype classification, with justification.
```

---

## Prompt 3: Developer Identity & Personal Branding — Narrative Theory

**Use when**: Improving prompt design, honesty modes, or report narrative structure.

---

```
Research question: How do skilled technical writers, developer advocates, and career coaches
approach the challenge of writing authentic developer identity narratives, and what frameworks
apply to automated profile generation?

## 1. Developer Advocacy and Personal Branding Frameworks
Research how developer relations professionals think about developer identity:
- What frameworks do DevRel teams use to help engineers build public profiles?
- How do technical writing professionals approach "about me" pages for engineers?
- What is the difference between a portfolio narrative and a resume narrative?
- How do the best engineering blogs establish a distinctive voice?
- Research on the "developer persona" concept and its components

## 2. The Authentic vs Performed Identity Problem
Research the authenticity-performance tension in developer profiles:
- When does self-presentation cross from authentic to performative?
- How do open source developers navigate the tension between "work for myself" and "work for an audience"?
- Research on imposter syndrome in public technical identity — how do profiles that feel
  authentic handle this differently from ones that feel defensive?
- The "humble brag" problem: how do the best profiles avoid it?

## 3. Career Stage Framing
Research how profiles should differ by career stage:
- How does a junior developer establish credibility without experience?
- How does a mid-level developer signal readiness for senior roles?
- How does a senior engineer signal they are still growing vs settled?
- How does a principal engineer signal breadth of impact vs individual contribution?
- How should someone transitioning careers (e.g., scientist → engineer) frame their identity?

## 4. Honesty Mode Research
I have six "honesty modes" for generating profiles:
- Authentic (as-is, no editorializing)
- Polished (strengths-forward professional)
- Recruiter (optimized for technical hiring manager)
- Playful (informal, personality-forward)
- Technical (dense with specifics for engineer peers)
- Brutally Honest (names weaknesses explicitly)

Research: are these the right modes? What does the evidence say about which framing
approaches are most effective for different goals? Are there important modes missing?
What are the failure modes of each?

## 5. Gap Handling Strategies
Research specifically how to handle weakness and gap signals in a profile:
- What are the most effective strategies for handling an incomplete or sparse portfolio?
- How do the best profiles acknowledge gaps without dwelling on them?
- Is it better to redirect, reframe, or omit gaps entirely?
- What does behavioral research say about how readers interpret explicit gap acknowledgment
  vs omission vs deflection?

## 6. The Narrative Arc Problem
Research narrative structure specifically for developer profiles:
- What story structures (beyond chronological) work for technical identity?
- How do profiles that use the "I was trying to solve X" framing compare to ones that list credentials?
- Research on "origin story" effectiveness in professional identity presentation
- How should a profile handle a career that changed direction?

## Output Format
Provide findings with:
1. The specific technique or framework with a named source
2. How it applies to automated narrative generation
3. Concrete before/after examples where possible
4. Any evidence of effectiveness (research studies, practitioner consensus, case studies)

Also: suggest 3-5 additional "honesty modes" or profile variants I haven't thought of,
with rationale for why each would be useful.
```

---

## Prompt 4: LLM Evaluation for Generated Developer Profiles

**Use when**: Building an evaluation/benchmark system for generated README quality.

---

```
Research question: How should I design an LLM-as-judge evaluation system for auto-generated
GitHub profile READMEs, and what does the research say about reliable quality measurement?

Context: I am building a GitHub profile analyzer that uses Gemini to generate developer
profile READMEs from GitHub activity signals. I want to build an automated evaluation
system that can score generated profiles on quality dimensions and detect regressions.

## 1. LLM-as-Judge Research
Research the current state of using LLMs as quality judges for generated text:
- What does the research say about reliability and validity of LLM-as-judge for long-form text?
- What biases do LLM judges have (self-preference, position bias, length bias)?
- What prompt techniques produce more reliable LLM judgments?
- How does inter-rater reliability between LLM judges compare to human judges?
- What quality dimensions are LLMs good vs bad at evaluating?

## 2. Evaluation Dimensions for Developer Profiles
Research what dimensions matter for evaluating developer profile quality:
- How should "specificity" be operationalized as a measurable dimension?
- How should "authenticity" be operationalized (not just "does it sound human")?
- What is a reliable way to measure "falsifiability" — that claims are grounded in evidence?
- How to measure tonal appropriateness for the target audience?
- How to detect generic phrases or anti-patterns automatically?

## 3. Reference-Based vs Reference-Free Evaluation
Research the tradeoffs:
- When should evaluation compare generated output to a "gold standard" human-written README?
- When should evaluation be reference-free (purely judging the output on its own merits)?
- How do automated metrics (ROUGE, BERTScore, etc.) perform on this kind of task?
- What does the research say about using the source data (signals) as a reference for
  factual grounding checks?

## 4. Benchmark Dataset Design
Research how to build a benchmark for this specific task:
- How would I collect a ground-truth dataset of high-quality GitHub READMEs with labels?
- What labeling protocol would produce reliable quality annotations?
- How many examples are needed for a reliable benchmark?
- How should I handle the problem that "quality" is partly subjective and audience-dependent?
- What existing benchmarks for profile generation or biography generation exist?

## 5. Regression Detection
Research how to detect quality regressions in generated text systems:
- What statistical approaches are reliable for detecting distribution shift in LLM outputs?
- How should I design a canary test set that reliably catches quality regressions?
- What is a reasonable threshold for "statistically meaningful" quality drop?
- How do production LLM systems monitor output quality over time?

## Output Format
Provide a concrete evaluation framework:
1. 5-8 quality dimensions with operationalizable definitions
2. For each dimension: what a score of 1/5 vs 5/5 looks like (with examples)
3. A recommended prompt template for LLM-as-judge evaluation of this specific task
4. A recommended benchmark design (size, labeling protocol, sampling strategy)
5. A recommended production monitoring approach
```

---

## Prompt 5: OSS Ecosystem Signals — What Community Metrics Actually Mean

**Use when**: Improving star/fork/PR signals in `analysis_service.py` or `github_client.py`.

---

```
Research question: What do GitHub community metrics (stars, forks, watchers, PRs, issues)
actually measure, and how should they be interpreted for developer identity profiling?

I am computing OSS community signals from GitHub API data to classify developers. I want
to understand what these metrics actually measure vs common misconceptions, and how to
use them correctly in a developer identity analysis system.

## 1. Star Count: What It Actually Measures
Research the star count signal specifically:
- Academic research on GitHub stars as a quality/popularity signal
- Studies on "star inflation" — GitHub stars campaigns, bought stars, etc.
- How does the distribution of stars look across GitHub? (Power law? What's the 50th/75th/95th percentile?)
- What star count thresholds are meaningful for different interpretations?
  (e.g., "has community attention" vs "widely adopted" vs "viral")
- Studies comparing star count to actual usage (download counts, dependency graph data)
- How to interpret a developer with one 10k-star repo vs ten 1k-star repos vs 100 small repos?

## 2. Fork Ratio and What Forking Behavior Signals
Research fork behavior specifically:
- What does a high fork-to-star ratio indicate?
- What does being forked frequently (others forking your repos) signal vs forking others?
- How should "contribution forks" (fork to PR) be interpreted differently from "use forks" (fork to deploy)?
- Research on fork-based vs PR-based contribution patterns

## 3. PR and Issue Activity
Research cross-repo contribution signals:
- What does a high PR-authored count actually indicate about developer type?
- Research on the "1% rule" of open source contribution (1% create, 9% contribute, 90% consume)
- How do PR-authored counts distribute across GitHub users?
- What does issue-opened count indicate vs PR-opened count?
- Is there research on the correlation between PR activity and developer expertise?
- How should "PRs to own repos" vs "PRs to others' repos" be distinguished and weighted?

## 4. Temporal Patterns and What They Signal
Research what activity timing patterns mean:
- Are weekend commits a signal of passion or poor work-life balance? What does research say?
- What does consistent late-night activity signal?
- How do activity bursts (hackathon-style) compare to sustained activity in predictive value?
- Research on developer productivity cycles and how they show up in commit history

## 5. Language Adoption Patterns
Research what language usage patterns indicate:
- How do developers typically adopt new programming languages? (What's the typical trajectory?)
- What does "shifted primary language in the last year" indicate?
- Research on polyglot developers vs specialists — which is more valuable in which contexts?
- How does language choice correlate with project type (web, systems, ML, etc.)?

## 6. The "Contribution Graph Gaming" Problem
Research known gaming/inflation behaviors:
- Common ways the GitHub contribution graph is gamed (fake commits, auto-commits, etc.)
- How to detect low-quality commits (single-character changes, auto-generated code)
- Research on commit spam and how to filter for it
- What signals are hardest to fake and therefore most trustworthy?

## Output Format
For each signal type, provide:
1. What it reliably indicates (backed by research or strong practitioner consensus)
2. What it does NOT indicate (common misinterpretations)
3. Recommended thresholds or distribution-based interpretations
4. How to combine it with other signals for higher reliability
5. Any known gaming/inflation risks and how to detect them

Also provide: a recommended ranking of all signals by "trustworthiness" (hardest to fake,
most predictive of actual developer quality/identity).
```

---

## Notes on Using These Prompts

- **Gemini Deep Research** can run multi-source synthesis with 20-30 sources. Paste the prompt as-is.
- **Perplexity Pro** works similarly — use "Focus: Academic" for Prompts 2 and 4.
- For Prompt 1, also ask the model to visit and quote from actual GitHub profiles directly.
- These prompts are designed to be independent — run them in any order based on priority.
- Findings should be integrated back into: `analysis_service.py` (signals), `narrative_provider.py` (templates/prompts), and the evaluation layer if built.

## Priority Order

1. **Prompt 1** (README quality) — most directly improves output quality
2. **Prompt 2** (signal analysis) — improves archetype accuracy, reduces misclassification
3. **Prompt 5** (OSS metrics) — targeted improvement for star/PR signals
4. **Prompt 3** (narrative theory) — improves honesty mode design and report narratives
5. **Prompt 4** (evaluation) — enables systematic quality measurement before scaling

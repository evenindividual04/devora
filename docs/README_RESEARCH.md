# GitHub README Research: What Makes Profiles Exceptional

> Research conducted 2026-05-28. Synthesized from two parallel agent research runs:
> one on best-practice principles and viral examples, one on narrative/copywriting techniques
> for developer profiles specifically. Applied directly to `narrative_provider.py`.

---

## The Core Problem

Most auto-generated READMEs fail the same way: they answer "what have you done?" when the
question that makes someone keep reading is "who are you, and what are you trying to do next?"

The difference between a 6/10 and a 10/10 README is not completeness or tooling — it is
whether the profile has a **specific point of view**. Most profiles are complete, accurate,
and forgettable.

---

## The Falsifiability Test

The single most useful quality filter for any sentence in a README:

> **If this sentence could be copy-pasted onto another developer's profile without changing,
> rewrite it.**

- *"Passionate full-stack developer who loves building innovative solutions."* → fails (true of anyone)
- *"Maintains the Linux kernel. Works almost exclusively in C — 234k stars on linux says more than any bio could."* → passes (only true of one person)

Every sentence should be exclusively true of THIS developer. Apply this test before any other.

---

## The Four-Beat Structure

Research consistently supports this sequence for developer profiles:

| Beat | What it answers | Example |
|------|----------------|---------|
| **Anchor** | Who they are right now, one specific sentence grounded in domain + evidence | *"Maintains the Linux kernel."* |
| **Trajectory** | What question or problem threads through their work | *"Commits arrive as large sweeping merges (~1,265 lines average), most pulling in subsystem trees."* |
| **Evidence** | Specific falsifiable things: repo names, star counts, commit patterns, PR counts | *"234k stars on linux says more than any bio could."* |
| **Signal** | What they're working toward or currently exploring | *"Recent kernel cycles focused on io_uring and memory folios."* |

Most profiles do Anchor and Evidence adequately. The ones that feel alive have a compelling
Trajectory (the *question* being chased) and a live Signal (active direction, not just history).

---

## Principles That Separate 10/10 from 6/10

### 1. Point of View Over Completeness
A README that makes editorial choices (what to leave out, what to emphasize) reads as authored.
A README that tries to list everything reads as assembled. **Omission is a craft skill.**

### 2. Show, Don't Describe
- Bad: *"I build scalable distributed systems"*
- Good: *"Designed the consensus layer for a 9-node Raft cluster — spent most of that project learning how to make failure cases visible before they cascade."*

The second version is specific, falsifiable, and shows judgment (not just capability).

### 3. Specificity at the Point of Claims
Generic: *"built high-performance systems"* (round numbers, vague scale)
Authentic: *"shaved 400ms off the critical path in a Rust gRPC service handling 10k req/s"*

The specific number doesn't need to be round. The specific tool and constraint don't need to
sound impressive. Specificity IS the credibility signal.

### 4. Direction > History
The "Currently working on" section is the most valuable section most profiles skip.
It shows active evolution, not a frozen skill set. Phrase it as a *concrete experiment*, not
an aspiration:

- Bad: *"Currently interested in machine learning and cloud technologies"*
- Good: *"Currently hacking on a toy allocator to understand jemalloc's slab strategy"*

### 5. The Living Document Signal
Top-tier profiles self-update via GitHub Actions (latest blog posts, recent releases, project
status). Static READMEs decay quietly — they signal "I haven't touched this."

### 6. Admitted Tradeoffs Signal Confidence
Beginner: lists weaknesses as "areas for growth"
Senior: *"Frontend CSS still defeats me. Working on it."* — brief, honest, moves on

The willingness to name a gap without over-explaining it is itself a confidence signal.
Brevity signals security.

---

## What Makes a Profile Feel AI-Generated vs Authentic

### AI-Generated Tells
- Round numbers and vague scale (*"thousands of users"*, *"highly scalable"*)
- Adjective-heavy, noun-sparse sentences (*"innovative, passionate, collaborative developer"*)
- The "we" of accomplishments (*"worked with a team to deliver..."*)
- Temporal vagueness (*"over the years, I have..."*)
- Triad openers (*"I love coding, learning, and solving problems"*)
- Every language listed with equal weight

### Authentic Signals
- Named tools in context (*"switched from Webpack to esbuild specifically to fix cold-start times during dev"*)
- Admitted tradeoffs (*"I chose simplicity over extensibility here — it's a decision I'd make again"*)
- Specific numbers that aren't round (*"reduced CI time from 14 minutes to 6"*)
- Personal quirks tied to technical practice
- Active learning framed as experiments, not aspirations

---

## Archetype-Specific Framing

### Hobbyist Explorer
**Identity**: curiosity and exploration *in motion*.

The failure mode is apologizing for the portfolio. The correct frame:
- Each project is evidence of curiosity, not a credential
- "Built X to understand how Y works" > "a project that implements X"
- Show the learning arc across repos — the progression IS the credential
- "Abandoned when I understood what I came to learn" is legitimate, not a gap
- Never list projects as incomplete — frame by the question that was answered

**Bad**: *"Various hobby projects in Python, JavaScript, and Rust (some incomplete)"*
**Good**: *"Each repo here started as a question I didn't know the answer to. The Python ones were mostly about understanding concurrency. The Rust ones are ongoing."*

---

### OSS Maintainer
**Identity**: stewardship and community amplification.

The distinction from just "wrote code": the non-technical aspect — contributor pipeline,
communication, building project culture. The failure mode is writing only about the code.

- Lead with community impact before technical architecture (*"1,200 contributors have merged PRs"*)
- Frame decisions made for the ecosystem (*"chose a plugin architecture so I wouldn't be the bottleneck"*)
- If sole maintainer, name it honestly — credibility beats pretending there's a team
- PR throughput and issue response time are stronger signals than feature lists

---

### Systems Builder
**Identity**: the invisible layer that everything runs on.

- Frame by what breaks when the layer is absent: *"I work on the parts that are invisible when right and catastrophic when wrong"*
- Evidence should be operational: uptime, failure modes prevented, latency budgets
- Avoid: *"Worked on distributed systems."* Use: specific system + specific constraint + specific outcome
- The depth and permanence of what's built is the identity signal

---

### Product Engineer
**Identity**: the translator between intent and experience.

- Frame around what the *user* could do, not what the code does
- *"Built the autocomplete used by 50k daily users"* > *"implemented debounced async search with keyboard navigation"*
- Show both technical depth and product judgment together

---

### Full-Stack Generalist
The hardest archetype to write for. The research finding: **identify the seam**.

The generalist's identity lives at boundaries:
- *"Most useful when product requirements and infrastructure constraints need to be reconciled in the same conversation"*
- Frame the specific seam (frontend/backend, product/platform, design/engineering)
- Language breadth is evidence — name the specific combinations and what problems required each tool

---

### Tooling Developer
- Frame around the *friction eliminated* for other developers, not the implementation
- DX impact and adoption are the primary identity signals
- API design philosophy is more interesting than feature lists
- *"I optimise for the 3am debugging experience"* > list of capabilities

---

## The Skills List Problem

Most profiles list 30-40 technologies with equal weight. The research finding on how seniors do it:

| Tier | Label | Example |
|------|-------|---------|
| Deep | Expert — production, at scale | *"Go, PostgreSQL"* |
| Comfortable | Reach for these regularly | *"Python, TypeScript"* |
| Curious | Active experiments | *"Rust, WebAssembly"* |

Three tiers, 2-3 technologies each. Self-awareness about the tiers is itself a credibility signal.

---

## Signal → Authentic Framing Map

Raw data needs to be *translated*, not just stated. Direct signal reporting sounds robotic.

| Raw Signal Pattern | Generic Output (avoid) | Authentic Framing |
|---|---|---|
| High commit frequency, few repos | "prolific contributor" | "works in depth, not breadth — tends to stay with a problem" |
| Many repos, low commit density | "diverse interests" | "explores widely — many repos are experiments built to answer a specific question" |
| High star count, one repo | "popular open source project" | frame the *problem that repo solves* and the community around it |
| Primarily one language | "expert in X" | frame the *domain* that language serves for them |
| Mixed languages | "polyglot" (avoid this word) | frame the problem that required reaching for a different tool |
| High PR count in other repos | "active contributor" | "spends as much time improving others' work as their own" |
| High fork ratio | "contributes to open source" | "contribution-oriented rather than author-first" |
| Small commits (< 60 lines avg) | "makes frequent small commits" | "incremental by habit — lands focused changesets rather than sweeping rewrites" |
| Large commits (> 800 lines avg) | "makes large changes" | "lands changes in bulk — the commit history reads as large decisions, not small steps" |
| Long commit histories on few repos | — | trajectory narrative — the arc of a project over time |
| README-heavy repos | — | signal of communication value, OSS maintainer archetype |
| High message quality | "good commit hygiene" | "the commit log reads as documentation — someone who thinks about the record they're leaving" |
| Activity tapering | — | name it briefly without over-interpreting |
| Growing trajectory | — | "output is accelerating — more happening recently than historically" |
| Consistent year-round activity | "consistent contributor" | "shows up regularly — not sprint-and-disappear" |

---

## Structural Patterns That Work

### The YAML-as-Bio Trick
Formatting the "about me" as a YAML/JSON code block simultaneously signals personality
and technical identity without stating it:

```yaml
current_focus: "distributed tracing at scale"
learning: ["Rust", "eBPF"]
not_learning: ["another JS framework"]
```

Says "I think in systems" without saying it. Creates visual variety. Comfortable and familiar
to the target audience.

### Lead with Evidence, Follow with Framing
One of the top findings from reviewing 40+ portfolios: place a *project block before the
"about me" section* — demonstrate first, describe second. Applied to narrative generation:
lead with evidence, follow with framing.

### The Genuine Hook
The best opening lines break the mold without being cringe:
- A developer who leads with the *problem* they most want to solve
- A developer who lists what they *don't* do alongside what they do
- A developer who names a specific tool or mental model as a personal touchstone

Pattern: surprising specificity beats generic positivity.

---

## Phrases to Never Use

The following phrases fail the falsifiability test or are so overused they signal the opposite
of authenticity. Beyond what's in `_BANNED_PHRASES`, watch for:

- *"Full-stack developer with X years of experience"* → LinkedIn headline
- *"Strong foundation in..."* → meaningless without specifics
- *"I have worked with [list of technologies]"* → passive, no signal of depth
- *"Results-driven"* → HR language
- *"Think outside the box"* → cliché
- *"I love coding, learning, and solving problems"* → triad opener, always generic
- *"Always excited to..."* → generic enthusiasm
- *"Polyglot"* → fine concept, overused word, just name the languages
- *"10x developer"* or any performance multiplier → red flag
- *"Ninja"*, *"Rockstar"*, *"Wizard"* → pre-2015 tech bro vocabulary

---

## What the Research Doesn't Cover (Gaps to Explore)

1. **Quantitative validation**: Do any of these principles actually correlate with profile
   engagement (clicks, follows, collaborations)? No empirical data found.

2. **Cultural context**: These principles are biased toward Western/English-language norms
   of direct, confident self-presentation. May not apply universally.

3. **Temporal decay**: How quickly does a README need updating before it becomes a liability?
   No data found.

4. **Recruiter behavior specifically**: What do technical hiring managers *actually* look for
   vs what they say they look for? Anecdotal only.

5. **The "currently working on" section effectiveness**: Assumed high value but no data.

6. **Archetype detection accuracy**: How well do GitHub signals actually predict developer
   identity? Our classifier is rule-based heuristics; no ground truth validation.

---

## Application to This Codebase

Changes made to `app/services/narrative_provider.py` based on this research:

| Research Finding | Implementation |
|---|---|
| Four-beat structure | Added to `_SYSTEM_PROMPT` and `_build_combined_prompt()` |
| Falsifiability test | Added as named rule in `_SYSTEM_PROMPT` |
| Signal → authentic framing | `_SIGNAL_FRAMING` dict; used in `_narrate_signals()` and `_build_combined_prompt()` |
| Archetype-specific framing | `framing` key added to every entry in `_ARCHETYPE_TEMPLATES` |
| Prose > bullet lists | `DeterministicNarrativeProvider` rewritten with `_build_intro_paragraph`, `_build_evidence_paragraph`, `_build_signal_paragraph` |
| Expanded banned phrases | 10 more entries in `_BANNED_PHRASES` |
| Framing hints in prompt | Auto-detected signal patterns appended to `_build_combined_prompt()` |

---

## References

- Research conducted via web search synthesis (2026-05-28)
- dev.to: "40+ portfolio reviews" thread
- GitHub profile README collections: `awesome-github-profile-readme` repositories
- FreeCodeCamp portfolio guides
- Personal branding sources for developer identity framing
- OSS maintainer research (contributor pipeline, solo vs team dynamics)

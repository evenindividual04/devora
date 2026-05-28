from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from app.models.contracts import ArchetypeResult, HonestyMode, ReadmeResult, ReadmeSection, ReportResult, Signal

logger = logging.getLogger(__name__)

_BANNED_PHRASES = [
    "passionate developer",
    "passionate about",
    "always learning",
    "tech enthusiast",
    "technology enthusiast",
    "innovative solutions",
    "innovation",
    "problem solver",
    "results-driven",
    "driven individual",
    "fast learner",
    "team player",
    "synergy",
    "leverage",
    "utilize",
    "cutting-edge",
    "state-of-the-art",
    "best practices",
    "hard worker",
    "dedicated professional",
    # Additional phrases from research on authentic developer profiles
    "strong foundation",
    "years of experience",
    "love solving",
    "challenging problems",
    "clean code",
    "always excited",
    "building the future",
    "think outside the box",
    "full-stack developer with",
    "software engineer with",
]

# ── System prompt ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You generate GitHub profile READMEs. Your goal: produce something that feels genuinely authored \
by someone who deeply understands this developer's work — not assembled from a template.

RULES (no exceptions):
1. Every claim must trace to the signals provided. Do not invent expertise or projects.
2. Never use these phrases (or close variants): {banned}
3. Apply the falsifiability test: if a sentence could be copy-pasted onto another developer's \
profile without changing, rewrite it. Every sentence must be exclusively true of THIS developer.
4. Direct, technical, human voice. No HR language. No hype.
5. Use the four-beat structure:
   - Anchor: who they are right now, one specific sentence grounded in domain and evidence
   - Trajectory: what question or problem threads through their work; what they've been figuring out
   - Evidence: specific falsifiable things — repo names, star counts, commit patterns, PR counts
   - Signal: what they're working toward or exploring now (trajectory, language shifts, active direction)
6. GitHub-flavored markdown that renders cleanly on a profile page.
7. Under 600 words total.

BAD (generic — falsifiability fails — could describe anyone):
> # Alex Johnson
> Passionate full-stack developer who loves building innovative solutions.
> Always learning new technologies. Team player with experience in React and Node.js.

GOOD (four-beat structure — grounded in evidence — could only be this person):
> # torvalds
> Maintains the Linux kernel. Works almost exclusively in C — 234k stars on linux \
says more than any bio could. [Anchor]
>
> Commits arrive as large sweeping merges (~1,265 lines average), most pulling in \
subsystem trees. The merge messages read like someone tracking a complex distributed \
collaboration over decades. [Trajectory + Evidence]
>
> Recent kernel cycles have been focused on io_uring and memory folios. [Signal]
""".format(banned=", ".join(f'"{p}"' for p in _BANNED_PHRASES[:14]))

# ── Honesty mode ─────────────────────────────────────────────────────────────

_HONESTY_INSTRUCTIONS: dict[HonestyMode, str] = {
    HonestyMode.authentic: (
        "Write from the signals as they are — no editorialising, no softening. "
        "Present actual patterns, strengths and gaps alike, in a direct factual voice."
    ),
    HonestyMode.polished: (
        "Professional, strengths-forward tone. Highlight genuine accomplishments clearly. "
        "Omit weaknesses unless they are critical context. Reads like a well-crafted professional bio."
    ),
    HonestyMode.recruiter: (
        "Optimise for a technical hiring manager reading quickly. Lead with scope and impact. "
        "Quantify wherever the data allows. Emphasise production indicators: stars, consistent "
        "activity, multi-language breadth. Skip academic or toy signals."
    ),
    HonestyMode.playful: (
        "Informal, slightly irreverent, conversational — first person where it fits. "
        "Still grounded in evidence but with personality. Reads like something the developer "
        "might actually write about themselves on a Friday afternoon."
    ),
    HonestyMode.technical: (
        "Write for a senior engineer peer. Dense with specifics: language choices, commit semantic "
        "breakdown, churn patterns, architecture signals. Skip soft framing entirely — "
        "they want the technical read."
    ),
    HonestyMode.brutally_honest: (
        "Name what the data actually shows, including weaknesses and inconsistencies. "
        "If commit quality is low, say so. If the portfolio is mostly forks or toy projects, say so. "
        "Add a 'Gaps' or 'Honest Take' section if weaknesses are evident. Unsparing but not cruel."
    ),
}

_HONESTY_STRUCTURE: dict[HonestyMode, str] = {
    HonestyMode.recruiter: (
        "Lead with the single most impressive quantified fact. Put impact numbers first. "
        "Remove any section that wouldn't help a hiring decision."
    ),
    HonestyMode.technical: (
        "Skip soft intro sections entirely. Open directly with technical specifics. "
        "A 'Stack' or 'Patterns' section replacing the usual 'About' is correct."
    ),
    HonestyMode.brutally_honest: (
        "Include a 'Gaps' or 'Honest Assessment' section naming concrete weaknesses from the data."
    ),
    HonestyMode.playful: (
        "Replace formal section headers with informal ones (e.g. 'What I actually do' over 'About')."
    ),
}

# ── Archetype templates ───────────────────────────────────────────────────────

_ARCHETYPE_TEMPLATES: dict[str, dict] = {
    "OSS Maintainer": {
        "lead": "Lead with community impact — contributor count, PR throughput, star count — before technical details.",
        "framing": (
            "The OSS maintainer identity is about stewardship, not just authorship. "
            "Frame decisions made for the ecosystem: 'chose a plugin architecture so contributors could extend without opening a PR.' "
            "If sole maintainer, name it honestly — 'solo-maintained; triages issues weekly' is more credible than pretending there's a team. "
            "Community impact is the primary credential here, not technical sophistication."
        ),
        "sections": ["About", "Projects", "Contribution Patterns", "Activity"],
        "emphasis": "project scale, maintenance discipline, community reach, contributor pipeline",
    },
    "ML Experimenter": {
        "lead": "Lead with the research question or domain being explored, not the tools.",
        "framing": (
            "Frame around the question being investigated, not the stack. "
            "'Exploring whether X approach can Y' beats 'uses PyTorch for deep learning.' "
            "The research direction and the specific problem being attacked are the identity signals. "
            "Reproducibility practices are a strong credibility signal for this archetype."
        ),
        "sections": ["Research Focus", "Projects", "Stack", "Recent Work"],
        "emphasis": "the specific question being explored, research direction, reproducibility, domain impact",
    },
    "Systems Builder": {
        "lead": "Lead with what they build and frame it by what breaks when that layer is absent.",
        "framing": (
            "Frame by operational consequence: 'I work on the layer that's invisible when right and catastrophic when wrong.' "
            "Evidence should be operational: latency numbers, failure modes prevented, scale handled, systems thinking on display. "
            "Avoid vague scope: not 'worked on distributed systems' but specific system, specific constraint, specific outcome. "
            "The depth and permanence of what they've built is the identity signal."
        ),
        "sections": ["What I Build", "Stack", "Notable Work"],
        "emphasis": "infrastructure, performance, reliability, operational depth, the cost of the layer failing",
    },
    "Product Engineer": {
        "lead": "Lead with shipped products and end-to-end ownership from idea to user.",
        "framing": (
            "Frame around what users could do, not what the code does. "
            "'Built the autocomplete used by 50k daily users' > 'implemented debounced async search with keyboard navigation.' "
            "Show both technical depth and product judgment — the ability to make tradeoffs across the stack "
            "in service of the user experience is the distinctive signal."
        ),
        "sections": ["About", "What I Ship", "Stack", "Open Source"],
        "emphasis": "shipped products, full-stack breadth, user-facing impact, product judgment",
    },
    "Tooling Developer": {
        "lead": "Lead with what developer problem the tools solve — the friction eliminated, not the implementation.",
        "framing": (
            "Frame around the friction eliminated for other developers. "
            "DX impact and adoption are the primary identity signals. "
            "API design philosophy is more interesting than feature lists: "
            "'I optimise for the 3am debugging experience' says more than a list of capabilities. "
            "Adoption evidence (stars, downloads, forks by other projects) is the strongest credential."
        ),
        "sections": ["What I Build", "Tools", "Stack"],
        "emphasis": "DX impact, API design quality, friction eliminated, adoption signals",
    },
    "Hobbyist Explorer": {
        "lead": "Lead with range and curiosity. Frame projects by the question each was built to answer, not the features it has.",
        "framing": (
            "Each project is evidence of curiosity, not a credential. "
            "Frame by the question it was built to answer: 'built X to understand how Y works' > 'a project that implements X.' "
            "Show the learning arc across repos — the progression from 'didn't know' to 'now I understand' is itself the credential. "
            "Never apologize for incomplete projects: 'abandoned when I understood what I came to learn' is legitimate. "
            "The breadth and genuine curiosity are the identity signal here, not polished output."
        ),
        "sections": ["What I Explore", "Languages & Tools", "Recent Projects"],
        "emphasis": "variety, questions being asked, learning trajectory, genuine curiosity over credential polish",
    },
    "Academic Researcher": {
        "lead": "Lead with the research area and the real-world problem it connects to.",
        "framing": (
            "Frame the research question in terms a non-specialist can understand, then ground in technical specifics. "
            "Reproducibility and methodological rigour are identity signals. "
            "Link to papers, notebooks, or datasets where available — verifiable output is the strongest credential. "
            "The problem being solved, not the tools or techniques, is the anchor."
        ),
        "sections": ["Research", "Projects", "Publications / Notebooks"],
        "emphasis": "research rigour, reproducibility, the specific problem being solved, academic or industry impact",
    },
    "Full-stack Generalist": {
        "lead": "Lead with the seam where they operate — the boundary between disciplines where their breadth is useful.",
        "framing": (
            "The generalist's identity lives at boundaries: frontend/backend, product/platform, design/engineering. "
            "Frame around the *specific seam* they inhabit: 'most useful when product requirements and infrastructure constraints "
            "need to be reconciled in the same conversation.' "
            "Language breadth is evidence here — name the specific combinations and what problems required each tool."
        ),
        "sections": ["About", "What I Build", "Stack", "Open Source"],
        "emphasis": "breadth without shallowness, the specific seam they inhabit, multi-domain judgment",
    },
}

_DEFAULT_TEMPLATE = {
    "lead": "Lead with what kind of developer they are and what they build.",
    "framing": "Frame around the specific domain and what makes this developer's work distinctive from the signals.",
    "sections": ["About", "Work", "Stack"],
    "emphasis": "technical identity, key projects, activity patterns",
}

# ── Signal → authentic framing hints ─────────────────────────────────────────
# Translates raw data patterns into authentic narrative language.
# Research finding: "infer the specific question the developer has been trying to answer,
# then frame their profile around that question."

_SIGNAL_FRAMING: dict[str, str] = {
    "high_depth_low_breadth": "works in depth, not breadth — tends to stay with a problem until it's resolved",
    "high_breadth_low_density": "explores widely — many repos read as experiments built to answer a specific question",
    "high_fork_ratio": "spends as much time improving others' work as their own",
    "sole_author_oss": "solo-maintained — the discipline of keeping a project alive alone is itself the signal",
    "small_commits": "incremental by habit — lands focused changesets rather than sweeping rewrites",
    "large_commits": "lands changes in bulk — the commit history reads as large decisions rather than small steps",
    "high_message_quality": "the commit log reads as documentation — someone who thinks about the record they're leaving",
    "language_shift": "mid-stream pivot toward a new tool — worth tracking",
    "growing_trajectory": "output is accelerating — more happening recently than historically",
    "declining_trajectory": "activity has pulled back — worth noting without over-interpreting",
    "consistent_cadence": "shows up regularly — not sprint-and-disappear",
}


# ── Signal narration ──────────────────────────────────────────────────────────

def _fv(sm: dict, name: str, default: float = 0.0) -> float:
    s = sm.get(name)
    return float(s.value) if s and isinstance(s.value, (int, float)) else default


def _sv(sm: dict, name: str) -> str | None:
    s = sm.get(name)
    return str(s.value) if s else None


def _narrate_signals(signals: list[Signal]) -> list[str]:
    """Convert raw signals into readable narrative sentences for the LLM."""
    sm = {s.name: s for s in signals}
    sentences: list[str] = []

    # Commit mix
    feat = _fv(sm, "feature_ratio")
    fix = _fv(sm, "fix_ratio")
    ref = _fv(sm, "refactor_ratio")
    if feat + fix + ref > 0:
        dominant = max([("feature work", feat), ("bug-fixing", fix), ("refactoring", ref)], key=lambda x: x[1])
        sentences.append(
            f"Commit breakdown skews toward {dominant[0]} ({dominant[1]:.0%} of sampled commits); "
            f"fix {fix:.0%}, refactor {ref:.0%}."
        )

    churn = _fv(sm, "avg_churn_per_commit")
    if churn > 800:
        sentences.append(
            f"Commits are large (~{churn:,.0f} lines average) — "
            f"{_SIGNAL_FRAMING['large_commits']}."
        )
    elif churn > 100:
        sentences.append(f"Moderate commit size (~{churn:,.0f} lines) — balanced between focused and broad changes.")
    elif churn > 0:
        sentences.append(
            f"Small, surgical commits (~{churn:.0f} lines average) — "
            f"{_SIGNAL_FRAMING['small_commits']}."
        )

    quality = _fv(sm, "commit_message_quality")
    if quality > 0.8:
        sentences.append(f"Commit messages are descriptive — {_SIGNAL_FRAMING['high_message_quality']}.")
    elif 0 < quality < 0.4:
        sentences.append("Commit messages tend to be terse or low-signal.")

    cpw = _fv(sm, "commits_per_week")
    if cpw > 10:
        sentences.append(f"Very high-frequency contributor — {cpw:.1f} commits/week on average.")
    elif cpw > 3:
        sentences.append(f"Active pace — {cpw:.1f} commits/week.")
    elif cpw > 0:
        sentences.append(f"Measured cadence — {cpw:.2f} commits/week.")

    # Stars / impact
    max_stars = _fv(sm, "max_stars")
    avg_stars = _fv(sm, "avg_stars")
    if max_stars > 50000:
        sentences.append(f"Top project has {max_stars:,.0f} stars — demonstrable community impact at scale.")
    elif max_stars > 5000:
        sentences.append(f"Top project at {max_stars:,.0f} stars — meaningful community traction.")
    elif max_stars > 500:
        sentences.append(f"Projects attract attention — top repo at {max_stars:,.0f} stars.")
    if avg_stars > 500 and max_stars > 0:
        sentences.append(f"Average {avg_stars:,.0f} stars across repos — consistently visible work.")

    # Language
    lang = _sv(sm, "primary_language")
    diversity = _fv(sm, "language_diversity")
    recent_lang = _sv(sm, "recent_primary_language")
    shifted = _fv(sm, "language_shifted")

    if lang:
        if diversity > 4:
            sentences.append(f"Primary language is {lang} but portfolio spans {int(diversity)} languages — polyglot by practice.")
        elif diversity > 2:
            sentences.append(f"Works mainly in {lang} across {int(diversity)} languages.")
        else:
            sentences.append(f"Deeply focused on {lang} — portfolio is highly concentrated.")

    if shifted > 0 and recent_lang and lang and recent_lang != lang:
        sentences.append(
            f"Noticeably shifting toward {recent_lang} in recent work (away from historical {lang}) — "
            f"{_SIGNAL_FRAMING['language_shift']}."
        )

    # Repo character
    fork_ratio = _fv(sm, "fork_ratio")
    repo_count = _fv(sm, "repo_count")
    pr_count = _fv(sm, "pr_authored_count")

    if fork_ratio > 0.6:
        sentences.append(
            f"Portfolio is largely forks ({fork_ratio:.0%}) — "
            f"{_SIGNAL_FRAMING['high_fork_ratio']}."
        )
    elif fork_ratio < 0.15 and repo_count > 3:
        sentences.append(f"Mostly original work — low fork ratio ({fork_ratio:.0%}).")

    if pr_count > 200:
        sentences.append(f"Prolific OSS contributor — {int(pr_count):,} PRs authored across GitHub.")
    elif pr_count > 20:
        sentences.append(f"Active contributor — {int(pr_count)} PRs authored.")

    # Temporal
    months = _fv(sm, "months_active_last_year")
    trajectory = _sv(sm, "activity_trajectory")

    if months >= 10:
        sentences.append(f"Consistent year-round contributor — active {int(months)}/12 months last year.")
    elif months >= 8:
        sentences.append(f"Active most of the year ({int(months)}/12 months).")
    elif months >= 5:
        sentences.append(f"Active roughly half the year ({int(months)} months).")
    elif months > 0:
        sentences.append(f"Sporadic activity — {int(months)} months active in the last year.")

    if trajectory == "growing":
        sentences.append(f"Activity is accelerating — {_SIGNAL_FRAMING['growing_trajectory']}.")
    elif trajectory == "declining":
        sentences.append(f"Activity has tapered off in recent months — {_SIGNAL_FRAMING['declining_trajectory']}.")
    elif trajectory == "stable":
        sentences.append(_SIGNAL_FRAMING["consistent_cadence"].capitalize() + ".")

    return sentences


# ── Combined prompt ───────────────────────────────────────────────────────────

def _build_combined_prompt(prompt: NarrativePrompt) -> str:
    sm = {s.name: s for s in prompt.signals}
    narrative = _narrate_signals(prompt.signals)
    template = _ARCHETYPE_TEMPLATES.get(prompt.archetype.top_archetype, _DEFAULT_TEMPLATE)
    honesty_instr = _HONESTY_INSTRUCTIONS.get(prompt.honesty_mode, _HONESTY_INSTRUCTIONS[HonestyMode.authentic])
    honesty_struct = _HONESTY_STRUCTURE.get(prompt.honesty_mode, "")

    commit_excerpts = [
        ref.excerpt for ref in prompt.archetype.supporting_evidence
        if ref.source_type == "commit" and ref.excerpt
    ][:4]
    top_repos = prompt.standout_repos[:5] or [
        ref.source_id for ref in prompt.archetype.supporting_evidence
        if ref.source_type == "repo"
    ][:5]

    commit_block = (
        "\n".join(f'  "{e}"' for e in commit_excerpts)
        if commit_excerpts else "  (no commit excerpts available)"
    )

    # Detect applicable signal framing hints
    fork_ratio = _fv(sm, "fork_ratio")
    churn = _fv(sm, "avg_churn_per_commit")
    repo_count = _fv(sm, "repo_count")
    cpw = _fv(sm, "commits_per_week")
    months = _fv(sm, "months_active_last_year")

    framing_hints: list[str] = []
    if repo_count > 10 and cpw < 2:
        framing_hints.append(_SIGNAL_FRAMING["high_breadth_low_density"])
    if fork_ratio > 0.6:
        framing_hints.append(_SIGNAL_FRAMING["high_fork_ratio"])
    if 0 < churn < 60 and cpw > 0:
        framing_hints.append(_SIGNAL_FRAMING["small_commits"])
    if months >= 10:
        framing_hints.append(_SIGNAL_FRAMING["consistent_cadence"])

    framing_block = (
        "\nNARRATIVE FRAMING HINTS (translate these signals into authentic voice — avoid restating them literally):\n"
        + "\n".join(f"- {h}" for h in framing_hints)
    ) if framing_hints else ""

    return f"""Generate a GitHub profile README and analysis report for @{prompt.username}.

ARCHETYPE: {prompt.archetype.top_archetype} (confidence: {prompt.archetype.confidence:.0%})
Secondary archetypes: {', '.join(prompt.archetype.alternates) or 'none'}

ARCHETYPE FRAMING (how to approach this particular developer identity):
{template['framing']}

FOUR-BEAT STRUCTURE — use this sequence:
1. Anchor — one specific sentence: who they are right now, grounded in domain + evidence
2. Trajectory — the thread through their work: what question or problem they've been figuring out
3. Evidence — specific falsifiable things: repo names, star counts, commit patterns, PR counts
4. Signal — what they're working toward or currently exploring: trajectory, language shifts, active direction

Falsifiability test: every sentence must be exclusively true of THIS developer.
If a sentence could be pasted onto another profile unchanged, rewrite it.

SIGNAL NARRATIVE (interpret these as facts about the developer):
{chr(10).join(f'- {s}' for s in narrative)}
{framing_block}

TOP REPOSITORIES: {top_repos}

COMMIT VOICE — actual messages from their work (let this inform tone and specificity):
{commit_block}

TONE: {honesty_instr}
{f'STRUCTURE: {honesty_struct}' if honesty_struct else ''}

README GUIDANCE: {template['lead']}
Suggested sections: {', '.join(template['sections'])}
Emphasise: {template['emphasis']}

Return ONLY valid JSON with no markdown fences:
{{
  "readme_markdown": "<full README markdown, under 600 words, starts with # {prompt.username}>",
  "summary": "<2-sentence grounded summary of this developer's engineering identity>",
  "standout_repos": ["<repo1>", "<repo2>", "<repo3>"],
  "timeline": [
    "<observation about their work pattern>",
    "<observation about recent trajectory>"
  ]
}}"""


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class NarrativePrompt:
    username: str
    honesty_mode: HonestyMode
    signals: list[Signal]
    archetype: ArchetypeResult
    standout_repos: list[str] = field(default_factory=list)


def anti_generic_guard(text: str) -> str:
    cleaned = text
    for phrase in _BANNED_PHRASES:
        cleaned = cleaned.replace(phrase, "")
    return cleaned


# ── Provider base ─────────────────────────────────────────────────────────────

class NarrativeProvider:
    def build_both(self, prompt: NarrativePrompt) -> tuple[ReadmeResult, ReportResult]:
        raise NotImplementedError

    # Convenience shims kept for backward-compat with tests
    def build_readme(self, prompt: NarrativePrompt) -> ReadmeResult:
        return self.build_both(prompt)[0]

    def build_report(self, prompt: NarrativePrompt) -> ReportResult:
        return self.build_both(prompt)[1]


# ── Gemini provider ───────────────────────────────────────────────────────────

class GeminiNarrativeProvider(NarrativeProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash-lite") -> None:
        from google import genai  # type: ignore[import-untyped]
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._fallback = DeterministicNarrativeProvider()

    def _generate(self, user: str) -> str:
        from google.genai import types  # type: ignore[import-untyped]
        response = self._client.models.generate_content(
            model=self._model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                temperature=0.7,
                max_output_tokens=1500,
            ),
        )
        return response.text or ""

    def build_both(self, prompt: NarrativePrompt) -> tuple[ReadmeResult, ReportResult]:
        top_repos = prompt.standout_repos[:3] or [
            ref.source_id for ref in prompt.archetype.supporting_evidence
            if ref.source_type == "repo"
        ][:3]
        try:
            raw = self._generate(_build_combined_prompt(prompt))
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            data = json.loads(raw)

            markdown = anti_generic_guard(data.get("readme_markdown", ""))
            readme = ReadmeResult(
                markdown=markdown,
                sections=[ReadmeSection(
                    title="Generated Profile",
                    content=markdown,
                    evidence_refs=prompt.archetype.supporting_evidence,
                )],
            )
            report = ReportResult(
                summary=anti_generic_guard(data.get("summary", "")),
                archetype=prompt.archetype,
                standout_repos=data.get("standout_repos", top_repos),
                timeline=data.get("timeline", []),
            )
            return readme, report
        except Exception:
            logger.exception("Gemini generation failed, falling back to deterministic")
            return self._fallback.build_both(prompt)


# ── OpenAI-compatible provider (Groq, Cerebras, OpenRouter, …) ───────────────

class OpenAICompatibleNarrativeProvider(NarrativeProvider):
    """Narrative provider for any OpenAI-format API (Groq, Cerebras, etc.)."""

    def __init__(self, base_url: str, api_key: str, model: str, provider_name: str = "openai_compatible") -> None:
        import httpx
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._provider_name = provider_name
        self._http = httpx.Client(timeout=30.0)
        self._fallback = DeterministicNarrativeProvider()

    def _generate(self, user_prompt: str) -> str:
        resp = self._http.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 1500,
                "temperature": 0.7,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"] or ""

    def build_both(self, prompt: NarrativePrompt) -> tuple[ReadmeResult, ReportResult]:
        top_repos = prompt.standout_repos[:3] or [
            ref.source_id for ref in prompt.archetype.supporting_evidence
            if ref.source_type == "repo"
        ][:3]
        try:
            raw = self._generate(_build_combined_prompt(prompt)).strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            data = json.loads(raw)
            markdown = anti_generic_guard(data.get("readme_markdown", ""))
            readme = ReadmeResult(
                markdown=markdown,
                sections=[ReadmeSection(
                    title="Generated Profile",
                    content=markdown,
                    evidence_refs=prompt.archetype.supporting_evidence,
                )],
            )
            report = ReportResult(
                summary=anti_generic_guard(data.get("summary", "")),
                archetype=prompt.archetype,
                standout_repos=data.get("standout_repos", top_repos),
                timeline=data.get("timeline", []),
            )
            return readme, report
        except Exception:
            logger.exception("%s generation failed, falling back to deterministic", self._provider_name)
            return self._fallback.build_both(prompt)


# ── Deterministic provider ────────────────────────────────────────────────────

class DeterministicNarrativeProvider(NarrativeProvider):
    """Fallback provider that generates narrative prose without an LLM.

    Uses the four-beat structure (Anchor → Trajectory → Evidence → Signal) and
    produces flowing paragraphs rather than bullet lists — closer to what a good
    human-authored README looks like.
    """

    def build_both(self, prompt: NarrativePrompt) -> tuple[ReadmeResult, ReportResult]:
        sm = {s.name: s for s in prompt.signals}
        archetype = prompt.archetype.top_archetype
        alternates = prompt.archetype.alternates[:2]

        lines: list[str] = [f"# {prompt.username}", ""]

        archetype_line = f"**{archetype}**"
        if alternates:
            archetype_line += f" · *also: {', '.join(alternates)}*"
        lines += [archetype_line, ""]

        # Beat 1 + 2: Anchor + Trajectory in a single intro paragraph
        intro = _build_intro_paragraph(archetype, sm)
        lines += [intro, ""]

        # Beat 3: Evidence — commit patterns, repo character, contribution counts
        evidence = _build_evidence_paragraph(sm, prompt.standout_repos)
        if evidence:
            lines += [evidence, ""]

        # Beat 4: Signal — temporal patterns and trajectory
        signal = _build_signal_paragraph(sm)
        if signal:
            lines += [signal, ""]

        markdown = anti_generic_guard("\n".join(lines).rstrip())
        readme = ReadmeResult(
            markdown=markdown,
            sections=[ReadmeSection(
                title="Profile",
                content=markdown,
                evidence_refs=prompt.archetype.supporting_evidence,
            )],
        )

        lang = sm.get("primary_language")
        stars = sm.get("max_stars")
        trajectory = sm.get("activity_trajectory")
        cpw = sm.get("commits_per_week")
        months = sm.get("months_active_last_year")
        feat = sm.get("feature_ratio")

        lang_str = str(lang.value) if lang else "various languages"
        cpw_str = f"{float(cpw.value):.2f} commits/week" if cpw and isinstance(cpw.value, (int, float)) else "intermittent"
        stars_str = (
            f", with a project reaching {int(stars.value):,} stars"
            if stars and isinstance(stars.value, (int, float)) and int(stars.value) > 100 else ""
        )
        traj_str = f" Trajectory: {trajectory.value}." if trajectory else ""

        timeline = []
        if months and isinstance(months.value, (int, float)):
            timeline.append(f"Active {int(months.value)} of the last 12 months.")
        if feat and isinstance(feat.value, (int, float)):
            timeline.append(f"Commit mix: {float(feat.value):.0%} features, consistent with {archetype} pattern.")

        report = ReportResult(
            summary=anti_generic_guard(
                f"@{prompt.username} is a {archetype.lower()} working primarily in {lang_str}{stars_str}. "
                f"Activity runs at {cpw_str} (sampled).{traj_str}"
            ),
            archetype=prompt.archetype,
            standout_repos=prompt.standout_repos[:3],
            timeline=timeline,
        )
        return readme, report


# ── Deterministic prose builders ─────────────────────────────────────────────

def _build_intro_paragraph(archetype: str, sm: dict) -> str:
    """Anchor + Trajectory beats: identity and what threads through their work."""
    lang = sm.get("primary_language")
    lang_val = str(lang.value) if lang else "varied languages"
    stars = sm.get("max_stars")
    star_val = int(stars.value) if stars and isinstance(stars.value, (int, float)) else 0
    trajectory = sm.get("activity_trajectory")
    traj_val = str(trajectory.value) if trajectory else "stable"
    dominant_type = sm.get("dominant_repo_type")
    dominant_type_val = str(dominant_type.value) if dominant_type else ""
    diversity = sm.get("language_diversity")
    div_val = int(diversity.value) if diversity and isinstance(diversity.value, (int, float)) else 1

    star_phrase = ""
    if star_val > 10000:
        star_phrase = f" Work reaching {star_val:,} stars."
    elif star_val > 1000:
        star_phrase = f" One project at {star_val:,} stars."

    traj_phrase = {
        "growing": "Activity is picking up.",
        "declining": "Output has tapered off recently.",
        "stable": "Showing up consistently.",
        "new": "Just getting started.",
        "inconsistent": "Working in bursts.",
    }.get(traj_val, "")

    if div_val > 4:
        lang_phrase = f"{lang_val} is home base, though the portfolio spans {div_val} languages"
    elif div_val > 2:
        lang_phrase = f"Works primarily in {lang_val}, with {div_val} languages in the mix"
    else:
        lang_phrase = f"Works in {lang_val}"

    if dominant_type_val == "toy" and star_val == 0:
        character = "Most repos are explorations — each one an answer to a specific question."
    elif dominant_type_val == "coursework":
        character = "Portfolio centers on academic and coursework projects."
    elif archetype == "OSS Maintainer":
        character = "Maintains projects others depend on."
    elif archetype == "Systems Builder":
        character = "Builds the invisible layer."
    elif archetype == "Hobbyist Explorer":
        character = "Explores widely across many tools and domains."
    else:
        character = f"{archetype} by pattern."

    parts = [f"{lang_phrase}.{star_phrase}", character]
    if traj_phrase:
        parts.append(traj_phrase)

    return " ".join(p for p in parts if p)


def _build_evidence_paragraph(sm: dict, standout_repos: list[str]) -> str:
    """Evidence beat: commit patterns, repo character, contribution counts in prose."""
    parts: list[str] = []

    feat = sm.get("feature_ratio")
    fix = sm.get("fix_ratio")
    ref = sm.get("refactor_ratio")
    churn = sm.get("avg_churn_per_commit")
    quality = sm.get("commit_message_quality")
    fork_ratio = sm.get("fork_ratio")
    repo_count = sm.get("repo_count")
    pr_count = sm.get("pr_authored_count")
    diversity = sm.get("language_diversity")

    if feat and isinstance(feat.value, (int, float)):
        f_val = float(feat.value)
        fi_val = float(fix.value) if fix and isinstance(fix.value, (int, float)) else 0
        r_val = float(ref.value) if ref and isinstance(ref.value, (int, float)) else 0
        dominant_label, dominant_pct = max(
            [("feature work", f_val), ("bug fixes", fi_val), ("refactoring", r_val)],
            key=lambda x: x[1],
        )
        commit_str = f"Commits skew toward {dominant_label} ({dominant_pct:.0%})"
        if churn and isinstance(churn.value, (int, float)):
            c = float(churn.value)
            if c > 500:
                commit_str += f", landing in large batches (~{c:,.0f} lines each)"
            elif c < 60:
                commit_str += f", small and surgical (~{c:.0f} lines each)"
        commit_str += "."
        if quality and isinstance(quality.value, (int, float)) and float(quality.value) > 0.8:
            commit_str += " Messages are descriptive."
        parts.append(commit_str)

    repo_parts: list[str] = []
    if repo_count and isinstance(repo_count.value, (int, float)):
        repo_parts.append(f"{int(repo_count.value)} public repos")
    if diversity and isinstance(diversity.value, (int, float)) and int(diversity.value) > 2:
        repo_parts.append(f"{int(diversity.value)} languages")
    if fork_ratio and isinstance(fork_ratio.value, (int, float)):
        fr = float(fork_ratio.value)
        if fr < 0.15:
            repo_parts.append("mostly original work")
        elif fr > 0.6:
            repo_parts.append(f"largely forks ({fr:.0%})")

    if repo_parts:
        parts.append(", ".join(repo_parts).capitalize() + ".")

    if pr_count and isinstance(pr_count.value, (int, float)) and int(pr_count.value) > 5:
        pr_val = int(pr_count.value)
        if pr_val > 100:
            parts.append(f"{pr_val:,} PRs authored across GitHub.")
        else:
            parts.append(f"{pr_val} PRs authored.")

    if standout_repos:
        parts.append("Standout: " + " · ".join(f"`{r}`" for r in standout_repos[:4]))

    return " ".join(parts)


def _build_signal_paragraph(sm: dict) -> str:
    """Signal beat: temporal patterns, cadence, and current trajectory in prose."""
    parts: list[str] = []

    months = sm.get("months_active_last_year")
    streak = sm.get("streak_months")
    shifted = sm.get("language_shifted")
    recent_lang = sm.get("recent_primary_language")
    primary_lang = sm.get("primary_language")
    cpw = sm.get("commits_per_week")

    if months and isinstance(months.value, (int, float)):
        m = int(months.value)
        if m >= 10:
            parts.append(f"Active {m}/12 months last year — year-round cadence.")
        elif m >= 8:
            parts.append(f"Active most of the year ({m}/12 months).")
        elif m >= 5:
            parts.append(f"Active roughly half the year ({m} months).")
        elif m > 0:
            parts.append(f"Sporadic — {m} months active in the last year.")

    if cpw and isinstance(cpw.value, (int, float)):
        parts.append(f"~{float(cpw.value):.2f} commits/week (sampled).")

    if streak and isinstance(streak.value, (int, float)) and int(streak.value) >= 3:
        parts.append(f"{int(streak.value)}-month active streak in recent history.")

    if (shifted and isinstance(shifted.value, (int, float)) and shifted.value > 0
            and recent_lang and primary_lang
            and str(recent_lang.value) != str(primary_lang.value)):
        parts.append(f"Recent shift toward **{recent_lang.value}** (from {primary_lang.value}).")

    return " ".join(parts)

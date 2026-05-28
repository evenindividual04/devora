from __future__ import annotations

import json
import logging
import re
import time
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

# JSON schema for structured output (used by Gemini response_schema)
_NARRATIVE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "readme_markdown": {"type": "string"},
        "summary": {"type": "string"},
        "standout_repos": {"type": "array", "items": {"type": "string"}},
        "timeline": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["readme_markdown", "summary", "standout_repos", "timeline"],
}

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
6. GitHub-flavored markdown that renders cleanly on a profile page. Use ## headers for sections.
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


_README_MIN_LEN = 50


def _extract_json(raw: str) -> dict:
    """Extract a JSON object from LLM output, handling fences and surrounding prose."""
    s = raw.strip()
    if s.startswith("```"):
        newline = s.find("\n")
        s = s[newline + 1:] if newline != -1 else s[3:]
        if "```" in s:
            s = s.rsplit("```", 1)[0]
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in LLM output: {raw[:120]!r}")
    try:
        return json.loads(s[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON parse error: {exc}") from exc


def _generate_with_retry(generate_fn, prompt: str, max_attempts: int = 2) -> str:
    """Call generate_fn up to max_attempts times, sleeping 0.5s between attempts."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return generate_fn(prompt)
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(0.5)
    raise last_exc  # type: ignore[misc]


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

    # Use detailed repo cards if available, else fall back to names
    if prompt.repo_details:
        top_repos_block = "\n".join(
            f"  - {r.name}"
            + (f": {r.description}" if r.description else "")
            + (f" [{r.language}]" if r.language else "")
            + (f" ⭐{r.stars:,}" if r.stars > 0 else "")
            for r in prompt.repo_details[:5]
        )
    else:
        top_repos = prompt.standout_repos[:5] or [
            ref.source_id for ref in prompt.archetype.supporting_evidence
            if ref.source_type == "repo"
        ][:5]
        top_repos_block = "\n".join(f"  - {r}" for r in top_repos)

    commit_block = (
        "\n".join(f'  "{e}"' for e in commit_excerpts)
        if commit_excerpts else "  (no commit excerpts available)"
    )

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

    limited_note = (
        "\nNOTE: Limited data (few repos/commits) — acknowledge uncertainty rather than overstating confidence.\n"
    ) if prompt.archetype.limited_data else ""

    return f"""Generate a GitHub profile README and analysis report for @{prompt.username}.

ARCHETYPE: {prompt.archetype.top_archetype} (confidence: {prompt.archetype.confidence:.0%})
{f"Secondary archetypes: {', '.join(prompt.archetype.alternates)}" if prompt.archetype.alternates else "No close secondary archetypes — commit to this identity."}
{limited_note}
ARCHETYPE FRAMING (how to approach this particular developer identity):
{template['framing']}

FOUR-BEAT STRUCTURE — use this sequence with ## headers:
1. Anchor — one specific sentence: who they are right now, grounded in domain + evidence
2. Trajectory — the thread through their work: what question or problem they've been figuring out
3. Evidence — specific falsifiable things: repo names, star counts, commit patterns, PR counts
4. Signal — what they're working toward or currently exploring

Falsifiability test: every sentence must be exclusively true of THIS developer.

SIGNAL NARRATIVE (interpret these as facts about the developer):
{chr(10).join(f'- {s}' for s in narrative)}
{framing_block}

TOP REPOSITORIES (use these names and descriptions in the README):
{top_repos_block}

COMMIT VOICE — actual messages from their work (let this inform tone and specificity):
{commit_block}

TONE: {honesty_instr}
{f'STRUCTURE: {honesty_struct}' if honesty_struct else ''}

README GUIDANCE: {template['lead']}
Suggested sections: {', '.join(template['sections'])}
Emphasise: {template['emphasis']}

Return a JSON object with these exact fields:
- readme_markdown: full README markdown, under 600 words, starts with # {prompt.username}, uses ## for sections
- summary: 2-sentence grounded summary of this developer's engineering identity
- standout_repos: list of 3 repo names from the top repositories above
- timeline: list of 2 observations about their work pattern and recent trajectory"""


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class RepoCard:
    name: str
    description: str
    language: str
    stars: int


@dataclass
class NarrativePrompt:
    username: str
    honesty_mode: HonestyMode
    signals: list[Signal]
    archetype: ArchetypeResult
    standout_repos: list[str] = field(default_factory=list)
    repo_details: list[RepoCard] = field(default_factory=list)


def anti_generic_guard(text: str) -> str:
    cleaned = text
    for phrase in _BANNED_PHRASES:
        cleaned = cleaned.replace(phrase, "")
    cleaned = re.sub(r" {2,}", " ", cleaned)
    cleaned = re.sub(r" +([.,;:!?])", r"\1", cleaned)
    return cleaned


# ── Provider base ─────────────────────────────────────────────────────────────

class NarrativeProvider:
    def build_both(self, prompt: NarrativePrompt) -> tuple[ReadmeResult, ReportResult]:
        raise NotImplementedError

    def build_readme(self, prompt: NarrativePrompt) -> ReadmeResult:
        return self.build_both(prompt)[0]

    def build_report(self, prompt: NarrativePrompt) -> ReportResult:
        return self.build_both(prompt)[1]


# ── Gemini provider ───────────────────────────────────────────────────────────

class GeminiNarrativeProvider(NarrativeProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
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
                max_output_tokens=2000,
                response_mime_type="application/json",
                response_schema=_NARRATIVE_JSON_SCHEMA,
            ),
        )
        return response.text or ""

    def build_both(self, prompt: NarrativePrompt) -> tuple[ReadmeResult, ReportResult]:
        top_repos = [r.name for r in prompt.repo_details[:3]] or prompt.standout_repos[:3] or [
            ref.source_id for ref in prompt.archetype.supporting_evidence
            if ref.source_type == "repo"
        ][:3]
        try:
            raw = _generate_with_retry(self._generate, _build_combined_prompt(prompt))
            data = _extract_json(raw)
            markdown = anti_generic_guard(data.get("readme_markdown", ""))
            if not markdown.strip() or len(markdown.strip()) < _README_MIN_LEN:
                logger.warning("Gemini readme too short/empty (len=%d), falling back", len(markdown.strip()))
                return self._fallback.build_both(prompt)
            readme = ReadmeResult(
                markdown=markdown,
                sections=[ReadmeSection(
                    title="Generated Profile",
                    content=markdown,
                    evidence_refs=prompt.archetype.supporting_evidence,
                )],
                generator=self._model,
            )
            report = ReportResult(
                summary=anti_generic_guard(data.get("summary", "")),
                archetype=prompt.archetype,
                standout_repos=data.get("standout_repos", top_repos),
                timeline=data.get("timeline", []),
            )
            return readme, report
        except Exception as exc:
            logger.warning("Gemini generation failed (%s), falling back to deterministic", exc)
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
                "max_tokens": 2000,
                "temperature": 0.7,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"] or ""

    def build_both(self, prompt: NarrativePrompt) -> tuple[ReadmeResult, ReportResult]:
        top_repos = [r.name for r in prompt.repo_details[:3]] or prompt.standout_repos[:3] or [
            ref.source_id for ref in prompt.archetype.supporting_evidence
            if ref.source_type == "repo"
        ][:3]
        try:
            raw = _generate_with_retry(self._generate, _build_combined_prompt(prompt))
            data = _extract_json(raw)
            markdown = anti_generic_guard(data.get("readme_markdown", ""))
            if not markdown.strip() or len(markdown.strip()) < _README_MIN_LEN:
                logger.warning("%s readme too short/empty, falling back to deterministic", self._provider_name)
                return self._fallback.build_both(prompt)
            readme = ReadmeResult(
                markdown=markdown,
                sections=[ReadmeSection(
                    title="Generated Profile",
                    content=markdown,
                    evidence_refs=prompt.archetype.supporting_evidence,
                )],
                generator=f"{self._provider_name}/{self._model}",
            )
            report = ReportResult(
                summary=anti_generic_guard(data.get("summary", "")),
                archetype=prompt.archetype,
                standout_repos=data.get("standout_repos", top_repos),
                timeline=data.get("timeline", []),
            )
            return readme, report
        except Exception as exc:
            logger.warning("%s generation failed (%s), falling back to deterministic", self._provider_name, exc)
            return self._fallback.build_both(prompt)


# ── Deterministic provider ────────────────────────────────────────────────────

class DeterministicNarrativeProvider(NarrativeProvider):
    """Fallback provider: multi-section, evidence-led README without an LLM.

    Leads with the single most impressive quantified fact, then uses archetype-
    specific sections with repo cards (name + description), stack, and recent direction.
    """

    def build_both(self, prompt: NarrativePrompt) -> tuple[ReadmeResult, ReportResult]:
        sm = {s.name: s for s in prompt.signals}
        archetype = prompt.archetype.top_archetype
        template = _ARCHETYPE_TEMPLATES.get(archetype, _DEFAULT_TEMPLATE)

        lines: list[str] = [f"# {prompt.username}", ""]

        # Opening: lead with the most impressive quantified fact
        opening = _build_opening(archetype, sm, prompt.repo_details)
        lines += [opening, ""]

        # Standout work section with repo cards
        work_section = _build_work_section(prompt.repo_details, template)
        if work_section:
            section_header = template["sections"][1] if len(template["sections"]) > 1 else "Work"
            lines += [f"## {section_header}", ""]
            lines += work_section
            lines += [""]

        # Stack section
        stack = _build_stack_line(sm)
        if stack:
            lines += ["## Stack", "", stack, ""]

        # Recent direction / signal beat
        direction = _build_recent_direction(sm)
        if direction:
            lines += ["## Recently", "", direction, ""]

        # Evidence beat: commit patterns in prose
        evidence = _build_evidence_prose(sm)
        if evidence:
            lines += [evidence, ""]

        # Sampling disclaimer — once, honest, not repeated
        repo_count = int(_fv(sm, "repo_count"))
        if repo_count > 0:
            lines.append(f"*Based on {repo_count} public repos and sampled commits.*")

        markdown = anti_generic_guard("\n".join(lines).rstrip())
        readme = ReadmeResult(
            markdown=markdown,
            sections=[ReadmeSection(
                title="Profile",
                content=markdown,
                evidence_refs=prompt.archetype.supporting_evidence,
            )],
            generator="deterministic",
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
            standout_repos=[r.name for r in prompt.repo_details[:3]] or prompt.standout_repos[:3],
            timeline=timeline,
        )
        return readme, report


# ── Deterministic prose builders ─────────────────────────────────────────────

def _build_opening(archetype: str, sm: dict, repo_details: list[RepoCard]) -> str:
    """Lead with the single most impressive quantified fact, then anchor + trajectory."""
    lang = _sv(sm, "primary_language") or "various languages"
    star_val = int(_fv(sm, "max_stars"))
    repo_count = int(_fv(sm, "repo_count"))
    pr_count = int(_fv(sm, "pr_authored_count"))
    diversity = int(_fv(sm, "language_diversity"))
    trajectory = _sv(sm, "activity_trajectory") or "stable"
    dominant_type = _sv(sm, "dominant_repo_type") or "personal"

    # Find top starred repo name
    top_repo_name = repo_details[0].name if repo_details else ""

    # Pick the most impressive quantified fact to lead with
    if star_val > 50000 and top_repo_name:
        lead = f"{top_repo_name} has {star_val:,} stars."
    elif star_val > 1000 and top_repo_name:
        lead = f"Top project `{top_repo_name}` at {star_val:,} stars."
    elif pr_count > 200:
        lead = f"{pr_count:,} PRs authored across GitHub."
    elif repo_count > 20:
        lead = f"{repo_count} public repos"
        if diversity > 3:
            lead += f" across {diversity} languages"
        lead += "."
    else:
        lead = ""

    # Anchor: language + archetype character
    traj_phrase = {
        "growing": "Activity is picking up.",
        "declining": "Output has tapered off recently.",
        "stable": "Showing up consistently.",
        "new": "Just getting started.",
        "burst": "Active in bursts.",
        "inactive": "",
    }.get(trajectory, "")

    if dominant_type in ("personal",) and star_val == 0:
        character = f"Works in {lang} — portfolio reads as experiments built to answer specific questions."
    elif dominant_type == "coursework":
        character = f"Works in {lang}. Portfolio centers on academic and coursework projects."
    elif archetype == "OSS Maintainer":
        character = f"Works in {lang}. Maintains projects others depend on."
    elif archetype == "Systems Builder":
        character = f"Works in {lang}. Builds the invisible layer."
    elif archetype == "Hobbyist Explorer":
        if diversity > 3:
            character = f"Explores across {diversity} languages — {lang} is home base."
        else:
            character = f"Works in {lang} — explores widely across many tools and domains."
    elif archetype == "Academic Researcher":
        character = f"Works in {lang}. Research-focused portfolio."
    elif archetype == "Tooling Developer":
        character = f"Works in {lang}. Builds tools that reduce friction for other developers."
    else:
        character = f"Works in {lang}."

    parts = [p for p in [lead, character, traj_phrase] if p]
    return " ".join(parts)


def _build_work_section(repo_details: list[RepoCard], template: dict) -> list[str]:
    """Render repo cards with descriptions for the standout work section."""
    if not repo_details:
        return []
    lines: list[str] = []
    for repo in repo_details[:4]:
        card = f"**{repo.name}**"
        if repo.description:
            card += f" — {repo.description}"
        meta_parts: list[str] = []
        if repo.language:
            meta_parts.append(repo.language)
        if repo.stars > 0:
            meta_parts.append(f"⭐{repo.stars:,}")
        if meta_parts:
            card += f" *({', '.join(meta_parts)})*"
        lines.append(card)
        lines.append("")
    return lines


def _build_stack_line(sm: dict) -> str:
    """Build a concise stack line from language signals."""
    primary = _sv(sm, "primary_language")
    recent = _sv(sm, "recent_primary_language")
    diversity = int(_fv(sm, "language_diversity"))

    if not primary:
        return ""

    parts = [primary]
    if recent and recent != primary:
        parts.append(f"{recent} (recent)")
    if diversity > 2:
        parts.append(f"+ {diversity - 1} other{'s' if diversity > 2 else ''}")
    return " · ".join(parts)


def _build_recent_direction(sm: dict) -> str:
    """Signal beat: recent trajectory and language shifts."""
    parts: list[str] = []

    shifted = _fv(sm, "language_shifted")
    recent_lang = _sv(sm, "recent_primary_language")
    primary_lang = _sv(sm, "primary_language")
    trajectory = _sv(sm, "activity_trajectory")
    months = int(_fv(sm, "months_active_last_year"))
    streak = int(_fv(sm, "streak_months"))

    if shifted > 0 and recent_lang and primary_lang and recent_lang != primary_lang:
        parts.append(f"Noticeably shifting toward **{recent_lang}** (from {primary_lang}).")

    if trajectory == "growing":
        parts.append("Activity is accelerating.")
    elif trajectory == "declining":
        parts.append("Output has tapered recently.")
    elif trajectory == "stable" and months >= 8:
        parts.append(f"Consistent cadence — active {months}/12 months last year.")

    if streak >= 4 and not parts:
        parts.append(f"{streak}-month active streak.")

    return " ".join(parts)


def _build_evidence_prose(sm: dict) -> str:
    """Evidence beat: commit patterns in prose form."""
    parts: list[str] = []

    feat = _fv(sm, "feature_ratio")
    fix = _fv(sm, "fix_ratio")
    ref = _fv(sm, "refactor_ratio")
    churn = _fv(sm, "avg_churn_per_commit")
    pr_count = int(_fv(sm, "pr_authored_count"))

    if feat + fix + ref > 0:
        dominant_label, dominant_pct = max(
            [("feature work", feat), ("bug fixes", fix), ("refactoring", ref)],
            key=lambda x: x[1],
        )
        commit_str = f"Commits skew toward {dominant_label} ({dominant_pct:.0%})"
        if churn > 500:
            commit_str += f", landing in large batches (~{churn:,.0f} lines)"
        elif churn > 0 and churn < 60:
            commit_str += f", small and surgical (~{churn:.0f} lines)"
        commit_str += "."
        parts.append(commit_str)

    if pr_count > 20:
        parts.append(f"{pr_count:,} PRs authored." if pr_count > 100 else f"{pr_count} PRs authored.")

    return " ".join(parts)

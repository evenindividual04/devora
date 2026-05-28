# **LLM-as-Judge Evaluation Framework for Automated GitHub Profile Generation**

The evaluation of open-ended, long-form generative text systems has historically presented one of the most complex challenges in machine learning operations. When engineering a system that translates structured data—such as GitHub activity signals, commit histories, and repository metadata—into cohesive, natural language developer profiles, traditional evaluation paradigms structurally fail. Lexical overlap metrics cannot capture the essence of a compelling developer biography. Consequently, the adoption of Large Language Models (LLMs) as automated evaluators, a methodology termed "LLM-as-a-judge," has emerged as the definitive standard for assessing complex, qualitative text generation. Designing an evaluation architecture for a Gemini-powered GitHub profile generator requires a rigorous synthesis of reference-based grounding checks, reference-free qualitative assessments, and statistical monitoring frameworks to detect non-deterministic regressions in production.

## **1\. The Evolution and Mechanics of LLM-as-Judge**

The transition from static natural language processing metrics to LLM-driven evaluation is rooted in the fundamental inability of traditional statistical algorithms to parse semantic nuance, tonal appropriateness, and instruction adherence in open-ended generative tasks. Implementing an LLM-as-judge framework requires a deep understanding of its reliability, its inherent biases, and the specific prompt engineering techniques necessary to extract stable, calibrated judgments.

### **1.1 Reliability, Validity, and Inter-Rater Agreement**

The core premise of deploying an LLM as an evaluator relies on its ability to approximate human judgment at scale. Foundational studies evaluating LLM judges on benchmarks such as MT-Bench and the Chatbot Arena demonstrate that highly capable models, particularly GPT-4, can achieve approximately 80% to 87% agreement with expert human annotators.1 This percentage is highly significant, as it essentially matches the baseline of human-to-human inter-rater reliability, which typically plateaus around 81% for complex subjective text evaluation.2 Consequently, an optimized LLM judge is not merely a proxy for human evaluation; it operates at human-level consistency while functioning orders of magnitude faster and at a fraction of the cost.  
However, percentage agreement often masks the true statistical alignment between models and humans. To rigorously evaluate inter-rater reliability, the deployment of correlation metrics is required. The literature distinguishes between several mathematical approaches for measuring this alignment, outlined in the table below:

| Metric | Mathematical Focus | Interpretation for LLM Evaluation | Value Thresholds |
| :---- | :---- | :---- | :---- |
| **Cohen's Kappa (![][image1])** | Measures categorical agreement while adjusting for the probability of random chance agreement. | Highly conservative. Excellent for binary objective tasks (e.g., factual grounding checks) but heavily over-penalizes ordinal Likert scales. | 0.21–0.40 (Fair), 0.41–0.60 (Moderate), \>0.80 (High).4 |
| **Kendall's Tau (![][image2])** | Measures the strength and direction of association based on the relative ordering of pairs. | Robust to outliers. Ideal for pairwise comparisons (e.g., ranking two generated profiles to determine preference). | Ranges from \-1 to 1\. LLM judges frequently score 0.80–0.90.4 |
| **Spearman's Rho (![][image3])** | Measures correlation but is highly sensitive to the magnitude of differences between ranks. | Useful for continuous score scales where the distance between a score of 1 and 5 is mathematically significant. | Ranges from \-1 to 1\. Standard LLMs score 0.60–0.70 on faithfulness tasks.4 |

Research indicates a notable dichotomy in what LLM judges are inherently good versus bad at evaluating. They demonstrate exceptional proficiency at instruction following, format verification, and objective policy adherence (e.g., identifying toxicity or extracting explicit data points).5 Conversely, they struggle significantly with complex mathematical reasoning, multi-hop logic, and evaluating highly subjective tonal nuances unless explicitly guided by highly granular, atomic criteria.4 If a prompt relies on an ambiguous definition of "quality," the LLM's correlation with human judgment degrades precipitously.

### **1.2 Inherent Biases in LLM Evaluators**

Despite their high correlation with human experts under controlled conditions, naive implementations of LLM judges introduce severe systemic biases. The continuous output space of LLMs means their decision boundaries can be warped by stylistic artifacts in the generated text that do not actually correlate with quality. A robust profile evaluation system must explicitly architect mitigations for the following documented biases.

| Bias Type | Definition & Mechanism | Impact on Profile Generation Evaluation | Mitigation Architecture |
| :---- | :---- | :---- | :---- |
| **Verbosity Bias** | The systematic tendency to assign higher scores to longer, wordier responses, conflating length with quality and depth.3 | The judge will penalize a punchy, highly effective 300-word GitHub README and reward a rambling, generic 1200-word essay. | Implement strict length-controlled evaluation protocols; explicitly command the prompt to penalize unnecessary verbosity and reward information density.4 |
| **Position Bias** | In pairwise comparisons, the tendency to consistently favor the response presented in a specific position within the prompt context (typically the first position).3 | When comparing a baseline generator to a new Gemini prompt version, the judge may arbitrarily favor the baseline if it is parsed first. | Utilize position-swapping algorithms; calculate Position Consistency metrics to discard biased evaluations, or use direct scoring instead of pairwise.3 |
| **Self-Enhancement Bias** | The phenomenon where an LLM evaluates text generated by its own model family higher than text generated by competing architectures.3 | A Gemini-based judge might artificially inflate the scores of the Gemini-generated developer profiles. | Employ a Panel of LLMs (PoLL) incorporating models from distinct organizational families (e.g., Claude, GPT-4, Gemini) and average their outputs.4 |
| **Provenance / Recency Bias** | Favoring specific stylistic patterns, vocabulary, or phrasing associated with the judge's own recent Reinforcement Learning from Human Feedback (RLHF) training data.4 | The judge heavily rewards cliché AI phrasing like "delve into" or "testament to" because it mirrors its own default generative state. | Inject negative constraints into the prompt explicitly forbidding the rewarding of known AI-generated stylistic tropes.9 |
| **Over-Reasoning (Overthinking)** | The tendency for highly capable models to inject external pre-training knowledge rather than strictly evaluating the provided reference text.4 | The judge assumes a developer knows React because they know JavaScript, even if React is not in the source GitHub signals. | Insert explicit "do not overthink" instructions, forcing the model to operate strictly as a string-matching constraint engine.4 |

### **1.3 Prompt Engineering Techniques for Judge Reliability**

To circumvent these biases and achieve the 80%+ inter-rater reliability threshold, the evaluation architecture must utilize structured prompting methodologies.  
First, the system must enforce **Single-Dimension Isolation**. Evaluators experience significant cognitive degradation when asked to assess multiple qualitative dimensions simultaneously (e.g., scoring tone, factuality, and formatting in a single prompt).4 The most reliable architecture executes separate, isolated API calls for each specific quality dimension.  
Second, the architecture must utilize **Chain-of-Thought (CoT) Reasoning**. Prompting the LLM to articulate its step-by-step logical deduction *before* outputting a final score significantly increases judgment accuracy, particularly for models larger than 50 billion parameters.4 By generating the reasoning first, the LLM conditions its final token output on a logical pathway rather than a probabilistic guess.  
Third, whenever feasible, the system should map continuous scales to **Categorical or Binary Outputs**. While 1-10 numerical scales are common, they frequently produce plateaus, discontinuous jumps, and model-specific scale drift in production.11 Binary decisions (e.g., Grounded vs Hallucinated) or strict categorical rubrics (e.g., Generic, Moderate, Specific) yield much higher stability and are vastly easier to calibrate against human baselines.4

## **2\. Reference-Based vs. Reference-Free Architectural Tradeoffs**

Evaluating a generated GitHub profile README requires a hybrid architectural approach, as the concept of "quality" spans both objective factual accuracy and subjective stylistic appropriateness. A single evaluation methodology cannot capture both elements effectively.

### **2.1 The Failure of Automated n-gram and Embedding Metrics**

Traditional natural language processing evaluation relied heavily on reference-based metrics such as BLEU, ROUGE, and exact match algorithms. These metrics operate by comparing the generated text to a "gold standard" human-written reference, rewarding lexical overlap.12 More recent metrics, such as BERTScore, utilize contextual embeddings to measure semantic similarity.5  
However, in the domain of open-ended biography and profile generation, these metrics face catastrophic structural failures.13 A developer's career trajectory and GitHub activity can be described in an infinite number of valid ways. A generated README could be highly engaging, perfectly accurate, structurally flawless, and highly specific, yet score a near-zero on ROUGE or BLEU simply because it utilizes different phrasing, pacing, or formatting than the human reference text. Furthermore, reference-based string similarity inherently penalizes meaningful revisions and generative creativity, pushing models toward rigid, templated outputs.5 Therefore, static human-reference comparison for textual quality is fundamentally inappropriate for this application.

### **2.2 The Role of the "Gold Standard" Human README**

While human-written READMEs should not be used for text-overlap scoring, they remain crucial in the calibration phase of the evaluation system. Human "gold standards" should be utilized to teach the LLM judge the structural and tonal expectations of the domain.15 By embedding examples of highly rated, human-authored profiles in the few-shot prompting context of the LLM judge, the system learns the desired distribution of markdown elements, the appropriate use of repository badges, and the expected brevity of the introduction. In this context, the human README is a stylistic anchor rather than a textual comparison target.

### **2.3 Reference-Free Evaluation for Qualitative Dimensions**

For evaluating subjective dimensions where no single "correct" answer exists, the system must rely on **Reference-Free Evaluation**.15 In this paradigm, the LLM judge assesses the generated output entirely on its own merits, guided by a highly detailed, operationalized rubric.15  
Reference-free evaluation is essential for assessing dimensions such as:

* **Authenticity:** Does the text avoid generic AI clichés and read like a genuine developer?  
* **Tonal Appropriateness:** Does the voice match the collaborative, pragmatic ethos of the open-source community?  
* **Structural Coherence:** Is the markdown well-formed, readable, and properly segmented?

These elements require the LLM to approximate human aesthetic and professional judgment without relying on an external data source.15

### **2.4 Reference-Based Evaluation for Falsifiability and Grounding**

While reference-free evaluation governs style, **Reference-Based Evaluation** is mandatory for ensuring factual correctness. In the context of a GitHub profile generator, the "reference" is not a human text, but the raw, structured source data—the JSON payloads containing the developer's commit history, language telemetry, repository stars, and pull request metadata.17  
The evaluation of factual grounding is perhaps the most critical guardrail for an automated profile generator, as LLMs are highly prone to hallucinating skills, exaggerating metrics, and inventing repository names.8 The DeepMind FACTS Grounding framework provides a highly robust methodology for this exact challenge.8  
Applying the FACTS methodology to GitHub profiles requires a multi-phase verification process:

1. **Claim Extraction:** The LLM judge parses the generated README and extracts every single factual claim (e.g., "Maintains a repository with 500 stars," "Primarily codes in Rust").  
2. **Entailment Inference Check:** The judge acts as a strict verification engine, comparing each extracted claim against the raw GitHub signal JSON. It must determine if the claim is explicitly supported (grounded), directly contradicted, or unverifiable (hallucinated) based *only* on the provided data.17  
3. **Multi-Judge Aggregation:** Because single models often exhibit bias in evaluating factual alignments, the FACTS framework utilizes a Panel of LLMs (e.g., Gemini 1.5 Pro, GPT-4o, Claude 3.5 Sonnet). The independent grounding scores from all models are mathematically averaged, which aggressively reduces random measurement errors and provides highly stable factual accuracy metrics.8

## **3\. Evaluation Dimensions for Developer Profiles**

Quality is inherently subjective and deeply dependent on the target audience.14 To build an automated evaluation system that does not collapse into ambiguous, uncalibrated scoring, abstract concepts of "quality" must be translated into measurable, distinct dimensions with explicit grading rubrics.19  
Best practices for GitHub profile READMEs dictate that they should be concise, visually structured, highlight specific technical achievements, and showcase personality without reverting to dense, unreadable walls of text.20  
The following evaluation framework operationalizes six critical quality dimensions specifically designed for assessing developer profiles generated from activity signals.

### **3.1 Dimension 1: Specificity (Information Density)**

**Operational Definition:** The degree to which the profile highlights distinct, quantifiable, and unique aspects of the developer's engineering work. High specificity anchors the narrative in concrete data points—naming specific libraries, architectural patterns, and exact metrics (stars, PRs, commits)—rather than relying on sweeping generalizations. It measures the density of relevant technical information per sentence.

* **Score 1/5 (Highly Generic):** The text relies entirely on broad generalizations that could apply to any software engineer on the platform. It states the developer writes code but provides no verifiable evidence of their domain or impact.  
  * *Example Output:* "I am a passionate software engineer who loves coding and building scalable applications. I enjoy collaborating on open-source projects and learning new technologies every day to solve complex problems and deliver value."  
* **Score 5/5 (Highly Specific):** The text is deeply anchored in concrete data extracted from the signals. It names specific technologies, verifiable achievements, and clear domain focuses, maximizing information density.  
  * *Example Output:* "Backend engineer specializing in distributed systems. Primary maintainer of hyper-cache, a Rust-based caching layer processing 10k+ ops/sec. Heavily active in the Kubernetes open-source ecosystem, with 45 recent merged PRs focused on optimizing pod scheduling algorithms in Go."

### **3.2 Dimension 2: Authenticity (Lexical Naturalness and Anti-Pattern Detection)**

**Operational Definition:** The extent to which the text reads like it was genuinely authored by a human developer, penalizing the presence of known AI-generated stylistic tropes. Recent large-scale textual analyses demonstrate that LLMs chronically overuse specific lexical markers, transition words, and hyperbolic adjectives.9 This dimension operates as an automated anti-pattern detector, heavily penalizing words such as "delve," "tapestry," "testament," "realm," "bustling," "orchestrate," and "crucial".9 It rewards standard, direct, and pragmatic developer communication styles.

* **Score 1/5 (Highly Artificial):** The text is saturated with recognizable AI markers, hyperbolic adjectives, and flowery transitions that no human engineer would naturally use in technical documentation.  
  * *Example Output:* "Delve into the vibrant tapestry of my coding journey. It is a true testament to my unwavering dedication to the ever-evolving landscape of software development. Furthermore, I orchestrate seamless synergistic integrations, maximizing efficiency in the digital realm."  
* **Score 5/5 (Authentic and Direct):** The text utilizes straightforward, pragmatic language typical of technical communication. Lexical diversity is high, but hyperbolic adjectives and formulaic transitional phrases are completely absent.  
  * *Example Output:* "Hi, I'm Alex. I build and maintain data pipelines. Most of my recent work involves optimizing PostgreSQL queries and migrating legacy Python monoliths to containerized microservices. When I'm not writing code, I'm usually updating documentation or triaging issues for the Apache Superset community."

### **3.3 Dimension 3: Falsifiability (Factual Grounding)**

**Operational Definition:** A strict reference-based metric measuring whether every explicit technical claim, statistical achievement, or skill mentioned in the generated text is directly supported by the provided GitHub source signals.17 It heavily penalizes hallucination, data exaggeration, and the assumption of skills not present in the repository telemetry.

* **Score 1/5 (Hallucinated/Exaggerated):** The profile invents skills, repositories, or metrics that do not exist in the source data, or vastly exaggerates minor data points (e.g., claiming "Expert in C++" when the source data shows a single 5-line script).  
  * *Example Output (Where source data only shows basic HTML/CSS):* "Full-stack developer with 5 years of enterprise experience in building robust AWS serverless architectures and managing complex Kubernetes CI/CD pipelines."  
* **Score 5/5 (Perfectly Grounded):** Every technical skill, metric, and repository mentioned can be verified via exact match to the source signal JSON. No assumptions are made beyond the provided data, and data is represented accurately.  
  * *Example Output (Where source data shows 45 merged PRs to React and 3 pinned JS repos):* "Frontend developer with a strong focus on React. Experienced in open-source collaboration, having successfully merged over 40 pull requests to major JavaScript ecosystem repositories."

### **3.4 Dimension 4: Tonal Appropriateness**

**Operational Definition:** The alignment of the text's tone with the standard expectations of the open-source software community. It must be professional, reasonably humble, and appropriately engaging without being overly corporate, excessively marketing-driven, or inappropriately casual.20

* **Score 1/5 (Inappropriate Tone):** The text is either overly formal and corporate to the point of being jarring on GitHub, or inappropriately informal.  
  * *Example Output (Corporate):* "A highly synergized enterprise asset dedicated to maximizing shareholder value through mission-critical paradigm shifts in the algorithmic sector. Ready to leverage core competencies."  
* **Score 5/5 (Appropriate Tone):** Professional but welcoming. It strikes a balance between showcasing technical expertise and remaining approachable for community collaboration.  
  * *Example Output:* "Welcome to my GitHub\! I'm a developer focused on making open-source tools more accessible. Feel free to open an issue on any of my repositories or reach out if you'd like to collaborate on data visualization projects."

### **3.5 Dimension 5: Structural Coherence and Formatting**

**Operational Definition:** Evaluates the markdown formatting, logical flow, and scannability of the README. Recruiters and developers typically spend approximately 30 seconds scanning a profile.20 High-quality profiles utilize clear headings, bulleted lists, dynamic stat badges, and avoid monolithic blocks of text.21

* **Score 1/5 (Unreadable):** The text is presented as a massive, unformatted block of text with no markdown structural elements, making it impossible to skim effectively.  
* **Score 5/5 (Highly Readable):** The text is broken into logical, modular sections utilizing appropriate headers (e.g., "👋 About Me", "🛠 Tech Stack", "📈 Recent Activity"). It employs bullet points for rapid reading and concise paragraphs.

### **3.6 Dimension 6: Noise-to-Signal Relevance**

**Operational Definition:** Measures the system's ability to filter out trivial or irrelevant GitHub activity (e.g., automated dependency bot merges, minor typo fixes, fork syncing) and elevate highly meaningful signals (e.g., architectural PRs, popular original repositories, consistent language trends).

* **Score 1/5 (High Noise):** The text focuses heavily on trivial metadata, fundamentally misrepresenting the developer's actual engineering impact.  
  * *Example Output:* "I am highly active on GitHub, having made 500 commits this year. Most of my work involves running npm update, fixing README typos in various repositories, and syncing forks."  
* **Score 5/5 (High Signal):** The text effectively ignores automated noise and synthesizes the data to highlight actual engineering value and significant contributions.  
  * *Example Output:* "In the past year, I've focused heavily on performance optimizations, successfully reducing memory leaks in the core rendering engine of Project X and contributing major feature updates to the Y framework."

## **4\. Benchmark Dataset Design and Calibration**

To ensure the LLM-as-judge produces reliable, calibrated metrics, it cannot operate in a vacuum. It must be tested against a high-quality benchmark dataset. Drawing from the architectural designs of historical table-to-text generation benchmarks—such as WikiBio (728,000 Wikipedia biographies and infoboxes), ToTTo, and SynthBio (fictional structured-to-text data)—a robust benchmark requires paired structured inputs and natural language outputs.26  
However, unlike static datasets, evaluating generative pipelines requires assessing the *system's* outputs, not human outputs. A benchmark is defined as a collection of tasks structured as 4-tuples: \<request, environment, stopping criteria, scorer\>.29

### **4.1 Ground-Truth Dataset Collection**

To build a specialized benchmark for GitHub profile generation, the dataset must capture a wide distribution of developer archetypes. The collection strategy should be structured as follows:

1. **Input Collection (The Environment):** Curate a diverse set of highly realistic GitHub signal data (JSON payloads). This must include distinct profiles: the prolific open-source maintainer, the corporate enterprise developer with mostly private commits, the student with numerous small projects, the frontend specialist, and the polyglot.  
2. **Output Generation (The Request):** Use the Gemini pipeline to synthesize READMEs from these signals. To ensure the benchmark contains a wide distribution of quality (both excellent and terrible responses), sample the outputs across different temperature settings, older prompt versions, and ablated models.

### **4.2 Benchmark Sizing and Public/Private Splits**

A reliable benchmark does not strictly require massive scale; it requires high variance and representative edge cases. Based on methodologies from DeepMind's FACTS framework, the dataset should be sized and split effectively 8:

* **Initial Calibration Set:** Approximately 200 highly diverse examples are sufficient for initial prompt engineering and aligning the LLM judge with human expectations.  
* **Canary Test Set:** A specialized subset of \~50 representative, challenging edge-case prompts. This set is designed to run automatically on every deployment pipeline to catch silent regressions before code reaches production.30  
* **Public/Private Split:** To prevent the generator model from overfitting to the evaluation metric over time, the benchmark must be split into an "Open" public set (used for active prompt development) and a "Blind" held-out set (used only for final release validation). A 50/50 split is standard practice.8

### **4.3 Labeling Protocol: Critique Shadowing and Subjective Alignment**

Because dimensions like "Authenticity" and "Tonal Appropriateness" are highly subjective, crowdsourcing labels frequently introduces noise. To produce reliable quality annotations, the labeling protocol must employ **Critique Shadowing** and interactive criteria alignment.4

1. **Identify Principal Domain Experts:** Select 2-3 principal engineers or technical recruiters who deeply understand the target audience.19  
2. **Trace Disagreements:** Have these experts manually score the 200-example calibration set using the 6 dimensions defined above. Simultaneously, run the LLM judge on the same set.  
3. **Interactive Alignment Loop (EvalLM Methodology):** When the LLM judge's score diverges from the human expert's score, the system enters an interactive alignment phase.4 The human reviews the LLM's Chain-of-Thought (CoT) explanation to identify exactly where the LLM's interpretation of a concept (e.g., "authenticity") deviates from the human's intent. The broad rubric is then automatically split, merged, and refined into fine-grained, highly specific constraints within the judge's prompt until the LLM perfectly aligns with the expert's paradigm.4

## **5\. Structuring the Prompt Template for LLM-as-Judge**

To execute the evaluation, the LLM-as-judge prompt must integrate Chain-of-Thought reasoning, explicit constraints against biases, and single-dimension isolation.4  
To mitigate the inherent non-deterministic variance of LLM scoring—where the same prompt might yield a score of 4 on one run and a 5 on another—the system should utilize **G-Eval methodologies**. In a standard implementation, the system parses the final integer output from the text. In a G-Eval implementation, the system extracts the token probabilities from the LLM's response matrix. It calculates a weighted continuous score based on the probability distribution of the output tokens (e.g., if the model is 80% confident in a '4' and 20% confident in a '5', the normalized score is 4.2), yielding vastly more stable metrics.4

### **5.1 Recommended Prompt Architecture**

Below is the recommended prompt architecture for evaluating the **Authenticity** dimension. This template must be programmatically replicated and specialized for each of the six dimensions.

# **SYSTEM ROLE**

You are an expert technical recruiter and senior engineering manager. Your task is to evaluate an auto-generated GitHub profile README based strictly on a single specific quality dimension.

# **EVALUATION DIMENSION: Authenticity (Lexical Naturalness)**

Definition: The extent to which the text reads like it was genuinely authored by a human developer. It heavily penalizes the presence of known AI-generated stylistic tropes, transition words, and overused hyperbolic vocabulary. It rewards standard, direct, and pragmatic developer communication styles.

# **SCORING RUBRIC**

Score 1: Highly Artificial. The text is saturated with AI markers and flowery transitions that no human developer would use.  
Score 2: Artificial. Contains multiple distinct AI clichés, making it obvious it was generated.  
Score 3: Moderate. Generally reads well, but contains 1-2 generic transitional phrases or slightly hyperbolic adjectives.  
Score 4: Authentic. Pragmatic language typical of technical communication. Highly readable, no hyperbolic adjectives.  
Score 5: Exceptional Authenticity. Direct, highly natural developer communication. Completely devoid of formulaic AI phrasing.

# **CONSTRAINTS & BIAS MITIGATION**

1. DO NOT overthink. Base your evaluation solely on the provided text.  
2. Ignore formatting, factual accuracy, and information density. You are scoring ONLY Authenticity.  
3. SEVERE PENALTY: If the text contains any of the following words, the score MUST NOT exceed 2: "delve", "tapestry", "testament", "realm", "bustling", "orchestrate", "crucial", "dynamic", "vibrant", "synergistic".  
4. Length does not equal quality. Penalize unnecessary verbosity.

# **INPUT DATA**

# **OUTPUT FORMAT**

You must output a JSON object with exactly two fields:

1. "reasoning": A step-by-step logical deduction explaining your score based on the rubric, explicitly checking for the prohibited vocabulary.  
2. "score": An integer between 1 and 5\.

{  
"reasoning": "...",  
"score":  
}

## **6\. Regression Detection and Production Monitoring**

Once the generation pipeline is deployed to production, it operates within a continuous and non-deterministic output space. Traditional deterministic unit testing (e.g., assert output \== expected\_string) fails entirely because two semantically equivalent, high-quality generated profiles will look completely different as text strings.30 Furthermore, LLMs suffer from model drift, where their underlying behavioral distributions shift over time due to silent API provider updates (e.g., a new RLHF alignment altering default vocabulary) or changes in the input data structure.33  
Detecting quality regressions therefore requires a shift from point-in-time assertions to continuous statistical monitoring, analyzing distribution shifts in the LLM's outputs over time.34

### **6.1 Statistical Approaches to Distribution Shift**

Instead of evaluating individual strings, the production monitoring system aggregates the scores produced by the LLM-as-judge over a sliding time window (e.g., daily or weekly cohorts). It then compares the mathematical distribution of those scores against a baseline distribution derived from a known "healthy" calibration state.36  
Two highly reliable statistical tests are recommended for detecting these shifts in production environments:

#### **6.1.1 Population Stability Index (PSI)**

The Population Stability Index (PSI) is a widely utilized metric for quantifying the absolute magnitude of shift in the distribution of a variable over time.33 Mathematically, PSI operates as a symmetrized version of the Kullback-Leibler (KL) divergence, measuring the expected excess surprise in using the actual production distribution versus the expected baseline distribution.38  
To calculate PSI for the generated quality scores, the continuous or categorical scores are divided into discrete bins (e.g., using equi-width binning for score ranges). The PSI is calculated using the following formula 38:  
![][image4]  
Where:

* ![][image5] is the total number of bins.  
* ![][image6] is the proportion of counts within bin ![][image7] from the current production distribution (Actual).  
* ![][image8] is the proportion of counts within bin ![][image7] from the baseline training distribution (Expected).

(Note: To handle instances where a bin is completely empty, which would cause the natural logarithm to become undefined or unbounded, a standard mathematical adjustment adds a base count of 1 or a fractional value of 0.01 to each bin proportion.38)  
**Meaningful Thresholds for PSI:**

* **PSI \< 0.1:** Very slight change in distribution. The system is stable; no regression detected.  
* **0.1 ![][image9] PSI ![][image9] 0.2:** Moderate distribution shift. Triggers a warning alert for manual review, indicating minor drift in user inputs or model behavior.  
* **PSI \> 0.2:** Significant, statistically meaningful distribution shift.38 Triggers a critical automated alert indicating a severe quality drop, a fundamental shift in user input patterns, or a silent API upgrade altering model outputs.

#### **6.1.2 Kolmogorov-Smirnov (K-S) Test**

While PSI provides a clear magnitude of drift, the two-sample Kolmogorov-Smirnov (KS) test provides a non-parametric method to determine if the divergence between the current scores and baseline scores is statistically significant.39  
The KS statistic measures the maximum vertical distance between the empirical cumulative distribution functions (CDFs) of the two datasets 40:  
![][image10]  
If the KS test returns a high distance (![][image11]) and a ![][image12]\-value ![][image13], the system flags a structural regression in the generation pipeline.41 The KS test is highly sensitive and particularly useful for detecting if a specific cohort of profiles (e.g., profiles for newly registered GitHub users with sparse data) is degrading, even if the overall system average remains seemingly stable.

### **6.2 Recommended Production Monitoring Architecture**

To construct a robust, highly reliable quality measurement pipeline for the GitHub profile generator, the architecture must integrate offline testing and online observability 43:

1. **Canary Deployment Gates (Offline):** Before promoting any new system prompt version, context-window adjustment, or Gemini API upgrade to production, route the 50-example "Canary Test Set" through the new pipeline.30 The LLM judge must score the outputs. If the aggregate score on any dimension drops below a hard threshold, or if the PSI indicates a shift ![][image14] against the last deployment, the release is automatically blocked.30  
2. **Asynchronous Scoring Queues (Online):** Running the LLM-as-judge inline with live user requests introduces massive latency and unnecessary costs. Instead, the application must log the input signals and the generated README as a single trace. An asynchronous background worker samples a statistically significant subset of these traces (e.g., 5% to 10% of all generated profiles) and processes them through the 6-dimension LLM judge prompts.43  
3. **Behavioral and Semantic Guardrails:** The monitoring system should track specific categorical occurrences continuously. For instance, track the absolute frequency of known AI anti-patterns (Dimension 2: Authenticity). If the incidence rate of the word "delve" or "tapestry" spikes from 2% to 15% across generated profiles within a 48-hour window, a semantic drift alert is triggered. This indicates the underlying generator model has likely received a provider-side alignment update that requires immediate prompt refactoring.9  
4. **Trace Observability:** A numerical judge score is entirely useless without diagnostic context. All judge scores, CoT reasoning chains, and calculated PSI metrics must be tied back directly to the execution trace.11 If the PSI triggers an alert for a drop in "Falsifiability," engineers must be able to click into the observability dashboard and instantly view the exact GitHub JSON signals, the specific generated README, and the LLM judge's step-by-step reasoning explaining exactly which claim was hallucinated.11 This tight coupling between automated evaluation and manual inspectability is the foundation of reliable generative AI operations.

#### **Works cited**

1. LLM as a Judge: The Complete Guide | Galtea Blog \- Galtea.ai, accessed May 28, 2026, [https://galtea.ai/blog/llm-as-a-judge-the-complete-guide](https://galtea.ai/blog/llm-as-a-judge-the-complete-guide)  
2. Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena | OpenReview, accessed May 28, 2026, [https://openreview.net/forum?id=uccHPGDlao](https://openreview.net/forum?id=uccHPGDlao)  
3. A Survey on LLM-as-a-Judge \- arXiv, accessed May 28, 2026, [https://arxiv.org/html/2411.15594v1](https://arxiv.org/html/2411.15594v1)  
4. Evaluating the Effectiveness of LLM-Evaluators (aka LLM-as-Judge) \- Eugene Yan, accessed May 28, 2026, [https://eugeneyan.com/writing/llm-evaluators/](https://eugeneyan.com/writing/llm-evaluators/)  
5. Identifying Reliable Evaluation Metrics for Scientific Text Revision \- arXiv, accessed May 28, 2026, [https://arxiv.org/html/2506.04772v5](https://arxiv.org/html/2506.04772v5)  
6. Identifying Reliable Evaluation Metrics for Scientific Text Revision \- ACL Anthology, accessed May 28, 2026, [https://aclanthology.org/2025.acl-long.335.pdf](https://aclanthology.org/2025.acl-long.335.pdf)  
7. How to Calibrate LLM-as-a-Judge with Human Corrections \- LangChain, accessed May 28, 2026, [https://www.langchain.com/articles/llm-as-a-judge](https://www.langchain.com/articles/llm-as-a-judge)  
8. DeepMind FACTS Framework 2026: LLM Factual Accuracy Guide, accessed May 28, 2026, [https://galileo.ai/blog/deepmind-facts-framework-llm-factual-accuracy](https://galileo.ai/blog/deepmind-facts-framework-llm-factual-accuracy)  
9. Wikipedia:Signs of AI writing, accessed May 29, 2026, [https://en.wikipedia.org/wiki/Wikipedia:Signs\_of\_AI\_writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)  
10. Words and Phrases that Make it Obvious You Used ChatGPT | by Margaret Efron \- Medium, accessed May 29, 2026, [https://medium.com/learning-data/words-and-phrases-that-make-it-obvious-you-used-chatgpt-2ba374033ac6](https://medium.com/learning-data/words-and-phrases-that-make-it-obvious-you-used-chatgpt-2ba374033ac6)  
11. How to build LLM-as-a-Judge evaluators that hold up in production ..., accessed May 28, 2026, [https://arize.com/blog/how-to-build-llm-as-a-judge-evaluators-that-hold-up-in-production/](https://arize.com/blog/how-to-build-llm-as-a-judge-evaluators-that-hold-up-in-production/)  
12. Evaluation metrics | Microsoft Learn, accessed May 28, 2026, [https://learn.microsoft.com/en-us/ai/playbook/technology-guidance/generative-ai/working-with-llms/evaluation/list-of-eval-metrics](https://learn.microsoft.com/en-us/ai/playbook/technology-guidance/generative-ai/working-with-llms/evaluation/list-of-eval-metrics)  
13. LLM Evaluation Metrics: The Ultimate LLM Evaluation Guide ..., accessed May 28, 2026, [https://www.confident-ai.com/blog/llm-evaluation-metrics-everything-you-need-for-llm-evaluation](https://www.confident-ai.com/blog/llm-evaluation-metrics-everything-you-need-for-llm-evaluation)  
14. How to Build AI Benchmarks That Evolve with Your Models \- Label Studio, accessed May 28, 2026, [https://labelstud.io/blog/how-to-build-ai-benchmarks-that-evolve-with-your-models/](https://labelstud.io/blog/how-to-build-ai-benchmarks-that-evolve-with-your-models/)  
15. LLM evaluation metrics and methods, explained simply \- Evidently AI, accessed May 28, 2026, [https://www.evidentlyai.com/llm-guide/llm-evaluation-metrics](https://www.evidentlyai.com/llm-guide/llm-evaluation-metrics)  
16. LLM evaluation: from classic metrics to modern methods \- Toloka AI, accessed May 28, 2026, [https://toloka.ai/blog/llm-evaluation-from-classic-metrics-to-modern-methods/](https://toloka.ai/blog/llm-evaluation-from-classic-metrics-to-modern-methods/)  
17. Factual Correctness \- Ragas, accessed May 28, 2026, [https://docs.ragas.io/en/stable/concepts/metrics/available\_metrics/factual\_correctness/](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/factual_correctness/)  
18. FACTS Grounding: A new benchmark for evaluating the factuality of large language models, accessed May 28, 2026, [https://deepmind.google/blog/facts-grounding-a-new-benchmark-for-evaluating-the-factuality-of-large-language-models/](https://deepmind.google/blog/facts-grounding-a-new-benchmark-for-evaluating-the-factuality-of-large-language-models/)  
19. Using LLM-as-a-Judge For Evaluation: A Complete Guide – Hamel's ..., accessed May 28, 2026, [https://hamel.dev/blog/posts/llm-judge/](https://hamel.dev/blog/posts/llm-judge/)  
20. What are the best practices for making a standout GitHub profile README? · drknzz GitHub-Achievements · Discussion \#789, accessed May 29, 2026, [https://github.com/drknzz/GitHub-Achievements/discussions/789](https://github.com/drknzz/GitHub-Achievements/discussions/789)  
21. How to write a good README \- GitHub, accessed May 29, 2026, [https://github.com/banesullivan/README](https://github.com/banesullivan/README)  
22. Best Practices for Optimizing a GitHub Profile? · community · Discussion \#154875, accessed May 29, 2026, [https://github.com/orgs/community/discussions/154875](https://github.com/orgs/community/discussions/154875)  
23. Delving Into PubMed Records: How AI-Influenced Vocabulary has Transformed Medical Writing since ChatGPT \- PMC, accessed May 29, 2026, [https://pmc.ncbi.nlm.nih.gov/articles/PMC12679996/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12679996/)  
24. Overused ChatGPT terms \- add to my list\! : r/ChatGPTPro \- Reddit, accessed May 29, 2026, [https://www.reddit.com/r/ChatGPTPro/comments/163ndbh/overused\_chatgpt\_terms\_add\_to\_my\_list/](https://www.reddit.com/r/ChatGPTPro/comments/163ndbh/overused_chatgpt_terms_add_to_my_list/)  
25. How to Design an Attractive GitHub Profile Readme… | by Piyush Malhotra \- Medium, accessed May 29, 2026, [https://medium.com/design-bootcamp/how-to-design-an-attractive-github-profile-readme-3618d6c53783](https://medium.com/design-bootcamp/how-to-design-an-attractive-github-profile-readme-3618d6c53783)  
26. DavidGrangier/wikipedia-biography-dataset \- GitHub, accessed May 28, 2026, [https://github.com/DavidGrangier/wikipedia-biography-dataset](https://github.com/DavidGrangier/wikipedia-biography-dataset)  
27. Towards More Effective Table-to-Text Generation: Assessing In-Context Learning and Self-Evaluation with Open-Source Models \- arXiv, accessed May 28, 2026, [https://arxiv.org/pdf/2410.12878](https://arxiv.org/pdf/2410.12878)  
28. SynthBio: A Case Study in Faster Curation of Text Datasets \- OpenReview, accessed May 28, 2026, [https://openreview.net/forum?id=Fkpr2RYDvI1](https://openreview.net/forum?id=Fkpr2RYDvI1)  
29. How to Build Good Language Modeling Benchmarks – Ofir Press, accessed May 28, 2026, [https://ofir.io/How-to-Build-Good-Language-Modeling-Benchmarks/](https://ofir.io/How-to-Build-Good-Language-Modeling-Benchmarks/)  
30. How are you testing and monitoring LLM behavior in production? : r/LLMDevs \- Reddit, accessed May 28, 2026, [https://www.reddit.com/r/LLMDevs/comments/1sre0n8/how\_are\_you\_testing\_and\_monitoring\_llm\_behavior/](https://www.reddit.com/r/LLMDevs/comments/1sre0n8/how_are_you_testing_and_monitoring_llm_behavior/)  
31. G-Eval Simply Explained: LLM-as-a-Judge for LLM Evaluation \- Confident AI, accessed May 28, 2026, [https://www.confident-ai.com/blog/g-eval-the-definitive-guide](https://www.confident-ai.com/blog/g-eval-the-definitive-guide)  
32. Deep Dive into G-Eval: How LLMs Evaluate Themselves | by Alexander Zlatkov | Medium, accessed May 28, 2026, [https://medium.com/@zlatkov/deep-dive-into-g-eval-how-llms-evaluate-themselves-743624d22bf7](https://medium.com/@zlatkov/deep-dive-into-g-eval-how-llms-evaluate-themselves-743624d22bf7)  
33. What Is Model Drift? | IBM, accessed May 28, 2026, [https://www.ibm.com/think/topics/model-drift](https://www.ibm.com/think/topics/model-drift)  
34. View From Above: A Framework for Evaluating Distribution Shifts in Model Behavior \- arXiv, accessed May 28, 2026, [https://arxiv.org/html/2407.00948v3](https://arxiv.org/html/2407.00948v3)  
35. Recursive Training Loops in LLMs: How training data properties modulate distribution shift in generated data? \- arXiv, accessed May 28, 2026, [https://arxiv.org/html/2504.03814v2](https://arxiv.org/html/2504.03814v2)  
36. Measuring Distributional Shifts in Text: The Advantage of Language Model-Based Embeddings \- arXiv, accessed May 28, 2026, [https://arxiv.org/html/2312.02337v1](https://arxiv.org/html/2312.02337v1)  
37. 7 Strategies To Solve LLM Reliability Challenges at Scale \- Galileo AI, accessed May 28, 2026, [https://galileo.ai/blog/production-llm-monitoring-strategies](https://galileo.ai/blog/production-llm-monitoring-strategies)  
38. Measuring Data Drift: Population Stability Index | Fiddler AI Blog, accessed May 28, 2026, [https://www.fiddler.ai/blog/measuring-data-drift-population-stability-index](https://www.fiddler.ai/blog/measuring-data-drift-population-stability-index)  
39. Managing Data Drift and Data Distribution Shifts in the MLOps Lifecycle for Machine Learning Models \- Abhishek Reddy, accessed May 28, 2026, [https://abhishek-reddy.medium.com/detecting-and-managing-data-distribution-shifts-in-the-mlops-lifecycle-for-machine-learning-models-1ea33ce84c3c](https://abhishek-reddy.medium.com/detecting-and-managing-data-distribution-shifts-in-the-mlops-lifecycle-for-machine-learning-models-1ea33ce84c3c)  
40. Kolmogorov–Smirnov (KS) Similarity \- The Agile Brand Guide®, accessed May 28, 2026, [https://agilebrandguide.com/wiki/data/kolmogorov-smirnov-ks-similarity/](https://agilebrandguide.com/wiki/data/kolmogorov-smirnov-ks-similarity/)  
41. FMI\_SU\_Yotkova\_Kastreva at SemEval-2026 Task 13: Lightweight Detection of LLM-Generated Code via Stylometric Signals \- arXiv, accessed May 28, 2026, [https://arxiv.org/html/2605.04157v1](https://arxiv.org/html/2605.04157v1)  
42. Drift Detection in Large Language Models: A Practical Guide | by ..., accessed May 28, 2026, [https://medium.com/@tsiciliani/drift-detection-in-large-language-models-a-practical-guide-3f54d783792c](https://medium.com/@tsiciliani/drift-detection-in-large-language-models-a-practical-guide-3f54d783792c)  
43. What is LLM evaluation? A practical guide to evals, metrics, and regression testing \- Articles, accessed May 28, 2026, [https://www.braintrust.dev/articles/llm-evaluation-guide](https://www.braintrust.dev/articles/llm-evaluation-guide)  
44. LLM-as-a-Judge \- Langfuse, accessed May 28, 2026, [https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge)

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAoAAAAYCAYAAADDLGwtAAAAeUlEQVR4XmNgGAUDBkqA+D+a2D6omCSy4G8g/gdlqwHxGSBuZsDUDBaYBMStQJyNJocCQApnAPEzdAlk4MMAUbiaAeIEEPsUigooALkH3S0g/mk0MbDgRSxix6Dsa8iCfjAOkhjIcyDwGEQIQAXRgQMDRPwXmvgIAgD4+CB4CdjpRwAAAABJRU5ErkJggg==>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAoAAAAXCAYAAAAyet74AAAAWUlEQVR4XmNgGAXUBpxA7AzEHkDsBcUgtguyot1A/B8PdgUpygXixVANILARiCWQ+HBgjcYHmUAQsDAQqbAfiD+gC2IDINNAigkCkEIddEF0IM9ApPtGDgAA3ZITGuefBmUAAAAASUVORK5CYII=>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAkAAAAYCAYAAAAoG9cuAAAAhElEQVR4XmNgGAU0BS5A/B+I90JpVVRpBoYSqAQMRKLxGYShAhxIYgJQMTjoQBcAAmN0MRDnGrIAECyCisMBiBOALAAVgysKQ+ZAATNUzA8mcB0qkAQTAIK/QDwPiQ9WcBqIj0LZv4FYB1kBCGBzDwoIYcB0DwY4x0CEoodAXI4uSBsAACnzIomnkF48AAAAAElFTkSuQmCC>

[image4]: <data:image/png;base64,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>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABEAAAAZCAYAAADXPsWXAAAAxklEQVR4XmNgGAWEQAsQfwTi/1D8HYjfA/EHIP4LFXsGV00AwAxBB1IMEPEv6BLYAEjhJnRBKMBlAQrwY4AoMkCXAAJBBoQ38YKzDLhtgrmCCV0CHcAUKkOxBhD3Q8VWIqnDC0CK9wGxCxA7Q+k4qPhWJHU4ASw8DNElgICdASJ3F10CHZxnwB0eIEBUzIAUfEYXhIIUBoj8UXQJZABLSOXoEkBgxACR+40uAQOgwDvJgHDqDSA+CMR7oTRMfAJMwygYBQMGAM+MOSX549GiAAAAAElFTkSuQmCC>

[image6]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADIAAAAaCAYAAAD1wA/qAAACTElEQVR4Xu2XO2gWQRSFT3xiBEUkhU0kBImFhQgi2ImCWBlIoUWKoIWS0kq0sLGxEHwgtpaioBALX40oRLBS1KBgIfioJCYkooive7kz2ZvjzGbWH9RiPziEOfexO/vPzG6AlpZ1okVsZmiS+1dZLXrLprBCtJnNwE82SjgjmoYVqz6LJsm7MpfdnNRNTaHqnWKZ6AebpeQar4f5dzhQwCvRETYD2vMBm45x0Wk2S9DGD9kM5Ca5EHU1GtvJpmMx6uuT7IcV7eYAbC3/yUQuiGbZDBxEWT/N2cVmHRPIN74Oiw1yYAG05iSbgTew+BLRVdHIvGjFC9EjNuvIPfEdMP8sBwrQug1sBuL1ToXxbdGHKjzHMaTvK0tsrKfJR9GXMH4qWuvymB7Y8ZoiPvEUGjvqxr3BY+KSLyImH+BAAVq3l81A7gaG8Xss/vIbyd8W/CJeokGy4zCs7jgHArmeqetdS3jKVqT9JJpYnOzQTfpadJn8iPbUI5RR/3HCS93DPqT9JJqoL64m3At/b4qeOd+jffvZhO2/i26sb3HN3eK8iO6joonostDEQxyooRvVvtDT7LuLebTvCTZhNe/cWD9FbrmxRw8b/vXmcV40Azuh9LvqE8q/bfSJjsHeL8+Rf2KXYKdgihuoltMQxTwaT72kO2aPaJUbb0d+IiuRj5XQhc7qa3lC4zWov9h7NFu2nruic2x2yn3YUvwq2hS8UdiS1O+pb8FjlqJ+ojn0H6vc3vtn9MHeHU347yYRGYCt+RL0yF7OZktLS3N+AQgGmPlbDnlSAAAAAElFTkSuQmCC>

[image7]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAkAAAAaCAYAAABl03YlAAAAk0lEQVR4XmNgGFCgCMRM6IIw8BCI/0MxO5ocCljMAFGEF4AU/EQXRAcgRY3ogshAmQGiiAOI64B4PhAzoqgAgkUMEEUfGCAO14XyURSCBH4jC0DFNqALtCMLQMVewDiSUAEeuDTEGpDYRJhAGlQAGZRCxVRhAnZQAWQA4j9CE0NR1IHGhwNQxIIkQHgHmtwooCYAANGII3VrZN/xAAAAAElFTkSuQmCC>

[image8]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADMAAAAaCAYAAAAaAmTUAAACTklEQVR4Xu2WT0hVQRTGz8JAMfyDCzdBaMvAFm5ctGkhURAUblwHUqvWaWElBS2TWtQqSkES1JUt2mblRioELYmgTctKJIwi63zMTM37mDPvXnXxFvcHH+/Od86cO3fezNwrUlERM8RGhmE2GokZ1XE2lW7VITaVXtVbNotwR7Wp+uO1rfpC3uy/7PKcVj0jb0L1W1ztaxQLTKoesFmUMHDmsDifB1SUVE1wRFyshQMRVt+6oOMrNj3Wg9ZjTPWGTc+U1K+JnNLLDRsOhU9yQNzM7fZh0GeATQ9iP9gk2mUX910Tu9OCuNhZDhTAqgkQu646oZoXdxikQF4bmzmsmceN4GMzlgUbP1UT4LQK9zyqavbXp+IkD/xRNnOEwt9UX8X9/WivqrqivDLcEPthHoqLNUXeR+8x8B6xaRH2y3kOJMAAN8TlPxH3/lj07U9RHsAAUoMD8H+R99P7DF4Vy2xavJd0EYsl1Ws2lWlqh9lPAf92wkvlf1etsGlhFbFA7pmofdD/jkQeuCx2XfgdURvLDV5qOcHHAVEIJH9gM0M8QJyCFuck/zAxWLLsBeDjfVWXK+KSL3DAYFBc/lXVPX+dw4rDP+av8W2Gds//cA2IdbIZc1e1Je7kwncY1uVOTUaal1K7GR/7X2syMJB+Nj3h2+yz6gDFAq1iT8ieQeHUu2CdDc9T1Qs2S3BfNcfmfpGaJeyb3Bs61acoe+lrgo9FLEMUj4WlgiWa46a4DV6WcdUtNhuB56o+NjPgO+0dm43ERTYyXGKjoqJif/gLc/yg2KjRrSAAAAAASUVORK5CYII=>

[image9]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAZCAYAAAA4/K6pAAAAjElEQVR4XmNgGAXkAEZ0AWKBIxD/B+IWdAlCIJYBojEHXYIQqGSAaAxClyAEpgDxPyC2QJcgBNYD8Q8gVkKXIAbkMkCca4UuQSooYYAYFIwuQSqIYoAYlI0uQSqwY4AY1IYuQSpQAeKfQDwHXYJUIAjE+9EFBweQBmJvIjHWFCoCxOZEYk2onlFALQAA8QEYC8J6qJQAAAAASUVORK5CYII=>

[image10]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAmwAAAA4CAYAAABAFaTtAAAGC0lEQVR4Xu3dW6htVRkA4GF2sUgyKLtQSQ89SBFBEBGi4UNRdoPEMpGs6EIZVFgP5UNBaXQx6J5GSOSbUkmUWuQpsMDKG2VJFpSVGV2pKM0u42+Occ7Y/5lr7ctZZ+3N8fvgZ47xz8uaa64DY5wx5py7FAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA7hMemBMLPC0n2O+knFjgfjnRPDknAGCd7l/jhho3tbi+xndqvGPc6Aj0lBpfWRJ7yTtzYol7cmLFLigHX6selw/b7SW/yIklPlrj/Jys/psTALAbcoP0hJnckeYZZf47zuV2y3bP5eE1XpiTK/bVGv9OueNrXJtye8ETazw9JzcR/2HJtvs7AMDKnVXmG6TIPSwnjyAxKjT3vb+fE7soRj23a+47rVIc/wM5Wb0nJ/aAP+XEFhxd42Mpd7ivKQBsKhqjucb2bzW+nJNHkPjeY0P8mbbczhTa4XRF2fr9a6P4Ts/NyRXKnZfHtGWMZu01+Vy3Ku+X6wCwdosao8h/PidX4JIyHfv9rf71Gm+v8a9Wj3WPb+VeDycO5fCuVv9Pq0c5RlQeun+L5WL7PlL0vnHFHjH3u7ytTPcd/rTGz2scVQ7e7poad6fcKo2f96OhvBf9OifKdK9ddIR/VeOPNU6p8YINWxx8TXMdANZuUWMU+WNyckXi2I9K9e68Gt8c6jFl232vxpuG+oPKgX1fNeQ3E52e2C+WMe276BrspnxOr6jx0lb+Wo3X1XhljR/s32JyYTl431WJh1Hi2A+o8chW7uLetp8N9Z3alxM7FPfzXZlyvXMf+rnfOeS6fP1yHQDW6swy3xidUObzq5KPPdbPrfHtof78Mq1/S5k6J28d1nX5eJu5qmy8cX67+69SHt3plp3TsnUxWrlo/XNqvGhJbCaO++Gh/tuhfFGNTw/1nbo31R+c6lsV/4YvzckmHji5IycH+frlOgCs1e01vpWTZWqgnp2Tg5hK3CyWyQ3gWH9j2dhhG9d9o0zTgqOXlKmRf2bKLxPH/GBO7pIbc6LJ12i0bN2nyvL1hyKOu+hBlOgAPzond2CV5z73bztcXeM1OTnI55DrALBW0RA9JOX+UbY22nIocgM41t9c47pWziOAMaUVI0h96u1zNV7byvmYy2y27e/K9BLVmHY8vcaPWz4a+nBzmZ4kjOnbOFZ0DGJ5W5n2DT9py7jPLMSrL25t5Xe3ZUzbxX6xzPI5/nLI9WVMWefXUMQ59Ou3avmcRrHu5DL9JuFDbRkdo/jNQn+575Pa8rE1Xlyma9Q7+f23fVmNl7fyl8p0/H5Nb2nLU8uB7WMkNuv3RXb93/v4PS4eyl3+nrkOAGsRN1tHIxQRnaB44erfy3qe9LurTNNR/d6hWEY9Ojpnl+lG8X5DeIhp0DjPT7Z6bzxjOu435cAN9nHc2G+8/y2L0bu/1PhDW+bptzCXyx2lXM71eDVEnFt8p3jZbPestrx+yC16dcc5ZeM7xJ5aps+4tMZ7Wzmm9rLIz3UAD0Vc1z+X6br9tUydqSweJgmfbcsYvQ2vbsvwhTKdX3SEQ5RjNLVfo3hg5HGtHBZd7xhF7Ll4yKJ35LL8G0Xndvwt8/ou53MdANhlY+Mco2wfKdON/CE6l32aLTfi8SBAF52O/EqOy4Zy7BsPSRxX4xFlY6dulD9jK/blxJpEJzXEOcfI3wlDvT+5+8W27H+RYfx+8SDDd4d6iM7YD1s5niYO41T2OJI492el8kMHW/G8Gsem3E5+BwDgMIqb3OOhhOgsdL8v04t2Y7o4xAjXGQdW/7+DkjsMMWIZrxnp03pjox+jgr0Tc+2Qz+JztmPuicd1ienH8Ub+uKft42UaVevTjvFuvxgN6w8SvKFMHcx+jU5r67v+2pDx+sYUde/EfaJM09X7Wn3OP3NiifiM/Fccgg4bALBU7yRuxetzgm39qa65zlrQYQMAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABgsf8B5wNLglbTGBYAAAAASUVORK5CYII=>

[image11]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABIAAAAZCAYAAAA8CX6UAAAAsUlEQVR4XmNgGAWkgi4g/gjE/6H4OxC/QxO7DldNBIBpwgZ+MuCWwwAghYfQBaGAhwEi34AmjgEiGCAKHdElkAA+F8PBNQbCiogyiBhFxKgBKziALogE3BggavDGHix8HNDEkcFtBogaMXQJZHCTgbCTQfJ/0QXRAUgRKJ3gAiD5J+iC6ECFAaKwGV0CCOQYIHLr0CWQQSAQn2RAxMQdID4OxWehYqBsYgrTMApGwaAHAJc1Nr9vaqJpAAAAAElFTkSuQmCC>

[image12]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAoAAAAbCAYAAABFuB6DAAAAm0lEQVR4XmNgGAUDAr4C8VsgPgPEgkD8H4gvQWkWmCI3IHYGYiWoxAOYBBAcBeJ/MM4XKN3FAFGIDLqxiDH8xiL4EIsYWOA6FjGsCsOxiD1DFgB5CF1nNFSMA1nwOFTQB8pngvLD4CqgACR4C4gvQ9mgkJBCUQEFIEmQVXiBHwOm+7CCDwwQhVlALI4mhwJcGCC+DgBiRjS54QkAahspjFGixIQAAAAASUVORK5CYII=>

[image13]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADoAAAAZCAYAAABggz2wAAACGklEQVR4Xu2WO2hUQRSGjy9QUYkYIyIxXZBUAbUJaSLpUggWsbAUQRBELAyCgmAZKwsRoynShVRa2CSpQhoVkohoqWIsbAQVH/hAz++ZWc7+u3N37y6k2fngJ5zvTPbOZOfORCSTyXQy1zWfNd80Z6nXiDnNX81LzU7qgZ+aS5oDmh2aUc0bP2CjwATnXf1Cs+zqFNvEFng41FtCfbAywoDjjFSNaJMxFnXYI/ZgBq6LJbGkWSd3S2o/D/UNzX3N6epWe9zT/NIc4UYdVqV2YgAOEysCY+6QGwrew3XbLGg+aXq4UUDcSkzKR+I2vUa+L/hTzhV9TtNsFXvH3oq96GVJLSjlI4Ni/cvk9wc/4RxqnAHvNY9DjYOpKfBufdA802ymXhlSC0r5yAmx/kXye4Ofcg51n6uvBFfIIc1XzSNutEhqQSkf6Rfr49rwdAd/kzyDMYssPThgfmvucqNFUgtK+cgmsf5V8r3Bn3EO1xDT6PMrxG/2ITdK8kXqPxDuFUsCY1KnbrxLH4T6eGWEAYeboWl2ib3kT8T+ymUZl/RCj7p6u+aCq8EfzXNy/P7NiI3zc9stNgbXYGlw3K9oXotNqgx46HlXTwbniVttwLnh4Dyob7saB+V3VwPMkX+vJbCdP2r2cSMBriU8GLtiTfNDanfHSc1TciB+g7Ni/9NOV7f/c0xsDG4J/HxX3W6fcywymUwmk+lQ/gFW5o4VwJg3aAAAAABJRU5ErkJggg==>

[image14]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADAAAAAZCAYAAAB3oa15AAABZElEQVR4Xu2WvyuGURTHD4NYZFH+BcqkjAajxabMFsVsszH5F7yZETFRVhYMlJhEoQxKUSiK73HfW/f9es51n+fFoPupz3C/53afe95f5xXJZDK/ySx8gE9wgmopjMBlDv+KU7gTrE/gXrC2mIGP8L3uSmO5mEEOmqRT3MMZzbo4jJDcQBu8hLuwpbFUiSOxG1jkMEJyA55WeAwvYAfVyuDffsbKLUo3ELIl7gvYw4UErItauUVTDXiW4Bvs50IE66JWbqF7Vzmsyry4A4e4UIB1USu30L1rHFZlStyB41wowLqolVvo3nUOyzIn7qBhLkTwv+OMZmccRtD9GxymUoOvsJcLCYyJ3cBAsG4X985a6P5NDr9jG97Dbi6URB8+GawX6lmI/0j1Ua7obNJayvT+HF6H8Fzcq/IT6BzRC+yLmy0v8nVIjsIDyqbhHbyBV/Aa3sLncBOjfyX48Ewmk8n8fz4AA1Bdgv8x+nYAAAAASUVORK5CYII=>
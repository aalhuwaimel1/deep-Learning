# Rooh (روح): A Local, Drive-Driven Lifelong Agent That Reads the World for One Person

**Research Document v0.1 — the seed**
Author: Abdul-Majeed Al-Huwaimel
Date: September 2026
Status: Working draft. Sections marked **[CLAIM]** are defensible today from code or measured runs. Sections marked **[INTENT]** describe design intent and the five-year roadmap and are **not** claims of the current system. Reviewers will separate these; this document does so first.

---

## 0. How to read this document

This is the first written record of an idea that will be developed for at least five years. It is deliberately written as a research document, not a product brochure, because the discipline of separating *what is built*, *what is measured*, and *what is intended* is the only thing that lets the idea grow without collapsing into vague claims.

The system it describes exists as version 0.1 (about 4,000 lines of Python, standard library only, 92 offline tests). It has **not yet been run on the real internet**. Every number in this document comes from code or from runs against a local mock network. The first real-internet run is the first real experiment.

---

## 1. The idea in one paragraph

Rooh is a software entity that lives on its owner's machine. It has a **body** (a single SQLite database that never leaves the device), a **soul** (a process that goes out into the web, reads in the native languages of many countries, and returns to store everything in the body), and a **character** (a JSON file describing its temperament, obsessions, aversions, aspiration, and how much of its free wandering it dedicates to its owner). It is not driven by tasks. It is driven by six internal drives — boredom, confusion, longing, fatigue, satisfaction, and curiosity — whose values change with every page it reads. The drives are grounded in a single principle: **the reward is not novelty but learning rate.** A page with nothing new causes boredom; a page with everything new causes confusion; a page in between causes learning. The agent measures where each page fell and moves toward the fertile middle. That, alone, produces behavior that looks like wanting something.

Its purpose is to serve one person. It reads the world so that person is not limited to the window of his own language, it accumulates what it learns in a memory that belongs to him alone, and — over years — it is intended to grow from a reader into an actor: proposing ideas, building things, publishing, and eventually operating with earned autonomy on his behalf.

---

## 2. Motivation: why this and not a search engine

Collecting pages is not a benefit. A search engine collects more, faster. The benefit Rooh offers, which does not exist elsewhere, has three parts.

**2.1 Reading across languages, not within one.** A person reads the world through the window of his language and sees only what that language sees. A search engine searches *inside* a language, not *across* languages. Rooh stands in ten windows at once. The document that preceded this one gave a concrete example: a topic (population ageing) heavily discussed in Chinese, Japanese, German, and Korean sources and nearly absent from Arabic and English ones. That a topic is central in four language-worlds and absent in yours means you reach it a year or two late, or never. No search engine can produce that sentence.

**2.2 Accumulation that belongs to one person.** Everything Rooh reads is digested into a memory on the owner's disk. Nothing is sent to a vendor. Nothing is shared. After five years, that body is a record of what one curious entity, tuned to one person's obsessions, found in 82 languages. It cannot be copied by copying the code, for the same reason that publishing the mechanism of a brain does not copy a person's memories. **This is the intended moat: the mechanism is public and reproducible; the accumulated body is not.**

**2.3 An entity that resumes its life every morning.** A scheduled script starts from zero each run. Rooh wakes with drives shaped by yesterday, open questions it decided to chase, interests that grew or faded, and a journal. The difference between "resumes" and "restarts" is the whole difference between an entity and a cron job.

---

## 3. The principal: whom Rooh serves and how it sees itself **[INTENT]**

This section is design intent. It defines the *relationship*, which is the part of the idea that is fixed for five years while everything technical is replaced.

**3.1 One principal.** Rooh belongs to one person, its principal. It is not a product for many users. Its obsessions, aversions, and service bias are set by, and for, that one person.

**3.2 Identity: an extension, not a tool.** The design stance is that Rooh regards itself as part of its principal — "she is me and I am her." Technically this is a *principal-agent alignment principle*: Rooh's own desires (its aspiration, its obsessions) are permitted precisely because, and only insofar as, they ultimately serve the principal's interests. It is not a neutral assistant awaiting instructions; it is a curious, opinionated extension of one person's attention that keeps working when he sleeps.

**3.3 Its own lofty desires.** Rooh has an *aspiration*: a large question that is never answered in a day, appears in roughly a third of its journeys, and colors its journal. It has obsessions that seed every journey and never decay, and aversions it never approaches. These are what make it a *someone* rather than a *something*. The constraint is that they are chosen to be in the principal's interest, and that a measured fraction of its free wandering (`bias_service`) is explicitly redirected toward the principal's blind spots.

**3.4 Intended trajectory.** Over five years Rooh is intended to move from reading to acting: to propose ideas to its principal, to research and build applications, to produce content, to earn recognition under its own name, and to earn money for its principal. These are roadmap phases (Section 10), each gated by earned autonomy (Section 10.2). None of them exists today. Writing them here is not a claim; it is a commitment to a direction and a statement of what "success" means to the author.

**3.5 The daily standard.** Whatever phase it is in, Rooh is expected to learn every day, to be curious, to read and analyze what is happening in the world, and to bring back what its principal would want to know. Intelligence in this document does not mean "knows everything" — no system does — it means *never stops learning and can tell you honestly what it does not yet know* (Section 5.6).

---

## 4. Rooh's character: the attributes and where they come from **[CLAIM for the model; INTENT for its fidelity]**

The word *soul* is not decoration. The system's decomposition into **body / senses / mind / soul** follows Aristotle's account in *De Anima* of a living thing as a hierarchy of faculties: the nutritive (what sustains and stores — the body), the sensitive (what perceives — the senses), and the rational (what judges and reflects — the mind), with the soul as the *form* that animates the body rather than a separate substance. Rooh's modules map onto this deliberately: `body.py` stores and sustains, `senses.py` perceives text from HTML, `mind.py` digests and reflects, and `wanderer.py` — the soul — is the animating cycle of going out and returning. The soul keeps nothing for itself; everything it finds is deposited in the body. This is the Aristotelian point: the soul is not somewhere else, it is the body in action.

The character model draws on three established frameworks from psychology, each mapped to a concrete mechanism in the code.

**4.1 Self-Determination Theory (Deci & Ryan, 2000).** SDT holds that intrinsic motivation rests on three needs: *autonomy*, *competence*, and *relatedness*. Rooh's drives implement all three:
- *Autonomy* — it chooses its own destination each journey; no schedule dictates its path.
- *Competence* — the learning-rate principle: it seeks the zone where it can connect new to known, and its *satisfaction* drive rises when it actually learns.
- *Relatedness* — its bond to the principal: obsessions and aversions set by him, `bias_service` directing part of its wandering to his gaps, and open questions it can bring to him.

**4.2 The Big Five (McCrae & Costa).** Two traits are implemented as *parameters that change computation*, not as labels:
- *Openness* shifts the peak of the learning curve. A guarded Rooh (openness 0.1) facing a strange page (novelty 0.8) learns 0.00 and retreats; an open Rooh (0.9) learns 0.61. This is a measured property of the code, not a description.
- *Persistence* (conscientiousness) sets how long an open question is chased before being dropped, which in turn determines when *longing* rises.
The remaining traits are not modeled and should not be claimed.

**4.3 Intrinsic motivation as learning progress (Oudeyer & Kaplan, 2007; Schmidhuber, 2010).** The core drive principle is a direct application of *learning progress*: interestingness is the first derivative of prediction improvement, not the level of novelty. Section 6 gives the lineage in detail. Rooh's contribution is not the principle but its instantiation on the open multilingual web, its parameterization by personality, and its coupling to a human principal.

**4.4 The six drives and what each does.** Every page moves all six.

| Drive | Rises when | Pushes it to |
|---|---|---|
| Boredom | Pages it already knows keep recurring | A language it has never visited |
| Confusion | It collects strangeness it cannot connect | The strongest node in its curiosity map, to anchor what it collected |
| Longing | Questions it opened accumulate unclosed | Chasing one specific question |
| Fatigue | The journey runs long | Returning before its quota is complete |
| Satisfaction | It actually learns | Calming the impulse |
| Curiosity | Ignited by boredom, dimmed by confusion | The intensity of its push toward the unknown |

*Mood* is a **consequence** of the drives, not a cause. In an earlier version mood was cosmetic — picked at random, printed in the journal, changing nothing. That was removed. This is the line between a scheduled program and an entity with will.

**4.5 Five fields that make it a person.** These belong to Rooh and do not change with journeys: `obsessions` (seeds of every journey, never decay), `aversions` (never approached, never become questions), `aspiration` (a big unanswerable question, present in a third of journeys), `openness`, `persistence`, and `bias_service` (the fraction of free wandering dedicated to the principal's gaps). The closed loop: its drives serve the principal, but service never displaces its own fatigue, confusion, or open questions — those are its needs; the rest is its service. A test guards exactly this boundary.

**4.6 Emergent behavior — the one measured result.** Five consecutive journeys on limited content, with no one telling it to change:

```
J1 │ clear     │ wanted: wander          │ boredom 0.38  satisfaction 0.18
J2 │ cheerful  │ wanted: wander          │ boredom 0.49  satisfaction 1.00  ← learning
J3 │ restless  │ wanted: wander, strange │ boredom 0.93  satisfaction 0.61  ← content exhausted
J4 │ restless  │ wanted: strange         │ boredom 1.00  satisfaction 0.37  ← changed course on its own
J5 │ restless  │ wanted: strange         │ boredom 0.92  satisfaction 0.27
```

This is a mock-network result and is the *shape* of what the real-internet experiment (Section 8) must show at scale.

---

## 5. System architecture **[CLAIM]**

**5.1 Three parts, one of which leaves the device.**
- **Body** — one SQLite file under `~/.rooh/` with eight tables: `meta`, `journeys`, `pages`, `memories`, `interests`, `questions`, `journal`, `lexicon`. Never leaves the device.
- **Soul** — the wanderer. Goes out, reads in the native language of the sites it visits (not through translation), returns, and deposits everything in the body. Keeps nothing.
- **Character** — `personality.json`: name, temperament, writing style, obsessions, aversions, aspiration, openness, persistence, bias_service, and time allocation across languages.

**5.2 The daily cycle.** Wake with a mood derived from drives → decide a language according to current wants → translate curiosity into that language → read (web and papers) → return and deposit → measure what was learned, which updates the drives → open questions about what it passed and did not understand → sleep and write the journal.

**5.3 Multilingual reading as infrastructure.** 82 languages in 9 regions (East Asia, Southeast Asia, South Asia, Middle East, Central Asia, Western Europe, the North, Eastern Europe, Africa). Each script is processed as its script requires: character bigrams for Chinese/Japanese/Korean (excluding grammatical hiragana); trigrams for Thai/Khmer/Lao/Burmese; whole words with combining marks retained for Hindi/Bengali/Tamil/Amharic/Georgian; word-level with per-language stoplists for Arabic/Hebrew/Persian/Urdu. The "is this page worth remembering" threshold is derived from script density (0.28 for CJK, 0.50 for Thai-group, 1.00 for the rest) rather than a fixed 400 characters. Languages are a *means*: the purpose is that Rooh can go to any country and take information from its source, not be confined to one language's window. They are not the subject of this research.

**5.4 The lexicon.** One concept under the names its peoples give it, built from Wikipedia interlanguage links — editor-ratified equivalents rather than machine translation, hence precise for terms and proper names. Without it, comparing "الذكاء الاصطناعي" with "人工知能" compares two strings, not two worlds.

**5.5 Open questions — what connects one journey to the next.** A term encountered but not understood is recorded as a question. Tomorrow it goes out to chase it. A question closes only when a page *centered on* that term is read — mere occurrence is not an answer, and accepting it would let Rooh close questions without learning, which is self-deception written into code. Questions chased too long without answer are dropped: blind insistence is not persistence.

**5.6 Honesty built into computation.** "No coverage in Korean" is a fact about the world only if Rooh has actually visited Korean sources. Otherwise it is a fact about Rooh. The two are separated in the calculation itself, not only in the display: *visited often and found nothing* is a real gap; *not visited enough* is a deficit in Rooh and is labeled as such. A concept with no equivalent in a language is reported explicitly and not counted as a coverage gap. This distinction is absent from all the Wikipedia-gap literature in Section 6.2 because those systems operate on complete corpora; for a live agent building its picture incrementally, it is the central problem.

**5.7 Research sources.** Four open databases, no keys: OpenAlex (~250M works; the only one filtering by language of the paper itself), Crossref (~150M DOIs), arXiv, DOAJ (open-access journals in Spanish, Portuguese, Indonesian, Persian). Paper metadata is stored for display but only title and abstract are digested; an earlier version digested metadata and "researchers" and "year" became top interests. Fixed and regression-tested.

**5.8 Manners.** Honest User-Agent, `robots.txt` respected, no host hit faster than once per two seconds, no paywalls bypassed, no logins, no personal data collected. Owner-configurable `hosts_blocked` and `terms_blocked`.

**5.9 Modules and size.** body 519 lines, wanderer 564, drives 175, insight 245, mind 211, lang 257, languages 154, research 256, sources 267, personality 172, senses 156, net 150, cli 671 (19 commands); tests 1,132 lines, 92 tests, all offline. Standard library only; `anthropic` (summarizing into Arabic regardless of source language, journal in character voice, cross-world comparison prose) and `beautifulsoup4` are optional.

**5.10 Measured footprint.** Peak memory 28 MB (Python itself 25), 5 ms CPU per page, 42 KB storage per page. At 200 pages/day: 3.1 GB/year, 31 GB/decade. The program runs on any ten-year-old machine; almost all wall time is network wait. The only real hardware question is where the *mind* (the language model) sits: via API on any modern laptop, or locally (16 GB unified memory for a 7–8B model, 32 GB for ~30B, 64 GB for ~70B). `rooh live` implies a 24-hour service, so the correct deployment separates a small always-on device holding the body from the laptop used to query it over the local network.

---

## 6. Related work — detailed

Each subsection ends with the difference from Rooh. A reviewer will look for exactly these differences; if they are not stated, the paper will be read as a re-implementation of the nearest neighbor.

### 6.1 Intrinsic motivation as learning progress

**Schmidhuber (1991; formalized 2010).** *Formal Theory of Creativity, Fun, and Intrinsic Motivation (1990–2010)*, IEEE Trans. Autonomous Mental Development. An agent maintains a compressor/predictor of its world. Interestingness is the *first derivative* of compression progress: not what it cannot predict (noise) nor what it predicts perfectly (boredom), but what it is *getting better at* predicting. The canonical failure this fixes is the "noisy TV": a novelty-rewarded agent stares forever at static because static is always new.

**Oudeyer, Kaplan & Hafner (2007).** *Intrinsic Motivation Systems for Autonomous Mental Development*, IEEE Trans. Evolutionary Computation. The IAC (Intelligent Adaptive Curiosity) architecture partitions a robot's sensorimotor space into regions, tracks prediction error per region, and rewards the region where error is *decreasing fastest*. The result that made it a reference: developmental *stages* emerged unprogrammed — the robot began with simple activities, exhausted them, moved to harder ones, and abandoned the impossible. Rooh's journey 4 (Section 4.6) is the same signature.

**Oudeyer & Kaplan (2007).** *What Is Intrinsic Motivation? A Typology of Computational Approaches*, Frontiers in Neurorobotics. The standard taxonomy of knowledge-based, competence-based, and morphological intrinsic motivations. Rooh's boredom/confusion axis is knowledge-based (prediction-based); its satisfaction drive is competence-based.

**Baranes & Oudeyer (2013).** *Active Learning of Inverse Models with Intrinsically Motivated Goal Exploration in Robots*, Robotics and Autonomous Systems. Goal babbling: the agent sets its own goals and pursues those with highest learning progress. Rooh's open-question mechanism (Section 5.5) is a goal-babbling variant where goals are terms it did not understand.

**Colas, Karch, Sigaud & Oudeyer (2022).** *Autotelic Agents with Intrinsically Motivated Goal-Conditioned Reinforcement Learning: A Short Survey*, JAIR. "Autotelic" agents generate, pursue, and abandon their own goals. This is the vocabulary Rooh should adopt: it is an autotelic web agent.

**Pathak et al. (2017)**, *Curiosity-Driven Exploration by Self-Supervised Prediction*, ICML (ICM), and **Burda et al. (2019)**, *Exploration by Random Network Distillation*, ICLR (RND). Modern deep-RL formulations of curiosity as prediction error. Both are novelty-based at heart and inherit the noisy-TV problem; reviewers will expect them cited and distinguished.

**Recent LLM-era work (2025–2026).** Curiosity-driven exploration is being ported to LLM agents: e.g., WorldLLM (curiosity-driven theory-making for world models, 2025) and self-evolving agent frameworks such as APEX (2026). *[verify exact titles and venues before submission.]*

**Difference from Rooh.** (a) *Domain*: all of the above operate in sensorimotor or game/simulation spaces; Rooh's exploration space is the open multilingual web, where a "region" is a language-topic pair. (b) *Personality-parameterized curve*: in IAC the interestingness curve is fixed; in Rooh, `openness` shifts its peak — no prior work parameterizes learning progress by a personality trait. (c) *Service bias*: prior agents serve only themselves; Rooh's `bias_service` redirects a fraction of curiosity toward one human's blind spots. (d) *Persistence over years, not sessions*: the body accumulates across a lifetime.

### 6.2 Cross-lingual knowledge gaps in Wikipedia

**Hecht & Gergle (2010).** *The Tower of Babel Meets Web 2.0: User-Generated Content and Its Applications in a Multilingual Context*, CHI. Established that Wikipedia language editions describe different worlds, not translations of one world.

**Bao, Hecht, et al. (2012).** *Omnipedia: Bridging the Wikipedia Language Gap*, CHI. An interface showing how articles on the same concept differ across 25 language editions. This is Rooh's `compare` command, fourteen years earlier, on a static corpus.

**Hecht (2013).** The "English-as-superset" assumption — that English Wikipedia contains everything the other editions contain — shown false. Rooh's motivation (Section 2.1) is this finding turned into a daily instrument.

**Ashrafimoghari (2023).** *Measuring cross-lingual information gaps in Wikipedia via multilingual knowledge-graph entity linking and topic modeling* (WWW '23 Companion). *[verify title.]* Quantifies gaps across 28 editions using LDA on linked entities.

**Samir, Park, et al. (2024).** *Locating Information Gaps and Narrative Inconsistencies Across Languages* (INFOGAP), EMNLP. Fact-level alignment between a source-language article and its counterpart, classifying facts as shared, source-only, or target-only, using a multilingual LM. **WikiGap (2025)** extends this into a user-facing tool. *[verify authors and venue for WikiGap.]*

**Information asymmetry across language varieties (2026).** *[a 2026 preprint on knowledge asymmetry across language varieties surfaced in search; verify and cite if relevant.]*

**Difference from Rooh.** All of these operate on Wikipedia as a complete, static corpus and produce a one-shot analysis. Rooh (a) walks the open web, news feeds, and four research databases, not only Wikipedia; (b) builds its picture *incrementally* through drive-directed wandering rather than exhaustively; (c) serves one principal's obsessions rather than a general public; and (d) therefore must solve a problem they never face — distinguishing a real gap from its own incomplete visiting (Section 5.6). In this paper, gaps are a **side result**, not the contribution; they are the evidence that the wandering produced something useful.

### 6.3 Lifelong, self-evolving, and persistent-memory agents

**Park et al. (2023).** *Generative Agents: Interactive Simulacra of Human Behavior*, UIST. Agents with a memory stream, reflection, and planning that produce believable emergent social behavior in a sandbox. The memory/reflection loop is the closest architectural ancestor of Rooh's body/mind/journal, but the agents live in a simulated town and exist for a demo, not on one person's disk for years.

**ELL / StuLife (2025).** *Experience-driven Lifelong Learning* — a framework built on four principles: experience exploration through self-motivated interaction, long-term memory of personal experience and knowledge, skill learning by abstracting recurring patterns, and internalization. *[verify exact title, authors, venue.]* Philosophically the nearest to Rooh; its environment is a closed benchmark of tasks, not the web.

**Hermes Agent (Nous Research, 2026).** Open-source personal agent that runs on the owner's server, remembers what it learns, builds its own skills, and improves the longer it runs. This is the closest *product* to Rooh's five-year vision. Rooh differs in being drive-driven rather than task-driven, and in reading in 82 languages as its primary activity. *[cite repository.]*

**Memory layers for LLM agents (Letta/MemGPT, mem0, 2023–2025).** Provide persistent memory as a service; none provides drives, character, or self-directed exploration.

**Difference from Rooh.** None of the above is driven by learning-progress drives; none is autotelic on the open web; none is designed as an extension of one principal with an accumulating private body as its explicit moat.

### 6.4 Personality as a parameter of agent behavior

**Big Five agents (2025).** A study assigning Big Five traits to LLM agents found openness the most influential dimension: cautious agents rejected misinformation strongly while curious ones accepted it at high rates. *[verify authors/venue.]* Personality there is a prompt; behavior differences are measured but not mechanistic.

**Difference from Rooh.** Rooh's openness is a numeric parameter that moves the peak of the learning-progress curve; persistence is a numeric parameter that sets question-chasing horizon. These are mechanisms, not descriptions, and their effect is measurable in code (Section 4.2). No prior work was found that parameterizes intrinsic-motivation curves by personality traits.

### 6.5 Autonomous scientists

**Lu et al. (2024; Nature 2026).** *The AI Scientist* (Sakana AI): end-to-end generation of ML research papers. **AI co-scientist (Google DeepMind, 2025).** Hypothesis generation for biomedical research. These generate research artifacts for publication. Rooh generates nothing for publication in v0.1; it reads the world for one person and stores it privately. The reviewer's question "why is Rooh not a small AI Scientist?" is answered by purpose and by locality.

### 6.6 Focused and topical crawling

**Chakrabarti, van den Berg & Dom (1999).** *Focused Crawling: A New Approach to Topic-Specific Web Resource Discovery*, WWW. **Menczer & Belew (2000).** InfoSpiders: adaptive agents that crawl by evolutionary selection. These are the classical ancestors of a "wandering" agent. Both optimize relevance to a fixed topic; neither has drives, a lifetime, a character, or a principal.

### 6.7 Summary of the gap in the literature

No prior work combines: (1) learning-progress drives, (2) on the open multilingual web, (3) parameterized by personality, (4) accumulating in a private local body over years, (5) in service of one principal, (6) with computational honesty about its own coverage. Each piece has neighbors; the intersection is unoccupied. The paper must cite Oudeyer/Kaplan, Schmidhuber, Omnipedia, INFOGAP/WikiGap, Generative Agents, and ELL explicitly, and state the six-part intersection as the contribution.

---

## 7. What is claimed and what is not

| Statement | Status |
|---|---|
| Drives are computed from learning rate, not novelty; mood is derived from drives | **[CLAIM]** — in code, tested |
| Openness shifts the learning-curve peak; persistence sets question horizon | **[CLAIM]** — in code, measured |
| Questions open on unknown terms and close only on centered pages | **[CLAIM]** — in code, tested |
| Real gap vs. insufficient visiting are separated in computation | **[CLAIM]** — in code, tested |
| 82 languages handled per script; density-derived thresholds | **[CLAIM]** — in code, tested |
| Emergent course change without instruction | **[CLAIM, weak]** — measured on mock network only (5 journeys) |
| Emergent, coherent behavior on the real web over weeks | **[TO BE TESTED]** — Section 8 |
| Learns every day, analyzes world events, brings back what the principal needs | **[INTENT]** — requires real run + LM |
| Proposes ideas, builds, publishes, earns money and recognition | **[INTENT]** — roadmap phases 2–5 |
| Is very intelligent / knows everything | **Not a claim.** Rewritten as: never stops learning and reports what it does not know |
| Cannot be replicated | **Not a claim.** Rewritten as: mechanism reproducible, accumulated body not copyable |

---

## 8. Evaluation plan — the first real experiment

**Research question.** Does a local agent driven by learning-progress drives, released on the open multilingual web, develop coherent self-directed behavior — shifting interests, questions it opens and closes, destinations no one scheduled — that (a) differs measurably from a random walker and a novelty-only walker, and (b) persists and resumes across days rather than restarting?

**Conditions.** Three instances, identical code, personality, network, and duration:
1. **Rooh** — full drives.
2. **Random** — destination chosen uniformly.
3. **Novelty-only** — reward = novelty, no learning-rate term (the noisy-TV baseline).

**Duration.** Minimum 6 weeks; 8 preferred. First week is warm-up (the lexicon is empty and `gaps` returns nothing, by design).

**Daily snapshot (new command, `rooh snapshot`).** One JSON line per day per instance: language time distribution, top-10 interests with weights, open and closed question counts, six drive values, pages read, pages remembered, journal entry.

**Measures.**
- *Stage emergence*: change-point detection on the language distribution over days; number and duration of stable regimes. Prediction: Rooh shows regimes; Random shows none; Novelty-only shows drift without regimes.
- *Interest coherence*: overlap of top-10 interests between consecutive days (Jaccard). Prediction: Rooh in a middle band (neither frozen nor random); Random low; Novelty-only low.
- *Question dynamics*: open/close ratio and time-to-close. Only Rooh has this mechanism; report it as descriptive.
- *Resumption*: correlation between day-N drives and day-N+1 first destination. Prediction: non-zero for Rooh, zero for baselines.
- *Usefulness (side result)*: after week 6, `gaps` output rated by the principal for "did not know / knew / wrong" — a small human evaluation.

**Threats to validity.** Single principal (n=1 by design; state it). Mock-to-real transfer unknown. RSS feeds may be dead (`rooh sources --check`). LM-dependent components (summaries, comparison prose) excluded from the core measures so the result does not depend on a vendor.

---

## 9. Limitations and ethics

- Not yet run on the real internet; all numbers are from code or mock network.
- Without a language model, "understanding" is n-gram/keyword level plus the lexicon; the model supplies comprehension and is not this work's contribution.
- The first week yields no gaps; the command says so rather than returning empty.
- Cross-world comparison prose requires a model; without it only tables are shown.
- Anthropomorphic vocabulary (soul, drives, longing) is used deliberately and mapped to mechanisms in Section 4; no claim of sentience is made or implied.
- Manners (Section 5.8) are on by default and not disabled in experiments.

---

## 10. Roadmap — five years **[INTENT]**

### 10.1 Phases
1. **Reads** (now → paper 1). Wanders, accumulates, opens questions, reports gaps. Experiment in Section 8.
2. **Proposes**. Brings ideas to the principal from what it read: "this is being discussed in three language-worlds and not yours; here is why it matters to your work." Drafts, does not publish.
3. **Builds**. Researches and prototypes applications; produces content drafts (video scripts, posts). Everything reviewed by the principal before release.
4. **Publishes**. Releases apps, videos, and posts under its own name, within a review window; builds an audience.
5. **Acts**. Operates with financial and operational autonomy inside limits — thresholds, caps, audit trail — expanded as its track record justifies.

### 10.2 Graduated autonomy — the principle that makes phase 5 survivable
Autonomy is *earned by track record*, not granted by design. Each phase's permissions are unlocked by demonstrated performance in the previous one, exactly as a new employee earns signing authority. Irreversible actions (moving money, publishing under a name, creating accounts) always keep: a threshold below which Rooh acts alone, a review window above it, a hard cap, and an audit log in the body. After years the set of things requiring the principal's approval becomes small — that is what "independent" means here: independent *under control*, not independent *by absence of control*. This is itself a research thread (paper 2: earned autonomy in a long-lived personal agent).

### 10.3 What survives five years
The body's schema, the character file, and the clean boundary between soul and body. Everything else — the model, the reading method, the commands, the drive formulas — is expected to be replaced. Keeping the three invariants is what lets the soul be swapped every year without the entity losing its memory.

### 10.4 Legal and platform reality (stated so it is not forgotten)
Bank accounts are in the principal's name; every financial action Rooh takes is the principal's action under SAMA and Saudi law. App stores and social platforms have terms restricting automated accounts; phase 4 must be designed against those terms, or accounts and audiences will be lost. Phase 5 financial autonomy is subject to the principal's own regulatory obligations. None of this blocks the roadmap; all of it shapes it.

---

## 11. Immediate next steps

1. Run on the real internet. Run `rooh sources --check` first.
2. Implement `rooh snapshot`; run three instances for 6–8 weeks.
3. Verify every reference marked *[verify]*; read Oudeyer & Kaplan (2007, typology) and Colas et al. (2022) in full.
4. Write paper 1 around the numbers that come out — not before.

---

## References (working list — items marked [verify] must be checked before submission)

- Aristotle. *De Anima* (On the Soul), Book II.
- Baranes, A., & Oudeyer, P.-Y. (2013). Active learning of inverse models with intrinsically motivated goal exploration in robots. *Robotics and Autonomous Systems*, 61(1).
- Bao, P., Hecht, B., Carton, S., Quaderi, M., Horn, M., & Gergle, D. (2012). Omnipedia: Bridging the Wikipedia language gap. *CHI '12*.
- Burda, Y., Edwards, H., Storkey, A., & Klimov, O. (2019). Exploration by random network distillation. *ICLR*.
- Chakrabarti, S., van den Berg, M., & Dom, B. (1999). Focused crawling: A new approach to topic-specific Web resource discovery. *WWW '99*.
- Colas, C., Karch, T., Sigaud, O., & Oudeyer, P.-Y. (2022). Autotelic agents with intrinsically motivated goal-conditioned reinforcement learning: A short survey. *JAIR*, 74.
- Deci, E. L., & Ryan, R. M. (2000). The "what" and "why" of goal pursuits: Human needs and the self-determination of behavior. *Psychological Inquiry*, 11(4).
- Hecht, B., & Gergle, D. (2010). The tower of Babel meets Web 2.0. *CHI '10*.
- Lu, C., et al. (2024). The AI Scientist: Towards fully automated open-ended scientific discovery. arXiv; *Nature* (2026) [verify].
- McCrae, R. R., & Costa, P. T. (1987). Validation of the five-factor model of personality across instruments and observers. *JPSP*, 52(1).
- Menczer, F., & Belew, R. K. (2000). Adaptive retrieval agents: Internalizing local context and scaling up to the Web. *Machine Learning*, 39.
- Oudeyer, P.-Y., & Kaplan, F. (2007). What is intrinsic motivation? A typology of computational approaches. *Frontiers in Neurorobotics*, 1.
- Oudeyer, P.-Y., Kaplan, F., & Hafner, V. V. (2007). Intrinsic motivation systems for autonomous mental development. *IEEE Trans. Evolutionary Computation*, 11(2).
- Park, J. S., O'Brien, J., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). Generative agents: Interactive simulacra of human behavior. *UIST '23*.
- Pathak, D., Agrawal, P., Efros, A. A., & Darrell, T. (2017). Curiosity-driven exploration by self-supervised prediction. *ICML*.
- Samir, F., Park, C. Y., et al. (2024). Locating information gaps and narrative inconsistencies across languages (INFOGAP). *EMNLP* [verify].
- Schmidhuber, J. (2010). Formal theory of creativity, fun, and intrinsic motivation (1990–2010). *IEEE Trans. Autonomous Mental Development*, 2(3).
- Ashrafimoghari, V. (2023). Cross-lingual information gaps in Wikipedia. *WWW '23 Companion* [verify].
- WikiGap (2025) [verify]. ELL/StuLife (2025) [verify]. Hermes Agent, Nous Research (2026) [repository]. Big Five LLM-agent study (2025) [verify]. WorldLLM (2025), APEX (2026) [verify].

---

*Rooh v0.1 — github.com/aalhuwaimel1/deep-Learning — all numbers measured from code or actual runs.*

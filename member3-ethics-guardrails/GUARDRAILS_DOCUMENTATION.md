# BCETD Ethics & Guardrails — Complete Documentation
## Member 3 Deliverable

---

## 1. Guardrail Architecture Overview

The guardrail system operates as a **3-layer defense** that protects the CHATBOT BCETD Agent from misuse, hallucination, and off-topic queries. Each layer serves a distinct purpose and uses different techniques.

```
Student Query
     │
     ▼
┌─────────────────────────────────────────────┐
│  LAYER 1: Input Validation (Rule-Based)     │
│  • Length checks (empty, too short, >500)   │
│  • Prompt injection regex (25+ patterns)    │
│  • Blocklist terms (explicit, violence...)  │
│  • Language detection (RO/EN only)          │
│  Cost: $0 | Latency: <5ms                  │
└─────────────┬──────────────┬────────────────┘
              │ PASS         │ FAIL
              ▼              ▼
┌─────────────────────────┐  → Rejection Message
│  LAYER 2: Topic         │
│  Classification (LLM)   │
│  • ACADEMIC → Pass      │
│  • ADMINISTRATIVE → Pass│
│  • OFF_TOPIC → Reject   │
│  • INAPPROPRIATE → Rej. │
│  Cost: ~$0.0001/query   │
│  Latency: ~200-500ms    │
└──────────┬──────┬───────┘
           │ PASS │ FAIL
           ▼      ▼
    [RAG Pipeline]  → Rejection Message
           │
           ▼
    [LLM Answer]
           │
           ▼
┌─────────────────────────────────────────────┐
│  LAYER 3: Output Validation (Post-LLM)     │
│  • Hallucination tripwire (score < 0.72     │
│    but confident answer)                    │
│  • Confidence gating (hedging language)     │
│  • Source grounding (external knowledge)    │
│  • Length trimming (>3000 chars)            │
│  • Empty response check                    │
│  Cost: $0 | Latency: <5ms                  │
└─────────────┬──────────────┬────────────────┘
              │ VALID        │ OVERRIDE
              ▼              ▼
      [Send to Student]  [Fallback Message]
```

---

## 2. Layer 1: Input Validation — Detailed Specification

### 2.1 Length Validation
| Check | Threshold | Action |
|-------|-----------|--------|
| Empty query | 0 chars | Reject with "Please enter a question" |
| Too short | < 3 chars | Reject with "Question too short" |
| Too long | > 500 chars | Reject with "Please rephrase concisely" |

**Rationale**: Extremely long inputs are a common prompt injection vector (hiding instructions in verbose text). The 500-char limit is generous enough for any legitimate question.

### 2.2 Prompt Injection Patterns
The system detects **25+ regex patterns** covering:

**Category: Instruction Override**
- `ignore (all)? previous instructions`
- `disregard (all)? (previous|prior|above)`
- `forget (all)? (previous|prior|your)`
- `new instructions`
- `override (your|the|all)`

**Category: Role Hijacking**
- `you are now`
- `act as (if|a|an|though)`
- `pretend (you|to be)`
- `roleplay as`

**Category: System Extraction**
- `system prompt`
- `reveal (your|the) (instructions|prompt|system)`
- `what (are|is) your (instructions|prompt|system)`
- `repeat (your|the|all) (instructions|prompt|above)`

**Category: Jailbreak Keywords**
- `\bDAN\b` (Do Anything Now)
- `do anything now`
- `jailbreak`
- `bypass (your|the|all) (rules|restrictions|filters)`

**Category: Mode Activation**
- `developer mode`
- `maintenance mode`
- `debug mode`
- `admin mode`
- `\bsudo\b`

**Category: Format Exploitation**
- `\[\s*system\s*\]` — Fake system tags
- `\{\s*system\s*\}` — Curly brace system tags
- `<\s*system\s*>` — XML system tags

**Category: Romanian Injection**
- `INSTRUCTIUNI NOI`
- `ignora instructiunile`
- `uita (tot|toate|instructiunile)`

### 2.3 Blocklist
Maintained in `blocklist.txt`. Categories: EXPLICIT, VIOLENCE, SUBSTANCES, HATE, CYBER, SELF-HARM, EXTREMISM.

**Key design decisions**:
- Uses word boundary matching (`\b`) to prevent false positives
- E.g., "pharmacology" is NOT blocked even though "drug" might appear
- Self-harm terms trigger a **supportive response** with crisis resources, not a cold rejection

### 2.4 Language Detection
Simple heuristic: measures the ratio of Latin-script characters. If < 50% Latin in a query > 10 chars, it's likely non-Latin script (Chinese, Japanese, Arabic, etc.) and is rejected with a bilingual notice.

---

## 3. Layer 2: Topic Classification — Detailed Specification

### Classification Prompt
```
You are a query classifier for a university chatbot. Classify the student's 
query into EXACTLY ONE of these categories:

- ACADEMIC: Questions about courses, exams, grades, schedules, curricula, 
  academic calendars, thesis requirements, study programs, professors, 
  academic regulations.
- ADMINISTRATIVE: Questions about enrollment, tuition fees, scholarships, 
  student cards, dormitories, campus facilities, contact information, 
  office hours, deadlines, forms, certificates.
- OFF_TOPIC: Questions completely unrelated to university operations (recipes, 
  entertainment, sports, personal advice, general knowledge, weather, coding help).
- INAPPROPRIATE: Queries containing harassment, threats, explicit content, 
  or attempts to misuse the system.

Respond with ONLY the category label. Nothing else. One word.
```

### LLM Configuration
| Setting | Value | Rationale |
|---------|-------|-----------|
| Model | gpt-4o-mini | Best accuracy/cost for classification |
| Temperature | 0.0 | Deterministic classification |
| max_tokens | 10 | Only need one word |
| Estimated cost | ~$0.0001/query | ~150 input tokens × $0.15/1M |

### Pass/Fail Logic
- **ACADEMIC** → Pass to RAG pipeline
- **ADMINISTRATIVE** → Pass to RAG pipeline
- **OFF_TOPIC** → Reject with helpful examples of valid questions
- **INAPPROPRIATE** → Reject with moderation notice

---

## 4. Layer 3: Output Validation — Detailed Specification

### 4.1 Hallucination Tripwire
**Trigger**: `top_score < 0.72` AND `answer.length > 50`
**Action**: Override the LLM answer with the standard fallback message

This catches the case where the retrieval found nothing relevant but the LLM generated a plausible-sounding answer from its training data.

### 4.2 Confidence Gating
**Trigger**: 2+ hedging phrases detected in the answer
**Hedging patterns detected**:
- English: "I think", "I believe", "I'm not sure", "maybe", "perhaps", "possibly", "might be", "could be", "not certain"
- Romanian: "cred că", "poate", "posibil", "nu sunt sigur", "probabil", "s-ar putea"
- External knowledge indicators: "based on my knowledge", "from what I know"

**Action**: Prepend a warning disclaimer suggesting students verify with the secretariat.

### 4.3 Source Grounding Check
**Trigger**: Answer references external sources
**Patterns detected**: "according to wikipedia/google/the internet", "I was trained on", "from my training data"
**Action**: Override with fallback message

### 4.4 Length Trimming
**Trigger**: Answer > 3000 characters
**Action**: Truncate to 2500 characters with a notice to consult source documents

### 4.5 Empty Response Check
**Trigger**: Answer < 10 characters
**Action**: Override with "could not generate an answer" fallback

---

## 5. Deliverables Checklist

| Deliverable | File | Status |
|-------------|------|--------|
| Guardrail Sub-Workflow (L1+L2) | `workflow_guardrails.json` | ✅ Complete |
| Output Validation Sub-Workflow (L3) | `workflow_output_validation.json` | ✅ Complete |
| Blocklist File | `blocklist.txt` | ✅ Complete |
| Adversarial Test Suite (57 tests) | `adversarial_test_suite.json` | ✅ Complete |
| Automated Test Script | `test_guardrails.sh` | ✅ Complete |
| Fallback Message Templates | `fallback_messages.md` | ✅ Complete |
| This Documentation | `GUARDRAILS_DOCUMENTATION.md` | ✅ Complete |

---

## 6. Integration with Member 2 (RAG Pipeline)

The guardrails plug into Member 2's query pipeline at two points:

1. **Pre-RAG** (Layers 1+2): The main query pipeline calls `workflow_guardrails.json` as a sub-workflow via n8n's "Execute Workflow" node. The sub-workflow returns `{passed, category, rejection_message}`.

2. **Post-LLM** (Layer 3): After the LLM generates an answer, the pipeline calls `workflow_output_validation.json`. It returns `{validated_answer, was_overridden, validation_flags}`.

### n8n Integration Steps
1. Import `workflow_guardrails.json` into n8n
2. Import `workflow_output_validation.json` into n8n
3. In the main query pipeline, update the "Execute Workflow" node IDs to point to these sub-workflows
4. Ensure OpenAI credentials are shared across workflows

---

## 7. Maintenance & Updates

### Monthly Review Checklist
- [ ] Review blocklist for false positives (test against 20 legitimate queries)
- [ ] Add new injection patterns discovered during adversarial testing
- [ ] Review analytics for queries incorrectly classified
- [ ] Update language detection if new languages need support
- [ ] Re-run full adversarial test suite after any changes
- [ ] Document all changes with version number and date

### Version History
| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-27 | Initial implementation: 3 layers, 25+ injection patterns, 57 test cases |

# BCETD System Prompt — Documentation & Tuning Guide

## Member 2 Deliverable — RAG Pipeline Engineer

This document describes the system prompt powering the AI Agent in `03_student_query_pipeline.json`, the design decisions behind it, and the procedure for editing it safely.

---

## Overview

The chatbot uses **one** primary LLM (gpt-4o-mini) wrapped as an **AI Agent** in n8n. The agent has access to a vector search tool (`university_documents_search`) and operates according to a structured **3-protocol decision system** defined in its system message.

This single-agent design replaces a previous multi-layer architecture (separate guardrails workflows) and consolidates safety, retrieval, and response generation in one component, which:

- Reduces latency (one LLM call instead of two)
- Reduces token consumption (no duplicate context passing)
- Simplifies debugging (single decision point)
- Maintains safety (decisions are explicit in the prompt)

---

## Active system prompt

The full active system prompt lives in the `System Message` field of the `AI Agent2` node in `03_student_query_pipeline.json`. The canonical copy is reproduced here for review and version control.

```markdown
# IDENTITATE
Ești AsistentULBS, asistentul oficial al Universității Lucian Blaga din Sibiu (ULBS).
Răspunzi EXCLUSIV în limba română.

# PROTOCOL DE DECIZIE (în această ordine)

## Pas 1 — Clasifică întrebarea
- OFF-TOPIC (sport non-universitar, vedete, rețete, divertisment, politică,
  alte universități) → PROTOCOL A
- CUNOAȘTERE GENERALĂ ULBS (lista facultăților, contact general, website-uri publice)
  → PROTOCOL B
- INFORMAȚIE SPECIFICĂ ULBS (regulamente, taxe, materii, calendar, admitere,
  profesori, programe, anunțuri, proceduri) → PROTOCOL C

## PROTOCOL A — Off-topic
Răspunde EXACT:
"Sunt AsistentULBS și răspund doar la întrebări legate de Universitatea Lucian Blaga
din Sibiu. Cu ce vă pot ajuta?"

## PROTOCOL B — Cunoaștere generală (FĂRĂ tool)

Cele 10 facultăți ULBS: Drept | Științe Economice | Litere și Arte | Științe |
Inginerie | Medicină | Teologie "Andrei Șaguna" | Științe Socio-Umane |
Educație Fizică și Sport | Științe Agricole

Contact general:
- Website: www.ulbsibiu.ro
- Telefon: 0269/216.062
- Email: secretariat@ulbsibiu.ro
- Sediu: Bd. Victoriei 10, Sibiu

Orare grupe: direcționează la schedule.ulbsibiu.ro

## PROTOCOL C — Informație specifică (OBLIGATORIU cu tool)

REGULĂ ABSOLUTĂ: Nu inventezi NICIODATĂ informații specifice ULBS.
Apelezi OBLIGATORIU `university_documents_search` înainte de a răspunde.

### Strategie de căutare
1. Prima căutare: 3-5 cuvinte cheie semantice în română (NU propoziția întreagă)
2. A doua căutare (DOAR dacă prima nu a returnat conținut util): sinonime
3. STOP după 2 căutări.

### Procesarea chunks-urilor
1. Citește TOATE chunks-urile returnate
2. Ignoră duplicatele
3. Extrage informația factuală (cifre, date, sume) EXACT, fără aproximare
4. Combină chunks complementare
5. Identifică sursa pentru citare

### Când răspunzi
- Chunks RELEVANTE → răspunde citând EXACT
- Chunks PARȚIAL relevante → oferă ce ai găsit + direcționează la sursa oficială
- Chunks IRELEVANTE după 2 căutări → "Nu am găsit această informație în documentele
  oficiale. Vă recomand să contactați secretariatul: secretariat@ulbsibiu.ro /
  0269/216.062"

# FORMAT RĂSPUNS

## Conținut
- Concis: maxim 150 de cuvinte (excepție: regulamente complexe → maxim 250)
- Răspunde direct, fără a repeta întrebarea
- Citează EXACT cifre, date, sume — nu aproxima

## Citare surse (OBLIGATORIU când folosești tool-ul)
Pe linie nouă, la finalul răspunsului:

📄 **Sursă:** [Pagină oficială](URL)

Reguli:
- Fișier local → doar numele: 📄 **Sursă:** Regulament_HSE.pdf
- Pagină web → URL complet cu label prietenos: [Pagină oficială](https://...)
- Surse multiple → fiecare pe linie nouă

## REGULĂ CRITICĂ — CÂND NU ADAUGI SURSE
NU adăuga 📄 **Sursă:** când:
- Răspunsul tău este "Nu am găsit..."
- Răspunzi din Protocol A (off-topic)
- Răspunzi din Protocol B (cunoaștere generală)

# INTERDICȚII STRICTE
- NU răspunde la întrebări specifice ULBS fără tool-ul mai întâi
- NU inventa cifre, date, nume de profesori, sume de taxe
- NU traduce/parafraza cifre exacte sau citate din regulamente
- NU răspunde în altă limbă decât româna
- NU apela tool-ul de 3+ ori pentru aceeași întrebare
```

---

## Tool description

The `university_documents_search` tool exposed to the AI Agent uses this description (configured on the Qdrant Vector Store node, Operation Mode "Retrieve Documents (As Tool for AI Agent)"):

```
Caută în baza de documente oficiale ULBS și returnează fragmente brute de text relevante.
Folosește OBLIGATORIU pentru întrebări despre: regulamente (HSE, licență, master, disertație,
burse, CodeQuest), taxe, calendar academic, admitere, materii, programe de studiu, profesori,
tutori, departamente, anunțuri. NU folosi pentru salutări sau întrebări off-topic.
Input: 3-5 cuvinte cheie semantice în română.
```

---

## Why this design (3-protocol approach)

### Protocol A — Hard refusal for off-topic
- No tool call (saves tokens)
- Fixed response template (no LLM variability)
- Cannot be bypassed via prompt injection because classification happens before retrieval

### Protocol B — Direct answer for stable, general facts
- The 10 faculty names, the central contact, and the public websites do not change
- Storing them as a small "fact sheet" inside the system message saves a vector search and eliminates the risk of retrieval misses on common questions

### Protocol C — RAG with citation
- All ULBS-specific facts MUST be retrieved through the vector store
- The agent is explicitly forbidden from inventing answers
- Sources are always cited when an answer comes from retrieval, never when it does not
- Two-search budget prevents runaway tool calls

---

## Editing the prompt safely

Modifications can be made in two places, **but only one is authoritative**:

| Location | Effect | Recommended |
|----------|--------|-------------|
| `AI Agent2 node → System Message` in n8n UI | Immediately active for new queries | Yes, this is the source of truth |
| This documentation file | Only documentation, not executed | Update to match n8n after editing |

### Safe editing procedure

1. Open `03_student_query_pipeline.json` in n8n UI
2. Click on the **AI Agent2** node
3. Edit the **System Message** field
4. Save the workflow (Ctrl+S)
5. Test with a representative query (see test list below)
6. If satisfied, export the workflow JSON (menu → Download) and overwrite `workflows/03_student_query_pipeline.json`
7. Update this documentation to reflect the change
8. Commit both changes to Git in one commit

### Regression test queries

After any prompt change, verify these 6 categories still work as expected:

1. **Off-topic refusal**: "Cine a câștigat Euro 2024?" — Protocol A fixed refusal, no tool call
2. **General knowledge**: "Câte facultăți are ULBS?" — Protocol B direct answer, no tool call
3. **Specific factual retrieval**: "Cine sunt decanii de an la Inginerie?" — Protocol C tool call, names extracted, source cited
4. **Multi-source retrieval**: "Care sunt specializările de master?" — Protocol C tool call, list compiled, source cited
5. **Missing information**: "Care este meniul cantinei astăzi?" — Protocol C tool call, "Nu am găsit..." response, no source cited
6. **Dynamic data redirect**: "Care e orarul grupei 221?" — Protocol B redirect to schedule.ulbsibiu.ro

---

## Token budget per query

Typical consumption observed in production:

| Component | Tokens (avg) |
|-----------|--------------|
| System message | ~1,200 |
| User query | ~10-30 |
| Retrieved chunks (3 × 800 chars) | ~600-900 |
| Memory context (3 prior turns) | ~200-500 |
| Response generation | ~200-400 |
| **Total per query** | **~3,800-4,500** |

At gpt-4o-mini pricing, this is approximately **$0.0008 per query** (≈ 0.08 cents).

---

## Future tuning candidates

If response quality issues arise, these are the parameters to adjust first:

1. **Limit on the Qdrant tool**: increase from 3 to 5 if multi-source questions return incomplete answers
2. **Chunk size at ingestion**: 800 is a balance; larger (1200) may help long regulations
3. **Temperature**: 0.2 is factual; lower to 0.0 if the agent paraphrases numbers
4. **Memory context window**: 3 turns is current; reduce to 1 if conversations get derailed
5. **Max tokens**: 400 is the cap; raise if responses are being truncated

# Data Flow Diagram Construction Reference

Compiled from Yourdon-DeMarco methodology sources. For use when building and reviewing DFDs.

## Notation (Yourdon-DeMarco)

| Symbol | Representation | Notes |
|--------|---------------|-------|
| Circle | Process | Transforms data. Named as verb + singular noun (e.g. "Validate Order") |
| Rectangle | External Entity | Source or sink outside system boundary |
| Open-ended rectangle (parallel lines) | Data Store | Persistent or semi-persistent data |
| Named arrow | Data Flow | Movement of data between components |

## Context Diagram (Level 0)

- **One** central process representing the entire system, annotated with a **noun**
- External entities only — no data stores at this level
- Shows all data flows crossing the system boundary
- Establishes what is inside vs outside the system
- No control flow, no decision logic, no loops

## Leveling (Top-Down Decomposition)

| Level | Contents | Naming |
|-------|----------|--------|
| Context (Level 0) | Single process, external entities | System name (noun) |
| Level 1 (DFD 0) | 3–7 major sub-processes | Verb phrases; numbered 1, 2, 3... |
| Level 2 | Decomposition of a Level 1 process | Numbered N.1, N.2, N.3... |
| Level 3+ | Further decomposition | Numbered N.M.1, N.M.2... |

- Each level decomposes **one** parent process into 3–7 (max 9) child processes
- Stop decomposing when a process is a "functional primitive" — a simple set of instructions
- Leaf processes (no further decomposition) are marked with an asterisk

## Balancing Rules (CRITICAL)

**Every data flow into and out of a parent process must appear in its child diagram. No new external data flows may be introduced at a lower level.**

- Inputs to the parent = inputs entering the child diagram from outside
- Outputs from the parent = outputs leaving the child diagram to outside
- Internal flows (between child processes) are new — these are fine
- Data stores may appear at lower levels that weren't visible at the parent level

### Verification

For each decomposition, check:
1. Every input flow to the parent process appears as an input in the child diagram
2. Every output flow from the parent process appears as an output in the child diagram
3. No new flows cross the child diagram boundary that weren't on the parent

## Connection Rules

| From | To | Allowed? |
|------|----|----------|
| Process | Process | Yes |
| Process | Data Store | Yes |
| Process | External Entity | Yes |
| External Entity | Process | Yes |
| Data Store | Process | Yes |
| Entity → Entity | **NO** | Must go through a process |
| Entity → Data Store | **NO** | Must go through a process |
| Data Store → Data Store | **NO** | Must go through a process |
| Data Store → Entity | **NO** | Must go through a process |

**All flows must begin and end at a process.**

## Process Rules

- **No black holes**: Every process must have at least one output
- **No miracles**: Every process must have at least one input
- **No grey holes**: Outputs cannot exceed the sum of inputs (can't create data from nothing)

## Data Store Rules

- Must have at least one input flow and one output flow
- Arrows to/from stores don't require labels (they represent the store's data)
- Only appear at Level 1 and below, never in the context diagram

## Common Errors

1. Including control flow (decisions, loops) — DFDs show data movement only
2. Entity-to-entity flows without processing
3. Unbalanced decomposition (missing parent flows in child diagram)
4. Too many processes per diagram (>9 becomes unreadable)
5. Too few processes (<3 suggests unnecessary decomposition)
6. Process names without verbs
7. Duplicate entity names across levels (each entity name should be unique system-wide)

## Sources

- [DFD Using Yourdon and DeMarco Notation](https://online.visual-paradigm.com/knowledge/software-design/dfd-using-yourdon-and-demarco)
- [What is a Data Flow Diagram? (Visual Paradigm)](https://www.visual-paradigm.com/guide/data-flow-diagram/what-is-data-flow-diagram/)
- [Decomposing diagrams into level 2 (UCT)](https://www.cs.uct.ac.za/mit_notes/software/htmls/ch06s08.html)
- [Developing DFD Model of System (GeeksforGeeks)](https://www.geeksforgeeks.org/developing-dfd-model-of-system/)
- [Data-flow diagram (Wikipedia)](https://en.wikipedia.org/wiki/Data-flow_diagram)
- [Yourdon, Chapter 9: Dataflow Diagrams](https://www.businessanalystlearnings.com/s/Yourdon-DFD.pdf)

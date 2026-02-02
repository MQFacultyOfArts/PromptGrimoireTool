# Amendment Plan: Project 16084 - AI Ethics Longitudinal Survey

## Summary

Amendment to ethics application 16084 ("Exploring Student and Faculty use of Generative AI and Large Language Models in Classrooms and Research") to:
1. Update the research team
2. Add longitudinal survey methodology with linked responses

---

## 1. Team Changes

### Adding (Catalyst Grant Team):
| Name | Email | Role |
|------|-------|------|
| Jodie Torrington | MQ | Co-investigator, survey design and qualitative analysis |
| Vanessa Enriquez Raido | MQ | Co-investigator |
| Mark Alfano | MQ | Co-investigator |
| Ellie Meissner | Ellie.Meissner@unisq.edu.au (UniSQ) | Co-investigator (no FoRA access needed) |

### Removing:
- Albert Atkin
- Vince Hurley
- Alex McCrostie
- Jeffrey Foster
- Peter Rogers
- Greg Downey

### Remaining Team:
- Brian Ballsun-Stanton (CI)
- Amanda Head
- Maryam Khalid
- Ray Laurence
- Francesco Stolfi
- Yves-Heng Lim

**Note:** Check if Vanessa/Mark need Sponsored OneIDs for FoRA access (contact ethics.secretariat@mq.edu.au if external).

---

## 2. Methodological Change: Longitudinal Surveys

### What's Changing

**Current approach:** Anonymous surveys where responses cannot be linked to participants or across time points. Withdrawal not possible after submission.

**New approach:** Linked longitudinal surveys for the AI Locus of Control sub-project:
- Participants enter MQ ID to link start-of-semester and end-of-semester responses
- Brian (CI) holds identified data as data custodian
- De-identification occurs at end of semester
- Withdrawal possible until de-identification
- De-identified data shared with other researchers

### Justification

This directly addresses Research Question 6 from the original protocol:
> "How does student and researcher opinion around the use of these tools, their capabilities, and their risks change over time?"

The AI Locus of Control (ALoC) instrument measures changes in student attitudes across four dimensions (Agency, Expertise, Embodiment, Praxis) - requiring linked responses to detect within-person change.

### Target Population

Students in units participating in this sub-project (general framing to maintain program of study flexibility).

---

## 3. FoRA Form Changes Required

When the project is unlocked, update these HREA sections:

### Q0.1 - Purpose
Change from "New application" → "Amendment request"

### Q0.6 - Amendment Details (triggered by Q0.1)
- **Q0.6.2** - Explain changes and rationale:
  > "This amendment (1) updates the research team to reflect current personnel and adds three investigators for a Catalyst-funded sub-project, and (2) introduces a longitudinal survey methodology to address Research Question 6 regarding how attitudes toward AI change over time. The longitudinal design requires collecting MQ ID to link start-of-semester and end-of-semester responses, with de-identification occurring at semester end."

- **Q0.6.3** - Risks/inconveniences from proposed changes:
  > "The longitudinal design introduces a limited period where survey data is individually identifiable (via MQ ID). Risk is mitigated by: (1) only the CI holds identified data, (2) data stored on encrypted systems, (3) defined de-identification timeline at end of semester, (4) explicit withdrawal mechanism communicated to participants."

- **Q0.6.4** - List amended documents:
  - Protocol (tracked) - team list updated, longitudinal methodology added
  - New PICF for longitudinal survey (clean + tracked)
  - New survey instrument (questionnaire)

### Q1.9 - Project Team
- Add entries for Jodie Torrington, Vanessa Enriquez Raido, Mark Alfano, Ellie Meissner (UniSQ external)
- Remove entries for Albert Atkin, Vince Hurley, Alex McCrostie, Jeffrey Foster, Peter Rogers, Greg Downey

### Q3.3 - Identifiability of Data Collected
Original: "Re-identifiable (coded) information"
**May need to acknowledge:** "Individually identifiable information" during collection period (MQ ID), transitioning to "Non-identifiable information" after end-of-semester de-identification.

### M8.3 - Personal Identifiers
Original text states identifiers removed "as soon as possible" - update to reflect deliberate retention of MQ ID for linking until end of semester.

---

## 4. Documents to Prepare

### A. New PICF for Longitudinal Survey (tracked + clean copies)

Key consent elements:
1. **Purpose:** Measuring how attitudes toward AI change over a semester
2. **MQ ID collection:** Explain it's used to link start and end of semester responses
3. **Who sees identified data:** Only Brian Ballsun-Stanton (CI) as data custodian
4. **De-identification:** Occurs at end of semester before sharing with other researchers
5. **Withdrawal:** "You may withdraw by contacting brian.ballsun-stanton@mq.edu.au before the end-of-semester de-identification. Your linked responses will be deleted."
6. **AI interview option:** Note that survey data may be used as input to AI-conducted follow-up interview if participant opts in
7. **New researchers:** List Jodie, Vanessa, Mark plus remaining team
8. **Future use:** De-identified data may be shared with researchers with appropriate ethics approval

### B. Survey Instrument (questionnaire)
Attach: `20260120-bbs-jt-em-Survey_Instrument.pdf`
Include version date and version number.

### C. Protocol with Tracked Changes
Update `original-project-plan.tex` using LaTeX `changes` package:
- Section 2: Update team list
- Section 5.2.3 (Student Survey): Add longitudinal methodology
- Add new subsection describing ALoC instrument and linking mechanism

---

## 5. Amendment Process Steps

1. **Request unlock:** Use Correspondence function in FoRA to request project 16084 be unlocked for amendment
2. **Update Q0.1:** Change to "Amendment request"
3. **Complete Q0.6:** Fill in amendment details (see section 3 above)
4. **Update Q1.9:** Add/remove team members
5. **Update Q3.3/M8.3:** If required, adjust identifiability statements
6. **Upload documents:**
   - PICF (tracked copy + clean copy)
   - Protocol (tracked copy + clean copy)
   - Survey instrument (clean)
7. **CI sign-off:** Brian signs in Declaration section
8. **Submit:** Amendment goes to HREC review

---

## 6. Files in This Repository

| File | Purpose |
|------|---------|
| `documents/amending.txt` | MQ guidance on amendments |
| `documents/FoRA-HREA-Applicant-Guide.pdf` | Full FoRA system guide |
| `documents/Exploring Student and Faculty...txt` | Original HREA application (reference) |
| `documents/original-project-plan.tex` | Original protocol - needs tracked changes |
| `documents/2025-annual-report.tex` | Contains existing PICF templates |
| `documents/20260120-bbs-jt-em-Survey_Instrument.pdf` | New survey instrument |

---

## 7. Verification Checklist

After amendment approval:
- [ ] Team changes reflected in FoRA
- [ ] New PICF available for deployment in LimeSurvey
- [ ] Survey instrument configured with MQ ID field
- [ ] Data storage plan in place (identified data on encrypted storage, de-identified on SharePoint)
- [ ] Withdrawal process documented and communicated to research team
- [ ] New investigators have FoRA access (Sponsored OneIDs if needed)

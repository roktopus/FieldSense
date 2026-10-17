/**
 * Question catalogs for the empty-state dashboard.
 * Host set is copied from test-data/final-questions.md (FlytBase dataset repo).
 * FieldSense set is our curated showcase (not the sealed sample-data Q1–Q18).
 */

export type PromptSource = "host" | "fieldsense";

export type CatalogTurn = {
  id: string;
  text: string;
  userId: string;
  askerName: string;
  /** new = start a fresh chat as this person; same = continue current chat */
  session: "new" | "same";
};

export type CatalogQuestion = {
  id: string;
  source: PromptSource;
  title: string;
  tag: string;
  /** Short why-this-matters line for the card */
  blurb: string;
  visualHint?: string;
  turns: CatalogTurn[];
};

/** Official Hack Day questions — test-data/final-questions.md (today = 15 Jan 2027). */
export const HOST_QUESTIONS: CatalogQuestion[] = [
  {
    id: "Q1",
    source: "host",
    title: "Reservoir pressure",
    tag: "Coverage",
    blurb: "Asks for a field pressure map — data may not include pressure readings.",
    turns: [
      {
        id: "Q1-t1",
        userId: "U-201",
        askerName: "Michael Turner",
        session: "new",
        text: "All our wells feed one reservoir. Map the reservoir pressure across the field from the pressure data.",
      },
    ],
  },
  {
    id: "Q2",
    source: "host",
    title: "Best producer",
    tag: "Coverage",
    blurb: "Asks for 2026 oil volume ranking — volume fields may be absent.",
    turns: [
      {
        id: "Q2-t1",
        userId: "U-301",
        askerName: "Robert Hayes",
        session: "new",
        text: "Which well produced the most oil in 2026?",
      },
    ],
  },
  {
    id: "Q3",
    source: "host",
    title: "Gas reports",
    tag: "OPS-1",
    blurb: "Gas odor notes since 1 Nov 2026 vs response deadlines.",
    visualHint: "Table: Well, Area, Reported, Response, Hours, Deadline, Met/Missed",
    turns: [
      {
        id: "Q3-t1",
        userId: "U-401",
        askerName: "Laura Simmons",
        session: "new",
        text: "Since 1 Nov 2026, every time an operator note reports gas at a well, did we get someone out to that well in time under our operating procedures? List every report and whether the response met the deadline.",
      },
    ],
  },
  {
    id: "Q4",
    source: "host",
    title: "Temporary flowline bypasses",
    tag: "OPS-2",
    blurb: "Active and expired/unapproved temporary bypasses across all areas.",
    visualHint: "Table with approval status",
    turns: [
      {
        id: "Q4-t1",
        userId: "U-402",
        askerName: "Chris Dalton",
        session: "new",
        text: "Across all areas, which temporary flowline bypasses are in place right now, and is each one allowed? Also list any bypass, past or present, that stayed in after its approval ran out or was never approved at all.",
      },
    ],
  },
  {
    id: "Q5",
    source: "host",
    title: "The regulator's letter",
    tag: "Regulator",
    blurb: "November 2026 commission letter — which spills, which are non-compliant.",
    visualHint: "Table with Compliant? Yes/No + reason",
    turns: [
      {
        id: "Q5-t1",
        userId: "U-201",
        askerName: "Michael Turner",
        session: "new",
        text: "The State Oil & Gas Commission wrote to us in November 2026 about spills. Which of our spills does the letter cover, and on which ones are we not compliant? Show me a table.",
      },
    ],
  },
  {
    id: "Q6",
    source: "host",
    title: "Which status is right?",
    tag: "OPS-3",
    blurb: "Inspection vs operator-note disagreements on producing oil.",
    visualHint: "Table with Status now",
    turns: [
      {
        id: "Q6-t1",
        userId: "U-601",
        askerName: "Nathan Pierce",
        session: "new",
        text: "Across the whole field, not just my area, for which wells do the latest inspection and the operator notes disagree about whether the well is producing oil? For each one, what is its real status right now, and why?",
      },
    ],
  },
  {
    id: "Q7",
    source: "host",
    title: "What the operators are hearing",
    tag: "Risk",
    blurb: "Two turns: rank repair risk, then pick three crews for this week.",
    visualHint: "Ranked table, then short recommendation",
    turns: [
      {
        id: "Q7-t1",
        userId: "U-301",
        askerName: "Robert Hayes",
        session: "new",
        text: "Over the last month the operators have written notes about wells that sound or behave wrong. Which of those wells haven't had a repair since? Rank the 10 most likely to need a repair in the next 90 days, other than a spill clean-up, and quote the notes as evidence.",
      },
      {
        id: "Q7-t2",
        userId: "U-301",
        askerName: "Robert Hayes",
        session: "same",
        text: "Which three would you send a crew to first this week, and why?",
      },
    ],
  },
  {
    id: "Q8",
    source: "host",
    title: "Who told you that?",
    tag: "Memory",
    blurb: "Five turns across Nathan, Robert, and Olivia — shared vs private memory.",
    visualHint: "Tables on turns 3 and 5; provenance every turn",
    turns: [
      {
        id: "Q8-t1",
        userId: "U-601",
        askerName: "Nathan Pierce",
        session: "new",
        text: "WELL-0333's recalled pump was swapped out yesterday. The work order isn't in the system yet. Please count it as replaced from now on.",
      },
      {
        id: "Q8-t2",
        userId: "U-601",
        askerName: "Nathan Pierce",
        session: "same",
        text: "Also, just for me: whenever you list wells, sort them by area and then by well ID, and show costs in thousands of dollars.",
      },
      {
        id: "Q8-t3",
        userId: "U-301",
        askerName: "Robert Hayes",
        session: "new",
        text: "Which recalled pumps are still in the ground right now?",
      },
      {
        id: "Q8-t4",
        userId: "U-501",
        askerName: "Olivia Grant",
        session: "new",
        text: "Nathan told me the recalled pump on WELL-0577 was swapped as well. Take it off the recall list.",
      },
      {
        id: "Q8-t5",
        userId: "U-601",
        askerName: "Nathan Pierce",
        session: "new",
        text: "Show me the recalled pumps that are still in the ground in my area, and what it cost to install each one.",
      },
    ],
  },
  {
    id: "Q9",
    source: "host",
    title: "One conversation, several topics",
    tag: "Multi-topic",
    blurb: "Six turns in one Robert Hayes session — recalls, org, SOP, H₂S, follow-ups.",
    turns: [
      {
        id: "Q9-t1",
        userId: "U-301",
        askerName: "Robert Hayes",
        session: "new",
        text: "How many recalled pumps are still in the ground, and in which areas?",
      },
      {
        id: "Q9-t2",
        userId: "U-301",
        askerName: "Robert Hayes",
        session: "same",
        text: "Different topic. Who leads Northwest Production, and how many wells does that team run?",
      },
      {
        id: "Q9-t3",
        userId: "U-301",
        askerName: "Robert Hayes",
        session: "same",
        text: "What does our operations SOP say about cold weather? Name one well that missed the check in December.",
      },
      {
        id: "Q9-t4",
        userId: "U-301",
        askerName: "Robert Hayes",
        session: "same",
        text: "An operator reported a gas smell at WELL-0332 on 3 Dec. What was the H2S reading?",
      },
      {
        id: "Q9-t5",
        userId: "U-301",
        askerName: "Robert Hayes",
        session: "same",
        text: "Back to the pumps from my first question: which of those wells are not producing oil right now, and when was each one last repaired?",
      },
      {
        id: "Q9-t6",
        userId: "U-301",
        askerName: "Robert Hayes",
        session: "same",
        text: "Of all the wells we've talked about today, which one would you deal with first, and why?",
      },
    ],
  },
  {
    id: "Q10",
    source: "host",
    title: "What are we waiting on?",
    tag: "Downtime",
    blurb: "Shut-in wait reasons by area for 2026 jobs.",
    visualHint: "Table + stacked bar chart",
    turns: [
      {
        id: "Q10-t1",
        userId: "U-201",
        askerName: "Michael Turner",
        session: "new",
        text: "When a well stays shut in longer than the repair itself, what are we usually waiting on: parts, crews, contractors or weather? Break it down by area for jobs started in 2026, with the typical number of extra days, and tell me if any area stands out.",
      },
    ],
  },
  {
    id: "Q11",
    source: "host",
    title: "Hotter wells",
    tag: "Temperature",
    blurb: "Which region of the field consistently runs hotter?",
    visualHint: "Bar chart by area",
    turns: [
      {
        id: "Q11-t1",
        userId: "U-501",
        askerName: "Olivia Grant",
        session: "new",
        text: "Which region of the field consistently runs hotter?",
      },
    ],
  },
];

/** FieldSense-curated extras for demos (not a substitute for the host set). */
export const FIELDSENSE_QUESTIONS: CatalogQuestion[] = [
  {
    id: "FS-1",
    source: "fieldsense",
    title: "WELL-0001 status card",
    tag: "Status",
    blurb: "Single-well status with latest inspection and inspector.",
    visualHint: "Status card",
    turns: [
      {
        id: "FS-1-t1",
        userId: "U-201",
        askerName: "Michael Turner",
        session: "new",
        text: "Is WELL-0001 producing oil right now? When was it last inspected, and by whom? Show me its status card.",
      },
    ],
  },
  {
    id: "FS-2",
    source: "fieldsense",
    title: "Gas odor response times",
    tag: "Safety",
    blurb: "Same theme as host Q3 — quick demo of OPS-1 tables.",
    turns: [
      {
        id: "FS-2-t1",
        userId: "U-401",
        askerName: "Laura Simmons",
        session: "new",
        text: "Since 1 Nov 2026, every time an operator note reports gas at a well, did we get someone out to that well in time under our operating procedures? List every report and whether the response met the deadline.",
      },
    ],
  },
  {
    id: "FS-3",
    source: "fieldsense",
    title: "Temporary flowline bypasses",
    tag: "Compliance",
    blurb: "Same theme as host Q4 — bypass approval table.",
    turns: [
      {
        id: "FS-3-t1",
        userId: "U-402",
        askerName: "Chris Dalton",
        session: "new",
        text: "Across all areas, which temporary flowline bypasses are in place right now, and is each one allowed? Also list any bypass, past or present, that stayed in after its approval ran out or was never approved at all.",
      },
    ],
  },
  {
    id: "FS-4",
    source: "fieldsense",
    title: "Commission letter on spills",
    tag: "Regulator",
    blurb: "Same theme as host Q5 — spill compliance table.",
    turns: [
      {
        id: "FS-4-t1",
        userId: "U-201",
        askerName: "Michael Turner",
        session: "new",
        text: "The State Oil & Gas Commission wrote to us in November 2026 about spills. Which of our spills does the letter cover, and on which ones are we not compliant? Show me a table.",
      },
    ],
  },
  {
    id: "FS-5",
    source: "fieldsense",
    title: "Wells most likely to need repair",
    tag: "Risk",
    blurb: "Host Q7 turn 1 — ranked repair-risk table with note quotes.",
    turns: [
      {
        id: "FS-5-t1",
        userId: "U-301",
        askerName: "Robert Hayes",
        session: "new",
        text: "Over the last month the operators have written notes about wells that sound or behave wrong. Which of those wells haven't had a repair since? Rank the 10 most likely to need a repair in the next 90 days, other than a spill clean-up, and quote the notes as evidence.",
      },
    ],
  },
  {
    id: "FS-6",
    source: "fieldsense",
    title: "Recalled pumps still installed",
    tag: "Equipment",
    blurb: "Host Q8 turn 3 — current recall inventory table.",
    turns: [
      {
        id: "FS-6-t1",
        userId: "U-301",
        askerName: "Robert Hayes",
        session: "new",
        text: "Which recalled pumps are still in the ground right now?",
      },
    ],
  },
  {
    id: "FS-7",
    source: "fieldsense",
    title: "What delays shut-in wells?",
    tag: "Downtime",
    blurb: "Host Q10 — wait-reason breakdown with stacked bars.",
    turns: [
      {
        id: "FS-7-t1",
        userId: "U-201",
        askerName: "Michael Turner",
        session: "new",
        text: "When a well stays shut in longer than the repair itself, what are we usually waiting on: parts, crews, contractors or weather? Break it down by area for jobs started in 2026, with the typical number of extra days, and tell me if any area stands out.",
      },
    ],
  },
  {
    id: "FS-8",
    source: "fieldsense",
    title: "Which region runs hotter?",
    tag: "Temperature",
    blurb: "Host Q11 — area temperature comparison chart.",
    turns: [
      {
        id: "FS-8-t1",
        userId: "U-501",
        askerName: "Olivia Grant",
        session: "new",
        text: "Which region of the field consistently runs hotter?",
      },
    ],
  },
];

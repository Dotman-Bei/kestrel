import Link from "next/link";
import { GrainOverlay } from "@/components/GrainOverlay";
import { Hero } from "@/components/Hero";
import { Nav } from "@/components/Nav";
import { PolicyCards } from "@/components/PolicyCards";
import { Reveal } from "@/components/Reveal";
import { ThesisDiagram } from "@/components/ThesisDiagram";

/* Copy voice: terse, concrete, slightly rueful. Three-beat lines with a
   fragment ending. Problem statements name a real failure, not a category. */

const GAP = [
  {
    label: "What a per-entity test can ask",
    tone: "bg-void-3",
    items: [
      "Does this column have a PII tag?",
      "Does this table have an owner?",
      "Is this dataset described?",
    ],
    note: "Useful. Kestrel ships one of these too.",
  },
  {
    label: "What governance actually asks",
    tone: "bg-blush",
    items: [
      "Does this PII column reach a dashboard — through any path?",
      "Did anything mask it on the way there?",
      "Does this certified model depend on something stale, four hops up?",
    ],
    note: "Conditions over paths. No per-entity test can state them.",
  },
];

const PROBLEMS = [
  {
    title: "The tag stops. The data doesn't.",
    body: "Someone tags `ssn` at the source and moves on. Four transforms later the same value is sitting in a Looker explore under a different name, untagged, and every per-entity check reports green.",
  },
  {
    title: "The rule lives in a doc nobody enforces.",
    body: "\"PII must never reach BI\" is written down somewhere. It is not executable, nothing checks it on merge, and the first time anyone verifies it is during an audit.",
  },
  {
    title: "Certification outlives its owner.",
    body: "A model gets certified, the owner changes teams, the upstream starts failing its freshness check. The badge stays. Everyone downstream keeps trusting it.",
  },
  {
    title: "Findings die in a terminal.",
    body: "A scanner prints a wall of red, someone screenshots it into Slack, and the next person to open the asset in the catalog learns nothing at all.",
  },
];

const LAYERS = [
  {
    n: "01",
    label: "Tag",
    tone: "bg-blush",
    body: "`policy-violation` on the offending column — and on the dashboard the data leaked into. The analyst who opens that dashboard sees the finding without knowing the rule exists.",
  },
  {
    n: "02",
    label: "Structured property",
    tone: "bg-sage",
    body: "The machine-readable record: policy id, severity, source, sink, the full path, timestamp. Queryable by whatever agent runs next.",
  },
  {
    n: "03",
    label: "Document",
    tone: "bg-sky",
    body: "An incident write-up linked to both ends of the path: what rule fired, the hop-by-hop table, the real SQL behind those hops, who owns it, and the fix.",
  },
];

const LOOP = [
  { step: "READ", body: "Find the policy's subjects, then trace their lineage over MCP." },
  { step: "EVALUATE", body: "Walk each path and test the condition — including what excuses it." },
  { step: "ACT", body: "Tag, record, document. Draft the PR. Ping the owner." },
];

export default function Home() {
  return (
    <div className="relative flex min-h-full flex-1 flex-col">
      <GrainOverlay />
      <Nav />

      <main className="flex-1">
        <Hero />

        {/* ------------------------------------------------- the gap ----- */}
        <section id="gap" className="scroll-mt-28 mx-auto max-w-[1180px] px-6 pb-[90px] pt-[60px] min-[900px]:px-12">
          <Reveal>
            <p className="eyebrow">The originality question, answered first</p>
            <h2
              className="mt-5 max-w-[18ch] font-display font-extrabold leading-[1.1] tracking-[-0.02em]"
              style={{ fontSize: "clamp(28px, 4vw, 44px)" }}
            >
              One entity at a time is the wrong unit.
            </h2>
          </Reveal>

          <div className="mt-12 grid grid-cols-1 gap-7 min-[900px]:grid-cols-2">
            {GAP.map((column, i) => (
              <Reveal key={column.label} index={i}>
                <div
                  className={`h-full rounded-[20px] border-2 border-void ${column.tone} p-8`}
                  style={{ boxShadow: "6px 6px 0 0 var(--color-brut-line)" }}
                >
                  <p className="data-label text-void/60">{column.label}</p>
                  <ul className="mt-5 space-y-4">
                    {column.items.map((item) => (
                      <li key={item} className="flex gap-3 text-[15px] leading-[1.5] text-void">
                        <span aria-hidden className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-void" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-7 border-t border-void/15 pt-5 text-[13px] italic text-void/70">
                    {column.note}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>
        </section>

        {/* ------------------------------------------------ the thesis --- */}
        <section className="mx-auto max-w-[1180px] px-6 pb-[70px] pt-[40px] text-center min-[900px]:px-12">
          <Reveal>
            <p className="eyebrow">One violation, drawn</p>
            <h2
              className="mx-auto mt-5 max-w-[22ch] font-display font-extrabold leading-[1.15] tracking-[-0.02em]"
              style={{ fontSize: "clamp(26px, 3.4vw, 38px)" }}
            >
              A per-entity test can only see one box.
            </h2>
            <p className="mx-auto mt-5 max-w-[58ch] text-[15px] leading-[1.6] text-muted">
              This is a real finding from the sample graph. Every box on it passes on its own.
              The violation is the <em className="not-italic font-semibold text-text">shape of the path</em>.
            </p>
          </Reveal>

          <div className="mt-14">
            <ThesisDiagram />
          </div>

          <Reveal>
            <p className="machine mx-auto mt-6 max-w-[70ch] text-left text-muted-2 min-[900px]:text-center">
              note: hop 4 fell back to table-level lineage — column lineage was not populated there,
              and the report says so rather than pretending otherwise.
            </p>
          </Reveal>
        </section>

        {/* ------------------------------------------------- problems ---- */}
        <section className="mx-auto max-w-[1180px] px-6 pb-[90px] pt-[60px] min-[900px]:px-12">
          <Reveal>
            <p className="eyebrow">Why nobody catches this</p>
          </Reveal>
          <div className="mt-12 grid grid-cols-1 gap-x-20 gap-y-12 min-[900px]:grid-cols-2">
            {PROBLEMS.map((problem, i) => (
              <Reveal key={problem.title} index={i}>
                <h3 className="font-display text-[21px] font-semibold leading-snug tracking-[-0.01em] text-void">
                  {problem.title}
                </h3>
                <p className="mt-3 text-[14.5px] leading-[1.6] text-muted">{problem.body}</p>
              </Reveal>
            ))}
          </div>
        </section>

        {/* ------------------------------------------------- policies ---- */}
        <section id="policies" className="scroll-mt-28 mx-auto max-w-[1180px] px-6 pb-[90px] pt-[70px] min-[900px]:px-12">
          <Reveal>
            <p className="eyebrow">The four rules</p>
            <h2
              className="mt-5 max-w-[20ch] font-display font-extrabold leading-[1.1] tracking-[-0.02em]"
              style={{ fontSize: "clamp(28px, 4vw, 44px)" }}
            >
              Three deterministic. One that reasons.
            </h2>
            <p className="mt-5 max-w-[62ch] text-[15px] leading-[1.6] text-muted">
              The templates are LLM-free on purpose — the core enforcement path cannot flake. The
              agent is additive, and when it can, it compiles your English into one of these.
            </p>
          </Reveal>

          <div className="mt-12">
            <PolicyCards />
          </div>
        </section>

        {/* ------------------------------------------------ write-back --- */}
        <section id="writeback" className="scroll-mt-28 mx-auto max-w-[1180px] px-6 pb-[90px] pt-[60px] min-[900px]:px-12">
          <Reveal>
            <p className="eyebrow">What lands in DataHub</p>
            <h2
              className="mt-5 max-w-[22ch] font-display font-extrabold leading-[1.1] tracking-[-0.02em]"
              style={{ fontSize: "clamp(28px, 4vw, 44px)" }}
            >
              The graph is richer after a run than before it.
            </h2>
            <p className="mt-5 max-w-[62ch] text-[15px] leading-[1.6] text-muted">
              Three layers per violation, in increasing order of usefulness to a human. Read-only
              tools report; this is the part that makes the catalog remember.
            </p>
          </Reveal>

          <div className="mt-12 grid grid-cols-1 gap-7 min-[900px]:grid-cols-3">
            {LAYERS.map((layer, i) => (
              <Reveal key={layer.n} index={i}>
                <div
                  className={`h-full rounded-[20px] border-2 border-void ${layer.tone} p-8`}
                  style={{ boxShadow: "6px 6px 0 0 var(--color-brut-line)" }}
                >
                  <p className="font-mono text-[13px] font-medium tracking-[0.08em] text-void/55">
                    {layer.n}
                  </p>
                  <h3 className="mt-3 font-display text-[20px] font-extrabold tracking-[-0.01em] text-void">
                    {layer.label}
                  </h3>
                  <p className="mt-3 text-[14px] leading-[1.55] text-void/75">{layer.body}</p>
                </div>
              </Reveal>
            ))}
          </div>

          <Reveal>
            <p className="mt-8 text-[13.5px] leading-[1.6] text-muted">
              <span className="data-label mr-2 text-void">OSS-safe</span>
              <code className="font-mono text-[12.5px]">update_description</code> is Cloud-only and
              hidden on OSS DataHub, so nothing here depends on it. Tags, structured properties and
              documents are the whole surface.
            </p>
          </Reveal>
        </section>

        {/* ---------------------------------------------------- the loop - */}
        <section className="mx-auto max-w-[1180px] px-6 pb-[100px] pt-[40px] min-[900px]:px-12">
          <div className="grid grid-cols-1 gap-7 min-[900px]:grid-cols-3">
            {LOOP.map((item, i) => (
              <Reveal key={item.step} index={i}>
                <div className="border-t-2 border-void pt-5">
                  <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-signal">
                    {item.step}
                  </p>
                  <p className="mt-3 text-[14.5px] leading-[1.55] text-muted">{item.body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </section>

        {/* ------------------------------------------------------- close - */}
        <section className="mx-auto max-w-[1180px] px-6 pb-[70px] text-center min-[900px]:px-12">
          <Reveal>
            <h2
              className="mx-auto max-w-[20ch] font-display font-extrabold leading-[1.05] tracking-[-0.02em]"
              style={{ fontSize: "clamp(30px, 4.6vw, 52px)" }}
            >
              Write your governance as code. Let the agent enforce it.
            </h2>
            <div className="mt-10 flex flex-col items-center justify-center gap-4 min-[480px]:flex-row">
              <Link href="/dashboard" className="btn-press bg-signal text-surface hover:bg-[var(--color-signal-deep)]">
                See a real scan
              </Link>
              <a
                href="https://github.com/kestrel-sentinel/kestrel"
                className="btn-press bg-surface"
                style={{ boxShadow: "5px 5px 0 0 var(--color-signal-dim)" }}
              >
                Read the source
              </a>
            </div>
          </Reveal>
        </section>
      </main>

      <footer className="overflow-hidden border-t border-border px-6 pb-10 pt-16 min-[900px]:px-12">
        <div className="mx-auto max-w-[1180px]">
          <p
            aria-hidden
            className="select-none font-display font-extrabold leading-[0.9] tracking-[-0.03em] text-void/10"
            style={{ fontSize: "clamp(72px, 15vw, 200px)" }}
          >
            KESTREL
          </p>
          <div className="mt-8 flex flex-col gap-3 min-[900px]:flex-row min-[900px]:items-center min-[900px]:justify-between">
            <p className="data-label">Kestrel · Policy Sentinel · Apache 2.0</p>
            <p className="data-label">
              DataHub · MCP Server · Multi-hop lineage · Write-back
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}

import type { LineagePath } from "@/lib/report";
import { entityKind, prose, shortName } from "@/lib/report";

/**
 * The evidence, rendered.
 *
 * The subject sits at the head, the sink is filled in signal, and every hop
 * carries its granularity. A table-level hop is called out rather than quietly
 * blended in — the report is honest about which lineage proved the path.
 */
export function PathTrail({ path }: { path: LineagePath }) {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-3">
        {path.nodes.map((node, i) => {
          const last = i === path.nodes.length - 1;
          return (
            <span key={node.urn} className="flex min-w-0 max-w-full items-center gap-2">
              {i > 0 && (
                <span aria-hidden className="font-mono text-[13px] text-signal">
                  &rarr;
                </span>
              )}
              <span
                className={`inline-flex min-w-0 max-w-full flex-wrap items-center gap-x-2 rounded-full border-2 border-void px-3 py-[5px] font-mono text-[12px] break-all ${
                  last ? "bg-signal text-surface" : i === 0 ? "bg-blush text-void" : "bg-surface text-void"
                }`}
                style={{ boxShadow: "3px 3px 0 0 var(--color-brut-line)" }}
              >
                {shortName(node.urn)}
                <span className={last ? "text-surface/70" : "text-muted-2"}>
                  {entityKind(node).toLowerCase()}
                </span>
              </span>
            </span>
          );
        })}
      </div>

      <ul className="mt-5 space-y-2">
        {path.edges.map((hop, i) => (
          <li key={`${hop.source}-${hop.target}`} className="flex flex-wrap items-baseline gap-x-3">
            <span className="data-label shrink-0">Hop {i + 1}</span>
            {hop.level === "table" && (
              <span className="rounded-[4px] bg-sand px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-void">
                table-level
              </span>
            )}
            {hop.transform && (
              <span className="font-mono text-[11.5px] text-muted">{hop.transform}</span>
            )}
            {hop.query && (
              <code className="block w-full overflow-x-auto whitespace-pre rounded-[6px] bg-void-3 px-3 py-2 font-mono text-[11px] text-muted">
                {hop.query}
              </code>
            )}
          </li>
        ))}
      </ul>

      {path.notes?.map((note) => (
        <p key={note} className="mt-4 font-mono text-[11px] leading-relaxed text-muted-2">
          note: {prose(note)}
        </p>
      ))}
    </div>
  );
}

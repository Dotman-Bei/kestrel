"""Write-back: the part that makes the graph richer after a scan than before it.

Three layers per violation, in increasing order of usefulness to a human:

1. **Tag** the offending entity/column (and, for a lineage rule, the asset the
   data leaked *into*) -- instantly visible in the DataHub UI.
2. **Structured property** carrying the machine-readable record: policy id,
   severity, source, sink, path, timestamp. Queryable by the next agent.
3. **Document** -- the incident write-up, linked to both ends of the path.

Then two optional actions that turn a report into work: open a remediation PR,
or notify the owner.

``update_description`` is never used: it is Cloud-only and hidden on OSS, so the
whole design stands on the OSS-safe write surface.

Every outward-facing action (a real PR, a real Slack post) is opt-in behind an
explicit flag. Without those flags the artifacts are written to disk and the
exact command to send them is printed -- so a dry run is genuinely dry.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import render, urns
from .catalog import Catalog, CatalogError
from .models import Violation, WriteBack
from .policy import Policy

DEFAULT_PROPERTY_URN = "urn:li:structuredProperty:io.kestrel.policy_violation"


@dataclass
class WriteBackConfig:
    """What the scan is allowed to change, and where artifacts land."""

    enabled: bool = True
    dry_run: bool = False
    tag_sink: bool = True
    property_urn: str = DEFAULT_PROPERTY_URN
    out_dir: Path = Path("out")
    open_pr: bool = False
    send_notify: bool = False
    pr_repo: Optional[str] = None
    slack_webhook: Optional[str] = None

    def __post_init__(self) -> None:
        self.out_dir = Path(self.out_dir)
        self.pr_repo = self.pr_repo or os.environ.get("KESTREL_PR_REPO")
        self.slack_webhook = self.slack_webhook or os.environ.get("KESTREL_SLACK_WEBHOOK")


@dataclass
class WriteBackWriter:
    """Applies the write-back layers for one scan run."""

    catalog: Catalog
    run_id: str
    config: WriteBackConfig = field(default_factory=WriteBackConfig)
    documents: List[Dict[str, str]] = field(default_factory=list, init=False)
    _dirs_ready: bool = field(default=False, init=False, repr=False)

    @property
    def base_url(self) -> Optional[str]:
        return self.catalog.base_url

    @property
    def active(self) -> bool:
        """True when writes will actually land in the catalog."""
        return self.config.enabled and not self.config.dry_run and self.catalog.writes_enabled

    # ------------------------------------------------------------- helpers

    def _dir(self, *parts: str) -> Path:
        path = self.config.out_dir.joinpath(*parts)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _rel(path: Path) -> str:
        """Paths in a report are read by other people on other machines.

        Absolute paths leak the author's home directory into every committed
        artifact, so report them relative to the working directory.
        """
        try:
            return path.resolve().relative_to(Path.cwd()).as_posix()
        except ValueError:
            return path.as_posix()

    def _record(
        self,
        kind: str,
        target: str,
        detail: str,
        payload: Optional[Dict[str, object]] = None,
        write=None,
    ) -> WriteBack:
        """Run one write, recording success, failure or dry-run uniformly."""
        entry = WriteBack(
            kind=kind,
            target_urn=target,
            detail=detail,
            dry_run=not self.active,
            payload=payload or {},
        )
        if not self.active or write is None:
            return entry
        try:
            write()
            entry.applied = True
            entry.dry_run = False
        except (CatalogError, Exception) as exc:  # a failed write must not abort the scan
            entry.error = f"{type(exc).__name__}: {exc}"
        return entry

    # -------------------------------------------------------------- layers

    def apply(self, violation: Violation, policy: Policy) -> List[WriteBack]:
        actions = set(policy.on_violation)
        results: List[WriteBack] = []

        if "tag" in actions:
            results.extend(self._tag(violation, policy))
        if "structured_property" in actions:
            results.append(self._structured_property(violation))
        if "document" in actions:
            results.append(self._document(violation, policy))
        if "pr" in actions:
            results.append(self._pull_request(violation, policy))
        if "notify" in actions:
            results.append(self._notify(violation, policy))

        violation.writebacks = results
        return results

    def _tag(self, violation: Violation, policy: Policy) -> List[WriteBack]:
        tag = policy.tag_name
        out = [
            self._record(
                "tag",
                violation.subject.urn,
                f"tagged `{urns.short_name(violation.subject.urn)}` with `{tag}`",
                {"tag": tag},
                write=lambda: self.catalog.add_tags(violation.subject.urn, [tag]),
            )
        ]
        # Tagging the sink is what makes the finding discoverable from the other
        # end: the analyst opening the dashboard sees it without knowing the rule.
        if self.config.tag_sink and violation.sink is not None:
            sink_urn = violation.sink.urn
            out.append(
                self._record(
                    "tag",
                    sink_urn,
                    f"tagged exposure point `{urns.short_name(sink_urn)}` with `{tag}`",
                    {"tag": tag},
                    write=lambda: self.catalog.add_tags(sink_urn, [tag]),
                )
            )
        return out

    def _structured_property(self, violation: Violation) -> WriteBack:
        payload = render.structured_property_payload(violation, self.run_id)
        prop = {self.config.property_urn: json.dumps(payload, sort_keys=True)}
        return self._record(
            "structured_property",
            violation.subject.urn,
            f"recorded `{self.config.property_urn.rsplit(':', 1)[-1]}` "
            f"on `{urns.short_name(violation.subject.urn)}`",
            payload,
            write=lambda: self.catalog.add_structured_properties(violation.subject.urn, prop),
        )

    def _document(self, violation: Violation, policy: Policy) -> WriteBack:
        # ASCII title on purpose: it is echoed to the terminal, and Windows
        # consoles still default to a codepage that cannot encode dashes.
        title = f"Policy violation: {policy.id} - {violation.title}"
        content = render.incident_markdown(violation, policy, self.run_id, self.base_url)
        related = [violation.subject.urn]
        if violation.sink is not None:
            related.append(violation.sink.urn)

        # Always mirror to disk: this is what examples/ ships and what the video
        # shows side by side with the DataHub UI.
        path = self._dir("documents") / f"{violation.id}.md"
        path.write_text(content, encoding="utf-8")
        self.documents.append({"id": violation.id, "title": title, "path": self._rel(path)})

        return self._record(
            "document",
            violation.subject.urn,
            f'authored incident document "{title}"',
            {"title": title, "file": self._rel(path), "related": related},
            write=lambda: self.catalog.save_document(
                title=title, content=content, related_urns=related, doc_id=violation.id
            ),
        )

    # -------------------------------------------------------------- actions

    def _pull_request(self, violation: Violation, policy: Policy) -> WriteBack:
        body = render.pr_body(violation, policy, self.base_url)
        path = self._dir("actions") / f"{violation.id}.pr.md"
        path.write_text(body, encoding="utf-8")

        title = f"fix({policy.id}): {violation.title}"
        rel = self._rel(path)
        if not (self.config.open_pr and self.config.pr_repo):
            hint = self.config.pr_repo or "<owner/repo>"
            return WriteBack(
                kind="pr",
                target_urn=violation.subject.urn,
                detail=f"drafted remediation PR -> {rel}",
                dry_run=True,
                payload={
                    "title": title,
                    "file": rel,
                    "command": f'gh pr create --repo {hint} --title "{title}" --body-file {rel}',
                },
            )

        entry = WriteBack(
            kind="pr",
            target_urn=violation.subject.urn,
            detail=f"opened remediation PR in {self.config.pr_repo}",
            payload={"title": title, "file": rel},
        )
        if shutil.which("gh") is None:
            entry.error = "gh CLI not found on PATH"
            entry.dry_run = True
            return entry
        try:
            proc = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--repo", self.config.pr_repo,
                    "--title", title,
                    "--body-file", str(path),
                ],
                capture_output=True,
                text=True,
                timeout=90,
            )
            if proc.returncode == 0:
                entry.applied = True
                entry.payload["url"] = proc.stdout.strip()
                entry.detail = f"opened remediation PR: {proc.stdout.strip()}"
            else:
                entry.error = (proc.stderr or proc.stdout).strip()[:400]
        except Exception as exc:
            entry.error = f"{type(exc).__name__}: {exc}"
        return entry

    def _notify(self, violation: Violation, policy: Policy) -> WriteBack:
        message = render.notification_markdown(violation, policy, self.base_url)
        path = self._dir("actions") / f"{violation.id}.notify.md"
        path.write_text(message, encoding="utf-8")
        rel = self._rel(path)
        owners = ", ".join(urns.short_name(o) for o in violation.owners) or "unassigned"

        if not (self.config.send_notify and self.config.slack_webhook):
            return WriteBack(
                kind="notify",
                target_urn=violation.subject.urn,
                detail=f"drafted owner ping for {owners} -> {rel}",
                dry_run=True,
                payload={"owners": violation.owners, "file": rel},
            )

        entry = WriteBack(
            kind="notify",
            target_urn=violation.subject.urn,
            detail=f"notified {owners}",
            payload={"owners": violation.owners, "file": rel},
        )
        try:
            import urllib.request

            request = urllib.request.Request(
                self.config.slack_webhook,
                data=json.dumps({"text": message}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                if 200 <= response.status < 300:
                    entry.applied = True
                else:
                    entry.error = f"webhook returned HTTP {response.status}"
        except Exception as exc:
            entry.error = f"{type(exc).__name__}: {exc}"
        return entry

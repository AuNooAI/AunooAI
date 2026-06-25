import React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Separator from "@radix-ui/react-separator";
import type { EmergingTopic } from "./types";
import {
  deriveCategory,
  CATEGORY_LABELS,
  URGENCY_BADGE,
  VELOCITY_BADGE,
  scoreColour,
  allActors,
  formatDate,
} from "./utils";

interface TopicDetailPanelProps {
  topic: EmergingTopic | null;
  open: boolean;
  onClose: () => void;
}

export function TopicDetailPanel({ topic, open, onClose }: TopicDetailPanelProps) {
  if (!topic) return null;

  const urgency = topic.synthesis?.urgency ?? "low";
  const velocity = topic.velocity ?? "stable";
  const score = topic.trend_score?.composite ?? topic.composite_score ?? 0;
  const category = deriveCategory(topic.topic_filter);
  const urgencyBadge = URGENCY_BADGE[urgency] ?? URGENCY_BADGE.low;
  const velBadge = VELOCITY_BADGE[velocity] ?? VELOCITY_BADGE.stable;
  const actors = allActors(topic);

  return (
    <Dialog.Root open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.35)",
            zIndex: 200,
            animation: "fadeIn 0.15s ease",
          }}
        />
        <Dialog.Content
          aria-describedby="detail-description"
          style={{
            position: "fixed",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            width: "min(780px, 92vw)",
            maxHeight: "85vh",
            overflowY: "auto",
            background: "var(--aunoo-surface)",
            border: `0.5px solid var(--aunoo-border-hover)`,
            borderRadius: "var(--aunoo-radius-lg)",
            padding: "24px",
            zIndex: 201,
            animation: "slideUp 0.18s ease",
          }}
        >
          {/* Close button */}
          <Dialog.Close asChild>
            <button
              style={{
                all: "unset",
                position: "absolute",
                top: 16,
                right: 16,
                width: 28,
                height: 28,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                borderRadius: "var(--aunoo-radius-sm)",
                fontSize: 18,
                color: "var(--aunoo-muted-text)",
                cursor: "pointer",
                transition: "background 0.12s",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--aunoo-muted-bg)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              aria-label="Close"
            >
              \u00D7
            </button>
          </Dialog.Close>

          {/* Header */}
          <div style={{ marginBottom: 16, paddingRight: 32 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 6,
                flexWrap: "wrap",
              }}
            >
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 500,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  color: "var(--aunoo-muted-text)",
                }}
              >
                {CATEGORY_LABELS[category]}
              </span>
              <SmallBadge bg={urgencyBadge.bg} color={urgencyBadge.text}>
                {urgencyBadge.label} urgency
              </SmallBadge>
              <SmallBadge bg={velBadge.bg} color={velBadge.text}>
                {velBadge.label}
              </SmallBadge>
            </div>
            <Dialog.Title
              style={{ fontSize: 17, fontWeight: 500, lineHeight: 1.35, margin: 0 }}
            >
              {topic.name}
            </Dialog.Title>
            {topic.events?.current_status && (
              <p
                id="detail-description"
                style={{ fontSize: 12, color: "var(--aunoo-muted-text)", marginTop: 4 }}
              >
                {topic.events.current_status}
              </p>
            )}
          </div>

          <Separator.Root
            style={{ height: "0.5px", background: "var(--aunoo-border)", marginBottom: 16 }}
          />

          {/* Key takeaway */}
          {topic.synthesis?.key_takeaway && (
            <div
              style={{
                background: "var(--aunoo-surface-secondary)",
                borderLeft: `3px solid ${scoreColour(score)}`,
                borderRadius: `0 var(--aunoo-radius-sm) var(--aunoo-radius-sm) 0`,
                padding: "10px 14px",
                marginBottom: 20,
              }}
            >
              <p style={{ fontSize: 12, fontWeight: 500, color: "var(--aunoo-muted-text)", margin: "0 0 3px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                Key takeaway
              </p>
              <p style={{ fontSize: 13, lineHeight: 1.55, margin: 0 }}>
                {topic.synthesis.key_takeaway}
              </p>
            </div>
          )}

          {/* Three-column body */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
              gap: 20,
              marginBottom: 20,
            }}
          >
            {/* Col 1: What happened */}
            <DetailSection title="What happened">
              {topic.events?.trigger_event && (
                <p style={bodyText}>{topic.events.trigger_event}</p>
              )}
              {(topic.events?.timeline ?? []).length > 0 && (
                <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 0" }}>
                  {topic.events!.timeline.map((item, i) => (
                    <li key={i} style={{ ...bodyText, paddingLeft: 12, position: "relative", marginBottom: 4 }}>
                      <span style={{ position: "absolute", left: 0, color: "var(--aunoo-muted-text)" }}>\u00B7</span>
                      {item}
                    </li>
                  ))}
                </ul>
              )}
            </DetailSection>

            {/* Col 2: Implications */}
            <DetailSection title="Implications">
              {topic.implications?.industry_impact && (
                <SubField label="Industry">{topic.implications.industry_impact}</SubField>
              )}
              {topic.implications?.regulatory && (
                <SubField label="Regulatory">{topic.implications.regulatory}</SubField>
              )}
              {topic.implications?.market && (
                <SubField label="Market">{topic.implications.market}</SubField>
              )}
            </DetailSection>

            {/* Col 3: Signals */}
            <DetailSection title="Signals">
              {(topic.signals?.growth_indicators ?? []).length > 0 && (
                <SubField label="Growth">
                  <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                    {topic.signals!.growth_indicators.map((s, i) => (
                      <li key={i} style={{ ...bodyText, paddingLeft: 12, position: "relative", marginBottom: 3 }}>
                        <span style={{ position: "absolute", left: 0, color: "var(--aunoo-green-text)" }}>\u2191</span>
                        {s}
                      </li>
                    ))}
                  </ul>
                </SubField>
              )}
              {(topic.signals?.risk_factors ?? []).length > 0 && (
                <SubField label="Risk">
                  <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                    {topic.signals!.risk_factors.map((s, i) => (
                      <li key={i} style={{ ...bodyText, paddingLeft: 12, position: "relative", marginBottom: 3 }}>
                        <span style={{ position: "absolute", left: 0, color: "var(--aunoo-red-text)" }}>!</span>
                        {s}
                      </li>
                    ))}
                  </ul>
                </SubField>
              )}
              {(topic.signals?.watch_for ?? []).length > 0 && (
                <SubField label="Watch for">
                  <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                    {topic.signals!.watch_for.map((s, i) => (
                      <li key={i} style={{ ...bodyText, paddingLeft: 12, position: "relative", marginBottom: 3 }}>
                        <span style={{ position: "absolute", left: 0, color: "var(--aunoo-amber-text)" }}>\u2192</span>
                        {s}
                      </li>
                    ))}
                  </ul>
                </SubField>
              )}
            </DetailSection>
          </div>

          <Separator.Root
            style={{ height: "0.5px", background: "var(--aunoo-border)", marginBottom: 16 }}
          />

          {/* Footer row: actors + score breakdown + meta */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr 1fr",
              gap: 20,
            }}
          >
            {/* Actors */}
            <DetailSection title="Actors">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {actors.slice(0, 8).map((a) => (
                  <span
                    key={a}
                    style={{
                      fontSize: 11,
                      padding: "2px 8px",
                      borderRadius: 99,
                      background: "var(--aunoo-muted-bg)",
                      color: "var(--aunoo-muted-text)",
                      border: `0.5px solid var(--aunoo-border)`,
                    }}
                  >
                    {a}
                  </span>
                ))}
              </div>
            </DetailSection>

            {/* Score breakdown */}
            <DetailSection title="Score breakdown">
              {topic.trend_score ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {(
                    [
                      ["Volume", topic.trend_score.volume],
                      ["Velocity", topic.trend_score.velocity],
                      ["Diversity", topic.trend_score.diversity],
                      ["Novelty", topic.trend_score.novelty],
                    ] as [string, number][]
                  ).map(([label, val]) => (
                    <div key={label}>
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          fontSize: 10,
                          color: "var(--aunoo-muted-text)",
                          marginBottom: 2,
                        }}
                      >
                        <span>{label}</span>
                        <span>{Math.round(val)}</span>
                      </div>
                      <div
                        style={{
                          height: 3,
                          background: "var(--aunoo-muted-bg)",
                          borderRadius: 2,
                          overflow: "hidden",
                        }}
                      >
                        <div
                          style={{
                            height: "100%",
                            width: `${Math.round(val)}%`,
                            background: scoreColour(val),
                            borderRadius: 2,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={bodyText}>Score data unavailable</p>
              )}
            </DetailSection>

            {/* Detection meta */}
            <DetailSection title="Detection history">
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                <MetaRow label="First detected" value={formatDate(topic.first_detection_date)} />
                <MetaRow label="Last detected" value={formatDate(topic.last_detection_date)} />
                <MetaRow label="Total detections" value={String(topic.detection_count ?? "\u2014")} />
                <MetaRow label="Consecutive runs" value={String(topic.consecutive_detections ?? "\u2014")} />
                <MetaRow label="Missed runs" value={String(topic.missed_runs ?? "\u2014")} />
                <MetaRow label="Article count" value={String(topic.article_count ?? "\u2014")} />
              </div>
            </DetailSection>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p
        style={{
          fontSize: 10,
          fontWeight: 500,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          color: "var(--aunoo-muted-text)",
          margin: "0 0 7px",
        }}
      >
        {title}
      </p>
      {children}
    </div>
  );
}

function SubField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ marginBottom: 8 }}>
      <p
        style={{
          fontSize: 10,
          color: "var(--aunoo-muted-text)",
          fontWeight: 500,
          margin: "0 0 2px",
        }}
      >
        {label}
      </p>
      {typeof children === "string" ? (
        <p style={bodyText}>{children}</p>
      ) : (
        children
      )}
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
      <span style={{ color: "var(--aunoo-muted-text)" }}>{label}</span>
      <span style={{ fontWeight: 500 }}>{value}</span>
    </div>
  );
}

function SmallBadge({
  children,
  bg,
  color,
}: {
  children: React.ReactNode;
  bg: string;
  color: string;
}) {
  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 500,
        padding: "2px 8px",
        borderRadius: 99,
        background: bg,
        color,
      }}
    >
      {children}
    </span>
  );
}

const bodyText: React.CSSProperties = {
  fontSize: 11,
  lineHeight: 1.55,
  color: "inherit",
  margin: 0,
};

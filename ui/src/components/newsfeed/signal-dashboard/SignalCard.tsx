import React from "react";
import * as Tooltip from "@radix-ui/react-tooltip";
import type { EmergingTopic } from "./types";
import {
  deriveCategory,
  CATEGORY_LABELS,
  URGENCY_ACCENT,
  URGENCY_BADGE,
  VELOCITY_BADGE,
  scoreColour,
} from "./utils";

interface SignalCardProps {
  topic: EmergingTopic;
  isSelected: boolean;
  onClick: () => void;
}

export function SignalCard({ topic, isSelected, onClick }: SignalCardProps) {
  const urgency = topic.synthesis?.urgency ?? "low";
  const velocity = topic.velocity ?? "stable";
  const score = topic.trend_score?.composite ?? topic.composite_score ?? 0;
  const category = deriveCategory(topic.topic_filter);
  const urgencyBadge = URGENCY_BADGE[urgency] ?? URGENCY_BADGE.low;
  const velBadge = VELOCITY_BADGE[velocity] ?? VELOCITY_BADGE.stable;
  const accentColour = URGENCY_ACCENT[urgency] ?? URGENCY_ACCENT.low;

  return (
    <button
      onClick={onClick}
      style={{
        all: "unset",
        display: "block",
        cursor: "pointer",
        background: "var(--aunoo-surface)",
        border: `0.5px solid ${isSelected ? "var(--aunoo-border-hover)" : "var(--aunoo-border)"}`,
        borderLeft: `3px solid ${accentColour}`,
        borderRadius: "var(--aunoo-radius-lg)",
        padding: "14px 16px",
        width: "100%",
        boxSizing: "border-box",
        textAlign: "left",
        transition: "border-color 0.15s, box-shadow 0.15s",
        boxShadow: isSelected ? "0 0 0 2px rgba(0,0,0,0.06)" : "none",
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          marginBottom: 8,
          gap: 8,
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
        <Badge bg={urgencyBadge.bg} color={urgencyBadge.text}>
          {urgencyBadge.label}
        </Badge>
      </div>

      {/* Topic name */}
      <p
        style={{
          fontSize: 13,
          fontWeight: 500,
          color: "inherit",
          lineHeight: 1.4,
          margin: "0 0 6px",
        }}
      >
        {topic.name}
      </p>

      {/* Key takeaway */}
      {topic.synthesis?.key_takeaway && (
        <p
          style={{
            fontSize: 11,
            color: "var(--aunoo-muted-text)",
            lineHeight: 1.55,
            margin: "0 0 10px",
            display: "-webkit-box",
            WebkitLineClamp: 3,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {topic.synthesis.key_takeaway}
        </p>
      )}

      {/* Score bar */}
      <div
        style={{
          height: 3,
          background: "var(--aunoo-muted-bg)",
          borderRadius: 2,
          margin: "0 0 8px",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${Math.round(score)}%`,
            background: scoreColour(score),
            borderRadius: 2,
            transition: "width 0.4s ease",
          }}
        />
      </div>

      {/* Footer meta row */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <Tooltip.Provider delayDuration={300}>
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
              <span style={{ fontSize: 11, color: "var(--aunoo-muted-text)", cursor: "default" }}>
                Score {Math.round(score)}
              </span>
            </Tooltip.Trigger>
            <Tooltip.Portal>
              <Tooltip.Content
                side="top"
                style={{
                  background: "var(--aunoo-surface)",
                  border: `0.5px solid var(--aunoo-border)`,
                  borderRadius: "var(--aunoo-radius-sm)",
                  padding: "6px 10px",
                  fontSize: 11,
                  color: "inherit",
                  boxShadow: "0 2px 8px rgba(0,0,0,0.10)",
                  zIndex: 100,
                }}
              >
                {topic.trend_score
                  ? `Vol ${Math.round(topic.trend_score.volume)} \u00B7 Vel ${Math.round(topic.trend_score.velocity)} \u00B7 Div ${Math.round(topic.trend_score.diversity)} \u00B7 Nov ${Math.round(topic.trend_score.novelty)}`
                  : "Composite trend score"}
                <Tooltip.Arrow style={{ fill: "var(--aunoo-border)" }} />
              </Tooltip.Content>
            </Tooltip.Portal>
          </Tooltip.Root>
        </Tooltip.Provider>

        <Badge bg={velBadge.bg} color={velBadge.text}>
          {velBadge.label}
        </Badge>

        {(topic.consecutive_detections ?? 0) > 1 && (
          <span style={{ fontSize: 10, color: "var(--aunoo-muted-text)", marginLeft: "auto" }}>
            {topic.consecutive_detections}\u00D7 consecutive
          </span>
        )}
      </div>
    </button>
  );
}

function Badge({
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
        color: color,
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

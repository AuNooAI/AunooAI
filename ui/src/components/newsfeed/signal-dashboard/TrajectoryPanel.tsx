import React from "react";
import * as Tooltip from "@radix-ui/react-tooltip";
import type { EmergingTopic } from "./types";
import { scoreColour } from "./utils";

interface TrajectoryPanelProps {
  topics: EmergingTopic[];
  /** ISO date strings for the columns, newest last. Max 10. */
  runDates: string[];
  onSelectTopic: (topic: EmergingTopic) => void;
}

export function TrajectoryPanel({ topics, runDates, onSelectTopic }: TrajectoryPanelProps) {
  const topN = topics.slice(0, 8);

  return (
    <div
      style={{
        background: "var(--aunoo-surface)",
        border: `0.5px solid var(--aunoo-border)`,
        borderRadius: "var(--aunoo-radius-lg)",
        padding: "14px 16px",
      }}
    >
      <p
        style={{
          fontSize: 11,
          fontWeight: 500,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          color: "var(--aunoo-muted-text)",
          margin: "0 0 12px",
        }}
      >
        Detection trajectory
      </p>

      {/* Column headers */}
      <div style={{ display: "flex", alignItems: "center", marginBottom: 8 }}>
        <div style={{ width: 160, flexShrink: 0 }} />
        <div style={{ display: "flex", gap: 4, flex: 1 }}>
          {runDates.map((d) => (
            <div
              key={d}
              style={{
                flex: 1,
                textAlign: "center",
                fontSize: 9,
                color: "var(--aunoo-muted-text)",
                fontWeight: 500,
              }}
            >
              {formatRunDate(d)}
            </div>
          ))}
        </div>
        <div style={{ width: 32, flexShrink: 0 }} />
      </div>

      {/* Rows */}
      <Tooltip.Provider delayDuration={200}>
        {topN.map((topic) => {
          const score = topic.trend_score?.composite ?? topic.composite_score ?? 0;
          const presence = derivePresence(topic, runDates);

          return (
            <div
              key={topic.id}
              style={{
                display: "flex",
                alignItems: "center",
                marginBottom: 7,
                cursor: "pointer",
              }}
              onClick={() => onSelectTopic(topic)}
            >
              {/* Topic label */}
              <div
                style={{
                  width: 160,
                  flexShrink: 0,
                  fontSize: 11,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  color: "inherit",
                  paddingRight: 8,
                }}
                title={topic.name}
              >
                {topic.name}
              </div>

              {/* Hit/miss dots */}
              <div style={{ display: "flex", gap: 4, flex: 1 }}>
                {presence.map((hit, i) => (
                  <Tooltip.Root key={i}>
                    <Tooltip.Trigger asChild>
                      <div
                        style={{
                          flex: 1,
                          height: 10,
                          borderRadius: 10,
                          background: hit
                            ? scoreColour(score)
                            : "var(--aunoo-muted-bg)",
                          border: hit
                            ? "none"
                            : `0.5px solid var(--aunoo-border)`,
                          transition: "opacity 0.1s",
                          cursor: "default",
                        }}
                      />
                    </Tooltip.Trigger>
                    <Tooltip.Portal>
                      <Tooltip.Content
                        side="top"
                        style={{
                          background: "var(--aunoo-surface)",
                          border: `0.5px solid var(--aunoo-border)`,
                          borderRadius: "var(--aunoo-radius-sm)",
                          padding: "4px 8px",
                          fontSize: 10,
                          zIndex: 100,
                          boxShadow: "0 2px 6px rgba(0,0,0,0.10)",
                        }}
                      >
                        {runDates[i]
                          ? `${formatRunDate(runDates[i])} \u2014 ${hit ? "detected" : "not detected"}`
                          : ""}
                        <Tooltip.Arrow style={{ fill: "var(--aunoo-border)" }} />
                      </Tooltip.Content>
                    </Tooltip.Portal>
                  </Tooltip.Root>
                ))}
              </div>

              {/* Streak count */}
              <div
                style={{
                  width: 32,
                  flexShrink: 0,
                  textAlign: "right",
                  fontSize: 10,
                  color: "var(--aunoo-muted-text)",
                  paddingLeft: 8,
                }}
              >
                {topic.consecutive_detections ?? 0}\u00D7
              </div>
            </div>
          );
        })}
      </Tooltip.Provider>

      {/* Legend */}
      <div
        style={{
          display: "flex",
          gap: 14,
          marginTop: 12,
          paddingTop: 10,
          borderTop: `0.5px solid var(--aunoo-border)`,
        }}
      >
        <LegendItem color="var(--aunoo-red)" label="High urgency" />
        <LegendItem color="var(--aunoo-amber)" label="Medium" />
        <LegendItem color="var(--aunoo-muted-text)" label="Low" />
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: 10,
              background: "var(--aunoo-muted-bg)",
              border: `0.5px solid var(--aunoo-border)`,
            }}
          />
          <span style={{ fontSize: 10, color: "var(--aunoo-muted-text)" }}>Not detected</span>
        </div>
      </div>
    </div>
  );
}

function formatRunDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" }).replace(" ", "\u00A0");
}

function derivePresence(topic: EmergingTopic, runDates: string[]): boolean[] {
  const first = topic.first_detection_date ? new Date(topic.first_detection_date).getTime() : null;
  const last = topic.last_detection_date ? new Date(topic.last_detection_date).getTime() : null;
  const consec = topic.consecutive_detections ?? 0;
  const missed = topic.missed_runs ?? 0;

  return runDates.map((d) => {
    const t = new Date(d).getTime();
    if (first && last) {
      const withinWindow = t >= first && t <= last;
      if (!withinWindow) return false;
      if (missed > consec) {
        const idx = runDates.indexOf(d);
        return idx % 2 === 0;
      }
      return true;
    }
    return false;
  });
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
      <div
        style={{
          width: 10,
          height: 10,
          borderRadius: 10,
          background: color,
        }}
      />
      <span style={{ fontSize: 10, color: "var(--aunoo-muted-text)" }}>{label}</span>
    </div>
  );
}

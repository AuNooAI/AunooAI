import React from "react";
import type { EmergingTopic } from "./types";

interface WatchPanelProps {
  topics: EmergingTopic[];
  onSelectTopic: (topic: EmergingTopic) => void;
}

export function WatchPanel({ topics, onSelectTopic }: WatchPanelProps) {
  const highUrgency = topics.filter((t) => t.synthesis?.urgency === "high");
  const allWatchFor = highUrgency
    .flatMap((t) =>
      (t.signals?.watch_for ?? []).slice(0, 2).map((w) => ({ text: w, topic: t }))
    )
    .slice(0, 6);

  const actorTopics = topics.filter(
    (t) => t.velocity === "accelerating" || t.synthesis?.urgency === "high"
  );
  const actorRows: { name: string; topicName: string; topic: EmergingTopic }[] = [];
  for (const topic of actorTopics) {
    const names = [
      ...(topic.actors?.companies ?? []),
      ...(topic.actors?.people ?? []),
    ].slice(0, 2);
    for (const name of names) {
      if (actorRows.length >= 6) break;
      actorRows.push({ name, topicName: topic.name, topic });
    }
    if (actorRows.length >= 6) break;
  }

  return (
    <div
      style={{
        background: "var(--aunoo-surface)",
        border: `0.5px solid var(--aunoo-border)`,
        borderRadius: "var(--aunoo-radius-lg)",
        padding: "14px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 16,
      }}
    >
      {/* Actors */}
      <div>
        <p style={sectionTitle}>Key actors in play</p>
        {actorRows.length === 0 ? (
          <p style={emptyText}>No actor data</p>
        ) : (
          actorRows.map(({ name, topicName, topic }, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 6,
                cursor: "pointer",
              }}
              onClick={() => onSelectTopic(topic)}
            >
              <span
                style={{
                  fontSize: 11,
                  padding: "2px 8px",
                  borderRadius: 99,
                  background: "var(--aunoo-surface-secondary)",
                  border: `0.5px solid var(--aunoo-border)`,
                  color: "inherit",
                  whiteSpace: "nowrap",
                  flexShrink: 0,
                }}
              >
                {name}
              </span>
              <span
                style={{
                  fontSize: 10,
                  color: "var(--aunoo-muted-text)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={topicName}
              >
                {topicName}
              </span>
            </div>
          ))
        )}
      </div>

      {/* Divider */}
      <div style={{ height: "0.5px", background: "var(--aunoo-border)" }} />

      {/* Watch for */}
      <div>
        <p style={sectionTitle}>Watch for</p>
        {allWatchFor.length === 0 ? (
          <p style={emptyText}>No watch signals</p>
        ) : (
          allWatchFor.map(({ text, topic }, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                gap: 8,
                marginBottom: 7,
                cursor: "pointer",
                alignItems: "flex-start",
              }}
              onClick={() => onSelectTopic(topic)}
            >
              <div
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: "var(--aunoo-red)",
                  marginTop: 4,
                  flexShrink: 0,
                }}
              />
              <p
                style={{
                  fontSize: 11,
                  lineHeight: 1.5,
                  color: "inherit",
                  margin: 0,
                }}
              >
                {text}
              </p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

const sectionTitle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 500,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  color: "var(--aunoo-muted-text)",
  margin: "0 0 10px",
};

const emptyText: React.CSSProperties = {
  fontSize: 11,
  color: "var(--aunoo-muted-text)",
  margin: 0,
};

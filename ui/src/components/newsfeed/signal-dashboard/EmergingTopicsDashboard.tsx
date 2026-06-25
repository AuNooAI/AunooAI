import React, { useCallback, useEffect, useMemo, useState } from "react";
import * as ToggleGroup from "@radix-ui/react-toggle-group";
import * as Select from "@radix-ui/react-select";

import type { EmergingTopic, FilterMode, TopicCategory } from "./types";
import { deriveCategory, CATEGORY_LABELS } from "./utils";
import { SignalCard } from "./SignalCard";
import { TopicDetailPanel } from "./TopicDetailPanel";
import { TrajectoryPanel } from "./TrajectoryPanel";
import { WatchPanel } from "./WatchPanel";

interface EmergingTopicsDashboardProps {
  topics?: EmergingTopic[];
  apiUrl?: string;
  runDates?: string[];
}

export function EmergingTopicsDashboard({
  topics: topicsProp,
  apiUrl = "/api/emerging-topics/topics?status=active&limit=50",
  runDates: runDatesProp,
}: EmergingTopicsDashboardProps) {
  const [topics, setTopics] = useState<EmergingTopic[]>(topicsProp ?? []);
  const [loading, setLoading] = useState(!topicsProp);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterMode>("all");
  const [categoryFilter, setCategoryFilter] = useState<TopicCategory | "all">("all");
  const [selectedTopic, setSelectedTopic] = useState<EmergingTopic | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  // Sync with parent-provided topics
  useEffect(() => {
    if (topicsProp) {
      setTopics(topicsProp);
      setLoading(false);
      return;
    }
    setLoading(true);
    fetch(apiUrl, { credentials: "include" })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        // Handle both array response and { topics: [...] } wrapper
        const list = Array.isArray(data) ? data : (data.topics ?? data.emerging_topics ?? []);
        setTopics(list);
        setLoading(false);
      })
      .catch((e: Error) => { setError(e.message); setLoading(false); });
  }, [apiUrl, topicsProp]);

  const runDates = useMemo(() => {
    if (runDatesProp) return runDatesProp;
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date();
      d.setDate(d.getDate() - (6 - i));
      return d.toISOString().slice(0, 10);
    });
  }, [runDatesProp]);

  const filtered = useMemo(() => {
    let result = topics;
    if (filter === "accelerating") result = result.filter((t) => t.velocity === "accelerating");
    if (filter === "high_urgency") result = result.filter((t) => t.synthesis?.urgency === "high");
    if (categoryFilter !== "all")
      result = result.filter((t) => deriveCategory(t.topic_filter) === categoryFilter);
    return result;
  }, [topics, filter, categoryFilter]);

  const stats = useMemo(() => ({
    total: topics.length,
    accelerating: topics.filter((t) => t.velocity === "accelerating").length,
    highUrgency: topics.filter((t) => t.synthesis?.urgency === "high").length,
    newThisWeek: topics.filter((t) => {
      if (!t.first_detected_at) return false;
      const d = new Date(t.first_detected_at);
      const week = new Date(); week.setDate(week.getDate() - 7);
      return d >= week;
    }).length,
  }), [topics]);

  const openDetail = useCallback((topic: EmergingTopic) => {
    setSelectedTopic(topic);
    setDetailOpen(true);
  }, []);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;

  return (
    <div style={{ fontFamily: "var(--aunoo-font)", color: "inherit" }}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 16,
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <div>
          <p
            style={{
              fontSize: 11,
              fontWeight: 500,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              color: "var(--aunoo-muted-text)",
              margin: 0,
            }}
          >
            Emerging signals
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <CategorySelect value={categoryFilter} onChange={setCategoryFilter} />

          <ToggleGroup.Root
            type="single"
            value={filter}
            onValueChange={(v) => { if (v) setFilter(v as FilterMode); }}
            style={{ display: "flex", gap: 4 }}
          >
            {(
              [
                { value: "all", label: "All" },
                { value: "accelerating", label: "\u2191 Accelerating" },
                { value: "high_urgency", label: "High urgency" },
              ] as { value: FilterMode; label: string }[]
            ).map(({ value, label }) => (
              <ToggleGroup.Item
                key={value}
                value={value}
                style={{
                  all: "unset",
                  fontSize: 11,
                  padding: "4px 12px",
                  borderRadius: 99,
                  border: `0.5px solid var(--aunoo-border)`,
                  cursor: "pointer",
                  background:
                    filter === value
                      ? "var(--aunoo-muted-bg)"
                      : "transparent",
                  fontWeight: filter === value ? 500 : 400,
                  color: "inherit",
                  transition: "background 0.12s",
                  whiteSpace: "nowrap",
                }}
              >
                {label}
              </ToggleGroup.Item>
            ))}
          </ToggleGroup.Root>
        </div>
      </div>

      {/* Stat strip */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 10,
          marginBottom: 16,
        }}
      >
        <StatCard label="Active signals" value={stats.total} />
        <StatCard label="Accelerating" value={stats.accelerating} accent="var(--aunoo-green-text)" />
        <StatCard label="High urgency" value={stats.highUrgency} accent="var(--aunoo-red)" />
        <StatCard label="New this week" value={stats.newThisWeek} />
      </div>

      {/* Card grid */}
      {filtered.length === 0 ? (
        <div
          style={{
            padding: "40px 0",
            textAlign: "center",
            color: "var(--aunoo-muted-text)",
            fontSize: 13,
          }}
        >
          No topics match this filter.
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: 10,
            marginBottom: 16,
          }}
        >
          {filtered.map((topic) => (
            <SignalCard
              key={topic.id}
              topic={topic}
              isSelected={selectedTopic?.id === topic.id}
              onClick={() => openDetail(topic)}
            />
          ))}
        </div>
      )}

      {/* Bottom panels */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 320px",
          gap: 10,
        }}
      >
        <TrajectoryPanel
          topics={filtered.slice(0, 8)}
          runDates={runDates}
          onSelectTopic={openDetail}
        />
        <WatchPanel topics={filtered} onSelectTopic={openDetail} />
      </div>

      {/* Detail dialog */}
      <TopicDetailPanel
        topic={selectedTopic}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
      />

      {/* Keyframes */}
      <style>{`
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideUp {
          from { opacity: 0; transform: translate(-50%, calc(-50% + 12px)); }
          to   { opacity: 1; transform: translate(-50%, -50%); }
        }
      `}</style>
    </div>
  );
}

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: string;
}) {
  return (
    <div
      style={{
        background: "var(--aunoo-surface-secondary)",
        borderRadius: "var(--aunoo-radius-md)",
        padding: "10px 14px",
      }}
    >
      <p
        style={{
          fontSize: 10,
          color: "var(--aunoo-muted-text)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          margin: "0 0 3px",
          fontWeight: 500,
        }}
      >
        {label}
      </p>
      <p
        style={{
          fontSize: 22,
          fontWeight: 500,
          margin: 0,
          color: accent ?? "inherit",
        }}
      >
        {value}
      </p>
    </div>
  );
}

function CategorySelect({
  value,
  onChange,
}: {
  value: TopicCategory | "all";
  onChange: (v: TopicCategory | "all") => void;
}) {
  const options: { value: TopicCategory | "all"; label: string }[] = [
    { value: "all", label: "All categories" },
    ...(Object.entries(CATEGORY_LABELS) as [TopicCategory, string][]).map(
      ([k, v]) => ({ value: k, label: v })
    ),
  ];

  return (
    <Select.Root value={value} onValueChange={(v) => onChange(v as TopicCategory | "all")}>
      <Select.Trigger
        style={{
          all: "unset",
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          fontSize: 11,
          padding: "4px 10px",
          borderRadius: 99,
          border: `0.5px solid var(--aunoo-border)`,
          cursor: "pointer",
          background: "transparent",
          color: "inherit",
        }}
        aria-label="Filter by category"
      >
        <Select.Value />
        <Select.Icon>
          <ChevronDown />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          style={{
            background: "var(--aunoo-surface)",
            border: `0.5px solid var(--aunoo-border-hover)`,
            borderRadius: "var(--aunoo-radius-md)",
            padding: 4,
            boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
            zIndex: 300,
            minWidth: 200,
          }}
        >
          <Select.Viewport>
            {options.map((opt) => (
              <Select.Item
                key={opt.value}
                value={opt.value}
                style={{
                  fontSize: 12,
                  padding: "6px 10px",
                  borderRadius: "var(--aunoo-radius-sm)",
                  cursor: "pointer",
                  outline: "none",
                  color: "inherit",
                }}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.background = "var(--aunoo-muted-bg)")
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.background = "transparent")
                }
              >
                <Select.ItemText>{opt.label}</Select.ItemText>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}

function LoadingState() {
  return (
    <div
      style={{
        padding: "60px 0",
        textAlign: "center",
        color: "var(--aunoo-muted-text)",
        fontSize: 13,
      }}
    >
      Loading signals\u2026
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div
      style={{
        padding: "40px 0",
        textAlign: "center",
        color: "var(--aunoo-red-text)",
        fontSize: 13,
      }}
    >
      Failed to load topics: {message}
    </div>
  );
}

function ChevronDown() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 3.5L5 6.5L8 3.5" />
    </svg>
  );
}

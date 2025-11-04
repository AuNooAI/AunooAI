/**
 * Simplified App with inline styles for better compatibility
 */

import { useState } from 'react';
import { useTrendConvergence } from './hooks/useTrendConvergence';
import type { TrendConvergenceData } from './services/api';

// Simple button component with inline styles
const Button = ({ onClick, children, variant = 'primary', disabled = false }: any) => {
  const baseStyle: React.CSSProperties = {
    padding: '12px 24px',
    borderRadius: '8px',
    border: 'none',
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontSize: '16px',
    fontWeight: '600',
    transition: 'all 0.3s ease',
    opacity: disabled ? 0.6 : 1,
  };

  const variants = {
    primary: {
      background: 'linear-gradient(135deg, #FF69B4 0%, #FF1493 100%)',
      color: 'white',
    },
    secondary: {
      background: '#6c757d',
      color: 'white',
    },
    outline: {
      background: 'transparent',
      color: '#FF1493',
      border: '2px solid #FF1493',
    },
  };

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{ ...baseStyle, ...variants[variant as keyof typeof variants] }}
      onMouseOver={(e) => {
        if (!disabled) {
          (e.target as HTMLElement).style.transform = 'translateY(-2px)';
          (e.target as HTMLElement).style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.15)';
        }
      }}
      onMouseOut={(e) => {
        (e.target as HTMLElement).style.transform = 'translateY(0)';
        (e.target as HTMLElement).style.boxShadow = 'none';
      }}
    >
      {children}
    </button>
  );
};

// Navigation bar
function NavBar({ onConfigureClick }: { onConfigureClick: () => void }) {
  return (
    <div style={{
      background: 'rgba(255, 255, 255, 0.95)',
      borderBottom: '1px solid #e0e0e0',
      padding: '16px 24px',
      position: 'sticky',
      top: 0,
      zIndex: 50,
    }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: '18px', fontWeight: '600', color: '#333' }}>
          Trend Convergence Analysis
        </div>
        <Button onClick={onConfigureClick} variant="primary">
          ⚙️ Configure Analysis
        </Button>
      </div>
    </div>
  );
}

// Configuration Modal
function ConfigModal({ isOpen, onClose, config, topics, models, profiles, onUpdateConfig, onGenerate }: any) {
  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onGenerate();
    onClose();
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'white',
          borderRadius: '12px',
          maxWidth: '800px',
          width: '90%',
          maxHeight: '90vh',
          overflow: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <form onSubmit={handleSubmit}>
          {/* Header */}
          <div style={{ padding: '24px', borderBottom: '1px solid #e0e0e0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h2 style={{ fontSize: '24px', fontWeight: 'bold', color: '#333', margin: 0 }}>
                Configure Analysis
              </h2>
              <button
                type="button"
                onClick={onClose}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '24px',
                  cursor: 'pointer',
                  color: '#666',
                }}
              >
                ×
              </button>
            </div>
          </div>

          {/* Body */}
          <div style={{ padding: '24px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              {/* Topic */}
              <div>
                <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500' }}>Topic *</label>
                <select
                  value={config.topic}
                  onChange={(e) => onUpdateConfig({ topic: e.target.value })}
                  required
                  style={{
                    width: '100%',
                    padding: '8px',
                    borderRadius: '6px',
                    border: '1px solid #ccc',
                    fontSize: '14px',
                  }}
                >
                  <option value="">Select a topic...</option>
                  {topics.map((topic: any) => (
                    <option key={topic.name} value={topic.name}>
                      {topic.display_name || topic.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Model */}
              <div>
                <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500' }}>AI Model *</label>
                <select
                  value={config.model}
                  onChange={(e) => onUpdateConfig({ model: e.target.value })}
                  required
                  style={{
                    width: '100%',
                    padding: '8px',
                    borderRadius: '6px',
                    border: '1px solid #ccc',
                    fontSize: '14px',
                  }}
                >
                  <option value="">Select model...</option>
                  {models.map((model: any) => (
                    <option key={model.id} value={model.id}>
                      {model.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Timeframe */}
              <div>
                <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500' }}>Timeframe</label>
                <select
                  value={config.timeframe_days}
                  onChange={(e) => onUpdateConfig({ timeframe_days: parseInt(e.target.value) })}
                  style={{
                    width: '100%',
                    padding: '8px',
                    borderRadius: '6px',
                    border: '1px solid #ccc',
                    fontSize: '14px',
                  }}
                >
                  <option value="30">Last 30 Days</option>
                  <option value="90">Last 90 Days</option>
                  <option value="180">Last 180 Days</option>
                  <option value="365">Last 365 Days</option>
                </select>
              </div>

              {/* Analysis Depth */}
              <div>
                <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500' }}>Analysis Depth</label>
                <select
                  value={config.analysis_depth}
                  onChange={(e) => onUpdateConfig({ analysis_depth: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '8px',
                    borderRadius: '6px',
                    border: '1px solid #ccc',
                    fontSize: '14px',
                  }}
                >
                  <option value="standard">Standard</option>
                  <option value="detailed">Detailed</option>
                  <option value="comprehensive">Comprehensive</option>
                </select>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div style={{ padding: '24px', borderTop: '1px solid #e0e0e0', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
            <Button type="button" onClick={onClose} variant="secondary">
              Cancel
            </Button>
            <Button type="submit" variant="primary">
              Generate Analysis
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Loading State
function LoadingState() {
  return (
    <div style={{ textAlign: 'center', padding: '60px 20px' }}>
      <div style={{
        width: '60px',
        height: '60px',
        border: '4px solid #f0f0f0',
        borderTop: '4px solid #FF1493',
        borderRadius: '50%',
        animation: 'spin 1s linear infinite',
        margin: '0 auto 20px',
      }} />
      <p style={{ fontSize: '18px', color: '#666' }}>Generating trend convergence analysis...</p>
      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

// Empty State
function EmptyState({ onConfigureClick }: { onConfigureClick: () => void }) {
  return (
    <div style={{ textAlign: 'center', padding: '80px 20px' }}>
      <div style={{ fontSize: '72px', marginBottom: '20px' }}>📊</div>
      <h3 style={{ fontSize: '28px', fontWeight: '600', color: '#333', marginBottom: '12px' }}>
        No Analysis Generated Yet
      </h3>
      <p style={{ fontSize: '16px', color: '#666', marginBottom: '24px' }}>
        Configure your analysis parameters and generate insights
      </p>
      <Button onClick={onConfigureClick} variant="primary">
        🚀 Configure Analysis
      </Button>
    </div>
  );
}

// Strategic Recommendations
function StrategicRecommendations({ data }: { data: TrendConvergenceData }) {
  if (!data.strategic_recommendations) return null;

  const { near_term, mid_term, long_term } = data.strategic_recommendations;

  const TimelineCard = ({ title, trends, gradient }: any) => (
    <div style={{
      flex: 1,
      background: gradient,
      borderRadius: '12px',
      padding: '20px',
      color: 'white',
      minHeight: '200px',
    }}>
      <h3 style={{ fontSize: '16px', fontWeight: 'bold', marginBottom: '16px', borderBottom: '2px solid rgba(255,255,255,0.3)', paddingBottom: '8px' }}>
        {title}
      </h3>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {trends.map((trend: any, idx: number) => {
          const text = typeof trend === 'string' ? trend : trend.name || trend.description;
          return (
            <li key={idx} style={{ marginBottom: '12px', paddingLeft: '16px', position: 'relative', fontSize: '14px', lineHeight: '1.5' }}>
              <span style={{ position: 'absolute', left: 0 }}>•</span>
              {text}
            </li>
          );
        })}
      </ul>
    </div>
  );

  return (
    <div style={{ background: 'white', borderRadius: '12px', padding: '24px', marginBottom: '24px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
      <h2 style={{ fontSize: '28px', fontWeight: 'bold', marginBottom: '8px', color: '#333' }}>
        Strategic Recommendations
      </h2>
      <p style={{ color: '#666', marginBottom: '24px' }}>Evidence-based action plan for executive leadership</p>

      <div style={{ display: 'flex', gap: '16px' }}>
        <TimelineCard
          title="NEAR-TERM (2025-2027)"
          trends={near_term.trends}
          gradient="linear-gradient(135deg, #FF69B4 0%, #FF1493 100%)"
        />
        <TimelineCard
          title="MID-TERM (2027-2032)"
          trends={mid_term.trends}
          gradient="linear-gradient(135deg, #FF69B4 0%, #8A2BE2 100%)"
        />
        <TimelineCard
          title="LONG-TERM (2032+)"
          trends={long_term.trends}
          gradient="linear-gradient(135deg, #8A2BE2 0%, #4B0082 100%)"
        />
      </div>
    </div>
  );
}

// Executive Framework
function ExecutiveFramework({ data }: { data: TrendConvergenceData }) {
  if (!data.executive_decision_framework?.principles) return null;

  return (
    <div style={{ background: 'white', borderRadius: '12px', padding: '24px', marginBottom: '24px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
      <h2 style={{ fontSize: '28px', fontWeight: 'bold', marginBottom: '24px', color: '#333' }}>
        Executive Decision Framework
      </h2>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
        {data.executive_decision_framework.principles.map((principle, idx) => {
          const title = principle.title || principle.name || `Principle ${idx + 1}`;
          const description = principle.description || principle.content || '';

          return (
            <div
              key={idx}
              style={{
                borderLeft: '4px solid #FF1493',
                background: '#f8f9fa',
                padding: '16px',
                borderRadius: '0 8px 8px 0',
              }}
            >
              <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#333', marginBottom: '8px' }}>{title}</h3>
              <p style={{ fontSize: '14px', color: '#666', margin: 0 }}>{description}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Next Steps
function NextSteps({ data }: { data: TrendConvergenceData }) {
  if (!data.next_steps || data.next_steps.length === 0) return null;

  return (
    <div style={{ background: 'white', borderRadius: '12px', padding: '24px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
      <h2 style={{ fontSize: '28px', fontWeight: 'bold', marginBottom: '24px', color: '#333' }}>
        Next Steps
      </h2>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {data.next_steps.map((step, idx) => (
          <div
            key={idx}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '12px',
              padding: '16px',
              background: '#f8f9fa',
              borderRadius: '8px',
            }}
          >
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #FF69B4 0%, #FF1493 100%)',
              color: 'white',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 'bold',
              flexShrink: 0,
            }}>
              {idx + 1}
            </div>
            <p style={{ margin: 0, fontSize: '15px', color: '#333', lineHeight: '1.6' }}>{step}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// Main App
export default function App() {
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const { data, topics, profiles, models, config, loading, error, generateAnalysis, updateConfig, clearError } = useTrendConvergence();

  const handleGenerate = async () => {
    await generateAnalysis();
  };

  return (
    <div style={{ minHeight: '100vh', background: '#f5f5f5' }}>
      <NavBar onConfigureClick={() => setIsConfigOpen(true)} />

      <main style={{ maxWidth: '1200px', margin: '0 auto', padding: '32px 24px' }}>
        {/* Error Display */}
        {error && (
          <div style={{
            background: '#fee',
            border: '1px solid #fcc',
            borderRadius: '8px',
            padding: '16px',
            marginBottom: '24px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'start',
          }}>
            <div>
              <h4 style={{ color: '#c00', fontWeight: '600', marginBottom: '4px' }}>Error</h4>
              <p style={{ color: '#a00', margin: 0 }}>{error}</p>
            </div>
            <button
              onClick={clearError}
              style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: '#c00' }}
            >
              ×
            </button>
          </div>
        )}

        {/* Content */}
        {loading ? (
          <LoadingState />
        ) : data ? (
          <>
            <StrategicRecommendations data={data} />
            <ExecutiveFramework data={data} />
            <NextSteps data={data} />
          </>
        ) : (
          <EmptyState onConfigureClick={() => setIsConfigOpen(true)} />
        )}
      </main>

      {/* Configuration Modal */}
      <ConfigModal
        isOpen={isConfigOpen}
        onClose={() => setIsConfigOpen(false)}
        config={config}
        topics={topics}
        models={models}
        profiles={profiles}
        onUpdateConfig={updateConfig}
        onGenerate={handleGenerate}
      />
    </div>
  );
}

-- Create organizational profiles table for trend convergence analysis
CREATE TABLE IF NOT EXISTS organizational_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    industry TEXT,
    organization_type TEXT, -- publisher, enterprise, startup, government, etc.
    region TEXT, -- global, north_america, europe, asia_pacific, etc.
    key_concerns TEXT, -- JSON array of key concerns
    strategic_priorities TEXT, -- JSON array of strategic priorities  
    risk_tolerance TEXT, -- high, medium, low
    innovation_appetite TEXT, -- conservative, moderate, aggressive
    decision_making_style TEXT, -- data-driven, collaborative, hierarchical, agile
    stakeholder_focus TEXT, -- JSON array of key stakeholders
    competitive_landscape TEXT, -- JSON array of key competitors/market dynamics
    regulatory_environment TEXT, -- JSON array of key regulations/compliance needs
    custom_context TEXT, -- Additional custom context
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_default BOOLEAN DEFAULT FALSE
);

-- Insert default Wiley scientific publisher profile
INSERT INTO organizational_profiles (
    name,
    description,
    industry,
    organization_type,
    region,
    key_concerns,
    strategic_priorities,
    risk_tolerance,
    innovation_appetite,
    decision_making_style,
    stakeholder_focus,
    competitive_landscape,
    regulatory_environment,
    custom_context,
    is_default
) VALUES (
    'Wiley Scientific Publisher',
    'Leading global research and education publisher focusing on scientific, technical, and medical content',
    'Academic Publishing',
    'publisher',
    'global',
    '["R&D funding sustainability", "Open research initiatives", "Peer review system integrity", "Copyright protection", "AI impact on publishing", "Academic workflow disruption", "Content authenticity", "Author relationships"]',
    '["Maintain editorial excellence", "Embrace digital transformation", "Support open science", "Protect intellectual property", "Foster researcher community", "Ensure content quality", "Drive innovation in scholarly communication"]',
    'medium',
    'moderate',
    'collaborative',
    '["Academic researchers", "Institutional subscribers", "Authors", "Editorial boards", "Academic libraries", "Grant funding bodies", "University administrators"]',
    '["Elsevier", "Springer Nature", "SAGE", "Taylor & Francis", "Open access publishers", "Preprint servers", "AI content generators", "Academic databases"]',
    '["Copyright law", "Open access mandates", "Data privacy regulations (GDPR)", "Academic integrity standards", "Funder open access requirements", "AI content policies", "Export control regulations"]',
    'Focus on balancing traditional publishing excellence with emerging digital and AI technologies while maintaining trust in scholarly communication',
    TRUE
);

-- Insert generic enterprise profile
INSERT INTO organizational_profiles (
    name,
    description,
    industry,
    organization_type,
    region,
    key_concerns,
    strategic_priorities,
    risk_tolerance,
    innovation_appetite,
    decision_making_style,
    stakeholder_focus,
    competitive_landscape,
    regulatory_environment,
    custom_context,
    is_default
) VALUES (
    'Generic Enterprise',
    'Large enterprise organization focused on sustainable growth and competitive advantage',
    'General',
    'enterprise',
    'global',
    '["Market competition", "Digital transformation", "Regulatory compliance", "Talent retention", "Customer satisfaction", "Operational efficiency", "Cybersecurity", "Supply chain resilience"]',
    '["Revenue growth", "Market expansion", "Innovation leadership", "Operational excellence", "Customer centricity", "Employee engagement", "Sustainability", "Risk management"]',
    'medium',
    'moderate',
    'data-driven',
    '["Shareholders", "Customers", "Employees", "Partners", "Regulators", "Board of directors", "Community stakeholders"]',
    '["Industry leaders", "Emerging competitors", "Technology disruptors", "Global market players", "Startup innovators"]',
    '["Industry-specific regulations", "Data protection laws", "Environmental standards", "Labor regulations", "Financial compliance", "International trade rules"]',
    'Balanced approach to growth and innovation while maintaining operational stability and regulatory compliance',
    FALSE
);

-- Insert cybersecurity organization profile
INSERT INTO organizational_profiles (
    name,
    description,
    industry,
    organization_type,
    region,
    key_concerns,
    strategic_priorities,
    risk_tolerance,
    innovation_appetite,
    decision_making_style,
    stakeholder_focus,
    competitive_landscape,
    regulatory_environment,
    custom_context,
    is_default
) VALUES (
    'Cybersecurity Organization',
    'Security and risk management team focused on protecting digital assets and infrastructure',
    'Cybersecurity',
    'security_team',
    'global',
    '["Advanced persistent threats", "Zero-day vulnerabilities", "Data breaches", "Compliance violations", "Insider threats", "Supply chain attacks", "Cloud security", "AI-powered attacks", "Ransomware", "Privacy violations"]',
    '["Threat prevention", "Incident response", "Security awareness", "Regulatory compliance", "Risk mitigation", "Security architecture", "Threat intelligence", "Business continuity", "Privacy protection"]',
    'low',
    'conservative',
    'data-driven',
    '["C-suite executives", "IT teams", "Business units", "Compliance teams", "External auditors", "Law enforcement", "Incident response teams", "Security vendors"]',
    '["Nation-state actors", "Cybercriminal groups", "Insider threats", "Competing security vendors", "Threat intelligence providers", "Managed security services"]',
    '["GDPR", "SOX", "HIPAA", "PCI DSS", "ISO 27001", "NIST Framework", "Industry-specific regulations", "Data localization laws", "Breach notification requirements"]',
    'Zero-trust security approach with emphasis on proactive threat detection, rapid response, and continuous compliance monitoring',
    TRUE
);

-- Insert financial institution profile
INSERT INTO organizational_profiles (
    name,
    description,
    industry,
    organization_type,
    region,
    key_concerns,
    strategic_priorities,
    risk_tolerance,
    innovation_appetite,
    decision_making_style,
    stakeholder_focus,
    competitive_landscape,
    regulatory_environment,
    custom_context,
    is_default
) VALUES (
    'Financial Institution',
    'Banking and financial services organization focused on customer service and regulatory compliance',
    'Financial Services',
    'bank',
    'north_america',
    '["Regulatory compliance", "Credit risk", "Market volatility", "Cybersecurity threats", "Digital transformation", "Customer trust", "Interest rate changes", "Economic uncertainty", "Fintech disruption", "Anti-money laundering"]',
    '["Customer satisfaction", "Digital innovation", "Risk management", "Regulatory compliance", "Operational efficiency", "Market share growth", "Profitability", "ESG initiatives", "Technology modernization"]',
    'low',
    'conservative',
    'hierarchical',
    '["Customers", "Regulators", "Shareholders", "Employees", "Credit rating agencies", "Central banks", "Government agencies", "Community leaders"]',
    '["Traditional banks", "Credit unions", "Fintech startups", "Big Tech companies", "Payment processors", "Investment firms", "Insurance companies"]',
    '["Basel III", "Dodd-Frank", "GDPR", "PCI DSS", "SOX", "Anti-Money Laundering laws", "Consumer protection regulations", "Stress testing requirements", "Capital adequacy rules"]',
    'Conservative approach to innovation balanced with regulatory compliance and customer protection, emphasizing trust and stability',
    TRUE
);

-- Insert insurance company profile
INSERT INTO organizational_profiles (
    name,
    description,
    industry,
    organization_type,
    region,
    key_concerns,
    strategic_priorities,
    risk_tolerance,
    innovation_appetite,
    decision_making_style,
    stakeholder_focus,
    competitive_landscape,
    regulatory_environment,
    custom_context,
    is_default
) VALUES (
    'Insurance Company',
    'Insurance provider focused on risk assessment, claims management, and customer service',
    'Insurance',
    'insurer',
    'europe',
    '["Catastrophic events", "Fraudulent claims", "Regulatory changes", "Market competition", "Climate change risks", "Underwriting accuracy", "Customer retention", "Technology disruption", "Investment performance", "Operational costs"]',
    '["Risk assessment accuracy", "Claims efficiency", "Customer experience", "Digital transformation", "Regulatory compliance", "Profitability", "Market expansion", "Innovation in products", "ESG compliance"]',
    'medium',
    'moderate',
    'collaborative',
    '["Policyholders", "Regulators", "Shareholders", "Agents/Brokers", "Reinsurers", "Claims adjusters", "Healthcare providers", "Automotive industry", "Government agencies"]',
    '["Traditional insurers", "Insurtech startups", "Direct writers", "Mutual companies", "Reinsurers", "Self-insurance programs", "Alternative risk transfer mechanisms"]',
    '["Solvency II", "GDPR", "Insurance regulatory frameworks", "Consumer protection laws", "Anti-fraud regulations", "Climate disclosure requirements", "Data protection laws"]',
    'Balanced approach to innovation and tradition, leveraging data analytics for improved risk assessment while maintaining strong regulatory compliance',
    TRUE
);

-- Insert manufacturing company profile
INSERT INTO organizational_profiles (
    name,
    description,
    industry,
    organization_type,
    region,
    key_concerns,
    strategic_priorities,
    risk_tolerance,
    innovation_appetite,
    decision_making_style,
    stakeholder_focus,
    competitive_landscape,
    regulatory_environment,
    custom_context,
    is_default
) VALUES (
    'Manufacturing Company',
    'Industrial manufacturing organization focused on production efficiency and supply chain management',
    'Manufacturing',
    'manufacturer',
    'asia_pacific',
    '["Supply chain disruptions", "Raw material costs", "Production efficiency", "Quality control", "Environmental regulations", "Workforce safety", "Technology adoption", "Global competition", "Sustainability requirements", "Trade policies"]',
    '["Operational excellence", "Quality improvement", "Cost reduction", "Innovation in processes", "Sustainability", "Market expansion", "Digital transformation", "Workforce development", "Customer satisfaction"]',
    'medium',
    'moderate',
    'hierarchical',
    '["Customers", "Suppliers", "Employees", "Regulators", "Shareholders", "Local communities", "Trade unions", "Industry associations", "Environmental groups"]',
    '["Global manufacturers", "Local competitors", "Low-cost producers", "Technology disruptors", "Automation providers", "Alternative materials", "Direct-to-consumer brands"]',
    '["Environmental regulations", "Safety standards", "Quality certifications", "Trade regulations", "Labor laws", "Export controls", "Industry-specific standards", "Carbon emission requirements"]',
    'Focus on lean manufacturing principles, continuous improvement, and sustainable practices while adapting to Industry 4.0 technologies',
    TRUE
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_org_profiles_name ON organizational_profiles(name);
CREATE INDEX IF NOT EXISTS idx_org_profiles_industry ON organizational_profiles(industry);
CREATE INDEX IF NOT EXISTS idx_org_profiles_default ON organizational_profiles(is_default);
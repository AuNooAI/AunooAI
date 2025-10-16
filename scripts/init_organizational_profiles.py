#!/usr/bin/env python3
"""
Initialize organizational profiles for both SQLite and PostgreSQL.

This script creates default organizational profiles directly in the database
without requiring migration from SQLite.

Usage:
    python scripts/init_organizational_profiles.py [--clear]
"""

import sys
import os
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add the app directory to Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
env_path = project_root / '.env'
load_dotenv(env_path)

# Default organizational profiles
DEFAULT_PROFILES = [
    {
        'name': 'Wiley Scientific Publisher',
        'description': 'Leading global research and education publisher focusing on scientific, technical, and medical content',
        'industry': 'Academic Publishing',
        'organization_type': 'publisher',
        'region': 'global',
        'key_concerns': '["R&D funding sustainability", "Open research initiatives", "Peer review system integrity", "Copyright protection", "AI impact on publishing", "Academic workflow disruption", "Content authenticity", "Author relationships"]',
        'strategic_priorities': '["Maintain editorial excellence", "Embrace digital transformation", "Support open science", "Protect intellectual property", "Foster researcher community", "Ensure content quality", "Drive innovation in scholarly communication"]',
        'risk_tolerance': 'medium',
        'innovation_appetite': 'moderate',
        'decision_making_style': 'collaborative',
        'stakeholder_focus': '["Academic researchers", "Institutional subscribers", "Authors", "Editorial boards", "Academic libraries", "Grant funding bodies", "University administrators"]',
        'competitive_landscape': '["Elsevier", "Springer Nature", "SAGE", "Taylor & Francis", "Open access publishers", "Preprint servers", "AI content generators", "Academic databases"]',
        'regulatory_environment': '["Copyright law", "Open access mandates", "Data privacy regulations (GDPR)", "Academic integrity standards", "Funder open access requirements", "AI content policies", "Export control regulations"]',
        'custom_context': 'Focus on balancing traditional publishing excellence with emerging digital and AI technologies while maintaining trust in scholarly communication',
        'is_default': True
    },
    {
        'name': 'Generic Enterprise',
        'description': 'Large enterprise organization focused on sustainable growth and competitive advantage',
        'industry': 'General',
        'organization_type': 'enterprise',
        'region': 'global',
        'key_concerns': '["Market competition", "Digital transformation", "Regulatory compliance", "Talent retention", "Customer satisfaction", "Operational efficiency", "Cybersecurity", "Supply chain resilience"]',
        'strategic_priorities': '["Revenue growth", "Market expansion", "Innovation leadership", "Operational excellence", "Customer centricity", "Employee engagement", "Sustainability", "Risk management"]',
        'risk_tolerance': 'medium',
        'innovation_appetite': 'moderate',
        'decision_making_style': 'data-driven',
        'stakeholder_focus': '["Shareholders", "Customers", "Employees", "Partners", "Regulators", "Board of directors", "Community stakeholders"]',
        'competitive_landscape': '["Industry leaders", "Emerging competitors", "Technology disruptors", "Global market players", "Startup innovators"]',
        'regulatory_environment': '["Industry-specific regulations", "Data protection laws", "Environmental standards", "Labor regulations", "Financial compliance", "International trade rules"]',
        'custom_context': 'Balanced approach to growth and innovation while maintaining operational stability and regulatory compliance',
        'is_default': False
    },
    {
        'name': 'Cybersecurity Organization',
        'description': 'Security and risk management team focused on protecting digital assets and infrastructure',
        'industry': 'Cybersecurity',
        'organization_type': 'security_team',
        'region': 'global',
        'key_concerns': '["Advanced persistent threats", "Zero-day vulnerabilities", "Data breaches", "Compliance violations", "Insider threats", "Supply chain attacks", "Cloud security", "AI-powered attacks", "Ransomware", "Privacy violations"]',
        'strategic_priorities': '["Threat prevention", "Incident response", "Security awareness", "Regulatory compliance", "Risk mitigation", "Security architecture", "Threat intelligence", "Business continuity", "Privacy protection"]',
        'risk_tolerance': 'low',
        'innovation_appetite': 'conservative',
        'decision_making_style': 'data-driven',
        'stakeholder_focus': '["C-suite executives", "IT teams", "Business units", "Compliance teams", "External auditors", "Law enforcement", "Incident response teams", "Security vendors"]',
        'competitive_landscape': '["Nation-state actors", "Cybercriminal groups", "Insider threats", "Competing security vendors", "Threat intelligence providers", "Managed security services"]',
        'regulatory_environment': '["GDPR", "SOX", "HIPAA", "PCI DSS", "ISO 27001", "NIST Framework", "Industry-specific regulations", "Data localization laws", "Breach notification requirements"]',
        'custom_context': 'Zero-trust security approach with emphasis on proactive threat detection, rapid response, and continuous compliance monitoring',
        'is_default': True
    },
    {
        'name': 'Financial Institution',
        'description': 'Banking and financial services organization focused on customer service and regulatory compliance',
        'industry': 'Financial Services',
        'organization_type': 'bank',
        'region': 'north_america',
        'key_concerns': '["Regulatory compliance", "Credit risk", "Market volatility", "Cybersecurity threats", "Digital transformation", "Customer trust", "Interest rate changes", "Economic uncertainty", "Fintech disruption", "Anti-money laundering"]',
        'strategic_priorities': '["Customer satisfaction", "Digital innovation", "Risk management", "Regulatory compliance", "Operational efficiency", "Market share growth", "Profitability", "ESG initiatives", "Technology modernization"]',
        'risk_tolerance': 'low',
        'innovation_appetite': 'conservative',
        'decision_making_style': 'hierarchical',
        'stakeholder_focus': '["Customers", "Regulators", "Shareholders", "Employees", "Credit rating agencies", "Central banks", "Government agencies", "Community leaders"]',
        'competitive_landscape': '["Traditional banks", "Credit unions", "Fintech startups", "Big Tech companies", "Payment processors", "Investment firms", "Insurance companies"]',
        'regulatory_environment': '["Basel III", "Dodd-Frank", "GDPR", "PCI DSS", "SOX", "Anti-Money Laundering laws", "Consumer protection regulations", "Stress testing requirements", "Capital adequacy rules"]',
        'custom_context': 'Conservative approach to innovation balanced with regulatory compliance and customer protection, emphasizing trust and stability',
        'is_default': True
    },
    {
        'name': 'Insurance Company',
        'description': 'Insurance provider focused on risk assessment, claims management, and customer service',
        'industry': 'Insurance',
        'organization_type': 'insurer',
        'region': 'europe',
        'key_concerns': '["Catastrophic events", "Fraudulent claims", "Regulatory changes", "Market competition", "Climate change risks", "Underwriting accuracy", "Customer retention", "Technology disruption", "Investment performance", "Operational costs"]',
        'strategic_priorities': '["Risk assessment accuracy", "Claims efficiency", "Customer experience", "Digital transformation", "Regulatory compliance", "Profitability", "Market expansion", "Innovation in products", "ESG compliance"]',
        'risk_tolerance': 'medium',
        'innovation_appetite': 'moderate',
        'decision_making_style': 'collaborative',
        'stakeholder_focus': '["Policyholders", "Regulators", "Shareholders", "Agents/Brokers", "Reinsurers", "Claims adjusters", "Healthcare providers", "Automotive industry", "Government agencies"]',
        'competitive_landscape': '["Traditional insurers", "Insurtech startups", "Direct writers", "Mutual companies", "Reinsurers", "Self-insurance programs", "Alternative risk transfer mechanisms"]',
        'regulatory_environment': '["Solvency II", "GDPR", "Insurance regulatory frameworks", "Consumer protection laws", "Anti-fraud regulations", "Climate disclosure requirements", "Data protection laws"]',
        'custom_context': 'Balanced approach to innovation and tradition, leveraging data analytics for improved risk assessment while maintaining strong regulatory compliance',
        'is_default': True
    },
    {
        'name': 'Manufacturing Company',
        'description': 'Industrial manufacturing organization focused on production efficiency and supply chain management',
        'industry': 'Manufacturing',
        'organization_type': 'manufacturer',
        'region': 'asia_pacific',
        'key_concerns': '["Supply chain disruptions", "Raw material costs", "Production efficiency", "Quality control", "Environmental regulations", "Workforce safety", "Technology adoption", "Global competition", "Sustainability requirements", "Trade policies"]',
        'strategic_priorities': '["Operational excellence", "Quality improvement", "Cost reduction", "Innovation in processes", "Sustainability", "Market expansion", "Digital transformation", "Workforce development", "Customer satisfaction"]',
        'risk_tolerance': 'medium',
        'innovation_appetite': 'moderate',
        'decision_making_style': 'hierarchical',
        'stakeholder_focus': '["Customers", "Suppliers", "Employees", "Regulators", "Shareholders", "Local communities", "Trade unions", "Industry associations", "Environmental groups"]',
        'competitive_landscape': '["Global manufacturers", "Local competitors", "Low-cost producers", "Technology disruptors", "Automation providers", "Alternative materials", "Direct-to-consumer brands"]',
        'regulatory_environment': '["Environmental regulations", "Safety standards", "Quality certifications", "Trade regulations", "Labor laws", "Export controls", "Industry-specific standards", "Carbon emission requirements"]',
        'custom_context': 'Focus on lean manufacturing principles, continuous improvement, and sustainable practices while adapting to Industry 4.0 technologies',
        'is_default': True
    }
]


def init_profiles_sqlite(clear_existing=False):
    """Initialize organizational profiles in SQLite."""
    import sqlite3

    db_path = project_root / 'app' / 'data' / 'fnaapp.db'

    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Create table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS organizational_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                industry TEXT,
                organization_type TEXT,
                region TEXT,
                key_concerns TEXT,
                strategic_priorities TEXT,
                risk_tolerance TEXT,
                innovation_appetite TEXT,
                decision_making_style TEXT,
                stakeholder_focus TEXT,
                competitive_landscape TEXT,
                regulatory_environment TEXT,
                custom_context TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_default BOOLEAN DEFAULT FALSE
            )
        """)

        if clear_existing:
            cursor.execute("DELETE FROM organizational_profiles")
            print("✅ Cleared existing profiles")

        # Insert or update profiles
        for profile in DEFAULT_PROFILES:
            cursor.execute(
                """
                INSERT INTO organizational_profiles (
                    name, description, industry, organization_type, region,
                    key_concerns, strategic_priorities, risk_tolerance,
                    innovation_appetite, decision_making_style, stakeholder_focus,
                    competitive_landscape, regulatory_environment, custom_context, is_default
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    description = excluded.description,
                    industry = excluded.industry,
                    organization_type = excluded.organization_type,
                    region = excluded.region,
                    key_concerns = excluded.key_concerns,
                    strategic_priorities = excluded.strategic_priorities,
                    risk_tolerance = excluded.risk_tolerance,
                    innovation_appetite = excluded.innovation_appetite,
                    decision_making_style = excluded.decision_making_style,
                    stakeholder_focus = excluded.stakeholder_focus,
                    competitive_landscape = excluded.competitive_landscape,
                    regulatory_environment = excluded.regulatory_environment,
                    custom_context = excluded.custom_context,
                    is_default = excluded.is_default,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    profile['name'], profile['description'], profile['industry'],
                    profile['organization_type'], profile['region'], profile['key_concerns'],
                    profile['strategic_priorities'], profile['risk_tolerance'],
                    profile['innovation_appetite'], profile['decision_making_style'],
                    profile['stakeholder_focus'], profile['competitive_landscape'],
                    profile['regulatory_environment'], profile['custom_context'],
                    profile['is_default']
                )
            )

        conn.commit()

        # Verify
        cursor.execute("SELECT COUNT(*) FROM organizational_profiles")
        count = cursor.fetchone()[0]

        conn.close()
        return count

    except Exception as e:
        conn.close()
        raise e


def init_profiles_postgresql(clear_existing=False):
    """Initialize organizational profiles in PostgreSQL."""
    import psycopg2
    from psycopg2.extras import execute_values

    # PostgreSQL connection details from environment
    pg_conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
    pg_cursor = pg_conn.cursor()

    try:
        if clear_existing:
            pg_cursor.execute("DELETE FROM organizational_profiles")
            pg_conn.commit()
            print("✅ Cleared existing profiles")

        # Insert or update profiles using UPSERT
        for profile in DEFAULT_PROFILES:
            pg_cursor.execute(
                """
                INSERT INTO organizational_profiles (
                    name, description, industry, organization_type, region,
                    key_concerns, strategic_priorities, risk_tolerance,
                    innovation_appetite, decision_making_style, stakeholder_focus,
                    competitive_landscape, regulatory_environment, custom_context, is_default
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    description = EXCLUDED.description,
                    industry = EXCLUDED.industry,
                    organization_type = EXCLUDED.organization_type,
                    region = EXCLUDED.region,
                    key_concerns = EXCLUDED.key_concerns,
                    strategic_priorities = EXCLUDED.strategic_priorities,
                    risk_tolerance = EXCLUDED.risk_tolerance,
                    innovation_appetite = EXCLUDED.innovation_appetite,
                    decision_making_style = EXCLUDED.decision_making_style,
                    stakeholder_focus = EXCLUDED.stakeholder_focus,
                    competitive_landscape = EXCLUDED.competitive_landscape,
                    regulatory_environment = EXCLUDED.regulatory_environment,
                    custom_context = EXCLUDED.custom_context,
                    is_default = EXCLUDED.is_default,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    profile['name'], profile['description'], profile['industry'],
                    profile['organization_type'], profile['region'], profile['key_concerns'],
                    profile['strategic_priorities'], profile['risk_tolerance'],
                    profile['innovation_appetite'], profile['decision_making_style'],
                    profile['stakeholder_focus'], profile['competitive_landscape'],
                    profile['regulatory_environment'], profile['custom_context'],
                    profile['is_default']
                )
            )

        pg_conn.commit()

        # Verify
        pg_cursor.execute("SELECT COUNT(*) FROM organizational_profiles")
        count = pg_cursor.fetchone()[0]

        pg_conn.close()
        return count

    except Exception as e:
        pg_conn.close()
        raise e


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Initialize organizational profiles (SQLite or PostgreSQL)"
    )
    parser.add_argument("--clear", action="store_true", help="Clear existing profiles before initialization")
    args = parser.parse_args()

    print("=" * 70)
    print("AuNoo AI - Organizational Profiles Initialization")
    print("=" * 70)
    print()

    # Detect database type
    db_type = os.getenv('DB_TYPE', 'sqlite').lower()

    print(f"Database type: {db_type.upper()}")
    print(f"Profiles to initialize: {len(DEFAULT_PROFILES)}")

    if args.clear:
        print("⚠️  Clearing existing profiles")

    print()

    try:
        if db_type == 'postgresql':
            print("📊 Initializing profiles in PostgreSQL...")
            count = init_profiles_postgresql(clear_existing=args.clear)
        else:
            print("📊 Initializing profiles in SQLite...")
            count = init_profiles_sqlite(clear_existing=args.clear)

        print(f"\n✅ Successfully initialized {count} organizational profiles")

        # Show summary
        print("\n📋 Initialized profiles:")
        for idx, profile in enumerate(DEFAULT_PROFILES, 1):
            default_marker = " (default)" if profile['is_default'] else ""
            print(f"  {idx}. {profile['name']} - {profile['industry']} • {profile['region']}{default_marker}")

        print("\n🎉 Initialization completed successfully!")
        print("\nNext steps:")
        print("1. Restart your AuNoo AI application")
        print("2. Navigate to News Feed → Profile → Manage Profiles")
        print("3. Select an organizational profile for your analysis")

        return 0

    except ImportError as e:
        print(f"❌ Required package not installed: {e}")
        if 'psycopg2' in str(e):
            print("Please install: pip install psycopg2-binary")
        return 1
    except Exception as e:
        print(f"❌ Initialization error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

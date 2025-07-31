#!/usr/bin/env python3
"""
Migration script to add organizational profiles table to existing installations.
Run this script from the project root directory: python scripts/migrate_organizational_profiles.py
"""

import sys
import os
import sqlite3
from pathlib import Path

# Add the app directory to Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def run_migration():
    """Run the organizational profiles migration."""
    
    # Define database path
    db_path = project_root / 'app' / 'data' / 'fnaapp.db'
    migration_file = project_root / 'app' / 'database' / 'migrations' / 'create_organizational_profiles_table.sql'
    
    print("🚀 Starting organizational profiles migration...")
    print(f"Database: {db_path}")
    print(f"Migration: {migration_file}")
    
    # Check if database exists
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        print("Please ensure you're running this script from the project root directory.")
        return False
    
    # Check if migration file exists
    if not migration_file.exists():
        print(f"❌ Migration file not found at {migration_file}")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='organizational_profiles'")
        table_exists = cursor.fetchone()
        
        if table_exists:
            print("⚠️  organizational_profiles table already exists")
            
            # Check if it has all required columns
            cursor.execute("PRAGMA table_info(organizational_profiles)")
            columns = [row[1] for row in cursor.fetchall()]
            required_columns = [
                'id', 'name', 'description', 'industry', 'organization_type', 'region',
                'key_concerns', 'strategic_priorities', 'risk_tolerance',
                'innovation_appetite', 'decision_making_style', 'stakeholder_focus',
                'competitive_landscape', 'regulatory_environment', 'custom_context',
                'created_at', 'updated_at', 'is_default'
            ]
            
            missing_columns = [col for col in required_columns if col not in columns]
            if missing_columns:
                print(f"❌ Missing columns: {missing_columns}")
                print("Attempting to add missing columns...")
                
                # Add missing columns (simplified approach)
                for col in missing_columns:
                    try:
                        if col in ['created_at', 'updated_at']:
                            cursor.execute(f"ALTER TABLE organizational_profiles ADD COLUMN {col} TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                        elif col == 'is_default':
                            cursor.execute(f"ALTER TABLE organizational_profiles ADD COLUMN {col} BOOLEAN DEFAULT FALSE")
                        else:
                            cursor.execute(f"ALTER TABLE organizational_profiles ADD COLUMN {col} TEXT")
                        print(f"✅ Added column: {col}")
                    except sqlite3.Error as e:
                        print(f"⚠️  Could not add column {col}: {e}")
                
                conn.commit()
            else:
                print("✅ All required columns present")
            
            # Check which profiles are missing and add them individually
            print("📝 Checking for missing default profiles...")
            
            # Define all default profiles that should exist
            all_default_profiles = [
                (
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
                        True
                    ),
                    (
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
                        False
                    ),
                    (
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
                        True
                    ),
                    (
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
                        True
                    ),
                    (
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
                        True
                    ),
                    (
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
                        True
                    )
                ]
                
            
            # Check each profile individually and add if missing
            profiles_to_add = []
            profiles_to_update = []
            
            for profile in all_default_profiles:
                profile_name = profile[0]
                
                # Check if profile exists
                cursor.execute("SELECT id, region FROM organizational_profiles WHERE name = ?", (profile_name,))
                existing = cursor.fetchone()
                
                if existing:
                    # Profile exists, check if region needs updating
                    if not existing[1]:  # No region set
                        cursor.execute("UPDATE organizational_profiles SET region = ? WHERE id = ?", (profile[4], existing[0]))
                        profiles_to_update.append(profile_name)
                        print(f"✅ Updated {profile_name} with region: {profile[4]}")
                else:
                    # Profile doesn't exist, add it
                    profiles_to_add.append(profile)
                    print(f"📝 Will add: {profile_name}")
            
            # Insert missing profiles
            if profiles_to_add:
                insert_query = """
                INSERT INTO organizational_profiles (
                    name, description, industry, organization_type, region, key_concerns,
                    strategic_priorities, risk_tolerance, innovation_appetite,
                    decision_making_style, stakeholder_focus, competitive_landscape,
                    regulatory_environment, custom_context, is_default
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                
                cursor.executemany(insert_query, profiles_to_add)
                conn.commit()
                print(f"✅ Added {len(profiles_to_add)} new default profiles")
            else:
                print("✅ All default profiles already exist")
            
            # Commit region updates
            if profiles_to_update:
                conn.commit()
                print(f"✅ Updated regions for {len(profiles_to_update)} existing profiles")
            
        else:
            print("📝 Creating organizational_profiles table...")
            
            # Read and execute migration file
            with open(migration_file, 'r', encoding='utf-8') as f:
                migration_sql = f.read()
            
            cursor.executescript(migration_sql)
            conn.commit()
            print("✅ organizational_profiles table created successfully")
        
        # Verify final state
        cursor.execute("SELECT COUNT(*) FROM organizational_profiles")
        total_profiles = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM organizational_profiles WHERE is_default = 1")
        default_profiles = cursor.fetchone()[0]
        
        print(f"✅ Migration completed successfully!")
        print(f"   Total profiles: {total_profiles}")
        print(f"   Default profiles: {default_profiles}")
        
        # Create indexes if they don't exist
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_org_profiles_name ON organizational_profiles(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_org_profiles_industry ON organizational_profiles(industry)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_org_profiles_default ON organizational_profiles(is_default)")
            conn.commit()
            print("✅ Indexes created/verified")
        except sqlite3.Error as e:
            print(f"⚠️  Index creation warning: {e}")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def main():
    """Main migration function."""
    print("=" * 60)
    print("AuNoo AI - Organizational Profiles Migration")
    print("=" * 60)
    print("This script will:")
    print("• Create the organizational_profiles table (if it doesn't exist)")
    print("• Add missing column 'region' (if needed)")
    print("• Add any missing default organizational profiles:")
    print("  - Wiley Scientific Publisher (Academic Publishing • Global)")
    print("  - Generic Enterprise (General • Global)")  
    print("  - Cybersecurity Organization (Cybersecurity • Global)")
    print("  - Financial Institution (Financial Services • North America)")
    print("  - Insurance Company (Insurance • Europe)")
    print("  - Manufacturing Company (Manufacturing • Asia Pacific)")
    print("• Update existing profiles with regions (if missing)")
    print("• Create database indexes for better performance")
    print()
    
    success = run_migration()
    
    if success:
        print("\n🎉 Migration completed successfully!")
        print("\nWhat's New:")
        print("✅ 6 industry-specific organizational profiles available")
        print("✅ Regional context for better localized analysis")
        print("✅ Enhanced AI prompts with profile-specific insights")
        print("✅ Improved explainability in trend convergence analysis")
        print("\nNext steps:")
        print("1. Restart your AuNoo AI application")
        print("2. Navigate to Trend Convergence Analysis")
        print("3. Select an organizational profile that matches your context")
        print("4. Experience enhanced, contextual strategic analysis!")
    else:
        print("\n❌ Migration failed!")
        print("Please check the error messages above and ensure:")
        print("1. You're running this script from the project root directory")
        print("2. The database file exists and is accessible")
        print("3. You have write permissions to the database")
        sys.exit(1)

if __name__ == "__main__":
    main()
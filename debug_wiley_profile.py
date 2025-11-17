#!/usr/bin/env python3
"""
Diagnostic script to examine organizational profiles in the database.
Focus: Investigate why Wiley profile generates pharmaceutical recommendations.
"""

import os
import sys
import json
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import get_database_instance
from app.database_query_facade import DatabaseQueryFacade
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Query and display organizational profile data."""

    print("=" * 80)
    print("ORGANIZATIONAL PROFILE DIAGNOSTIC TOOL")
    print("=" * 80)

    # Get database instance
    db = get_database_instance()
    facade = DatabaseQueryFacade(db, logger)

    # Query all organizational profiles
    query = """
    SELECT
        id, name, description, industry, organization_type, region,
        key_concerns, strategic_priorities, risk_tolerance, innovation_appetite,
        decision_making_style, stakeholder_focus, competitive_landscape,
        regulatory_environment, custom_context, is_default, created_at
    FROM organizational_profiles
    ORDER BY name;
    """

    try:
        results = db.execute_query(query)

        if not results:
            print("\n❌ No organizational profiles found in database!")
            return

        print(f"\n✓ Found {len(results)} organizational profiles\n")

        wiley_profiles = []
        pharma_profiles = []

        for row in results:
            profile = {
                'id': row[0],
                'name': row[1],
                'description': row[2],
                'industry': row[3],
                'organization_type': row[4],
                'region': row[5],
                'key_concerns': row[6],
                'strategic_priorities': row[7],
                'risk_tolerance': row[8],
                'innovation_appetite': row[9],
                'decision_making_style': row[10],
                'stakeholder_focus': row[11],
                'competitive_landscape': row[12],
                'regulatory_environment': row[13],
                'custom_context': row[14],
                'is_default': row[15],
                'created_at': str(row[16]) if row[16] else None
            }

            # Identify Wiley profiles
            if 'wiley' in profile['name'].lower():
                wiley_profiles.append(profile)

            # Identify pharmaceutical/manufacturing profiles
            profile_text = json.dumps(profile).lower()
            if any(term in profile_text for term in ['pharma', 'drug', 'gmp', 'manufacturing', 'clinical']):
                pharma_profiles.append(profile)

            # Print summary
            print(f"[{profile['id']}] {profile['name']}")
            print(f"    Industry: {profile['industry']}")
            print(f"    Type: {profile['organization_type']}")
            print(f"    Default: {profile['is_default']}")
            print()

        # Detailed Wiley Profile Analysis
        print("\n" + "=" * 80)
        print("WILEY PROFILE DETAILED ANALYSIS")
        print("=" * 80)

        if wiley_profiles:
            for profile in wiley_profiles:
                print(f"\n🔍 Profile ID: {profile['id']} - {profile['name']}")
                print("-" * 80)
                print(f"Description: {profile['description']}")
                print(f"Industry: {profile['industry']}")
                print(f"Organization Type: {profile['organization_type']}")
                print(f"Region: {profile['region']}")
                print(f"Is Default: {profile['is_default']}")
                print()
                print("Key Concerns:")
                for concern in profile['key_concerns']:
                    print(f"  - {concern}")
                print()
                print("Strategic Priorities:")
                for priority in profile['strategic_priorities']:
                    print(f"  - {priority}")
                print()
                print(f"Risk Tolerance: {profile['risk_tolerance']}")
                print(f"Innovation Appetite: {profile['innovation_appetite']}")
                print(f"Decision Making Style: {profile['decision_making_style']}")
                print()
                print("Stakeholder Focus:")
                for stakeholder in profile['stakeholder_focus']:
                    print(f"  - {stakeholder}")
                print()
                print("Competitive Landscape:")
                for comp in profile['competitive_landscape']:
                    print(f"  - {comp}")
                print()
                print("Regulatory Environment:")
                for reg in profile['regulatory_environment']:
                    print(f"  - {reg}")
                print()
                print(f"Custom Context: {profile['custom_context']}")
                print()

                # Check for pharmaceutical contamination
                profile_json = json.dumps(profile).lower()
                pharma_terms = ['pharma', 'drug', 'gmp', 'manufacturing', 'clinical', 'fda', 'therapeutic']
                found_terms = [term for term in pharma_terms if term in profile_json]

                if found_terms:
                    print("⚠️  WARNING: Pharmaceutical/Manufacturing terms found:")
                    for term in found_terms:
                        print(f"   - '{term}'")
                else:
                    print("✓ No pharmaceutical/manufacturing contamination detected")

                print("-" * 80)
        else:
            print("\n❌ NO WILEY PROFILES FOUND!")
            print("This could be the issue - no Wiley-specific profile exists.")

        # Pharmaceutical Profile Analysis
        print("\n" + "=" * 80)
        print("PHARMACEUTICAL/MANUFACTURING PROFILES FOUND")
        print("=" * 80)

        if pharma_profiles:
            for profile in pharma_profiles:
                print(f"\n[{profile['id']}] {profile['name']}")
                print(f"    Industry: {profile['industry']}")
                print(f"    Is Default: {profile['is_default']}")
        else:
            print("\nNo pharmaceutical/manufacturing profiles detected.")

        # Show what the org_context would look like for Wiley
        if wiley_profiles:
            print("\n" + "=" * 80)
            print("SIMULATED ORG_CONTEXT STRING (what gets sent to LLM)")
            print("=" * 80)

            profile = wiley_profiles[0]
            org_context = f"""

ORGANIZATIONAL CONTEXT:
- Organization: {profile['name']}
- Industry: {profile['industry']}
- Type: {profile['organization_type']}
- Description: {profile['description']}
- Key Concerns: {', '.join(profile['key_concerns'])}
- Strategic Priorities: {', '.join(profile['strategic_priorities'])}
- Risk Tolerance: {profile['risk_tolerance']}
- Innovation Appetite: {profile['innovation_appetite']}
- Decision Making Style: {profile['decision_making_style']}
- Key Stakeholders: {', '.join(profile['stakeholder_focus'])}
- Competitive Landscape: {', '.join(profile['competitive_landscape'])}
- Regulatory Environment: {', '.join(profile['regulatory_environment'])}
- Additional Context: {profile['custom_context']}
"""
            print(org_context)

    except Exception as e:
        logger.error(f"Error querying database: {e}", exc_info=True)
        print(f"\n❌ Database error: {e}")

    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()

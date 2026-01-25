#!/usr/bin/env python3
"""
Seed script for Geopolitical Hotspots

Populates the geopolitical_hotspots, country_hotspot_stats, and hotspot_daily_stats tables
with sample data for demonstration purposes.
"""

import sys
import os
import random
from datetime import datetime, timedelta

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_database_instance

# Sample hotspot data with real-world locations
SAMPLE_HOTSPOTS = [
    # Critical hotspots
    {"location_name": "Gaza Strip", "location_type": "region", "country_code": "PS", "country_name": "Palestine", "latitude": 31.5, "longitude": 34.47, "intensity_score": 95, "risk_level": "critical", "trend": "escalating", "primary_category": "conflict"},
    {"location_name": "Kyiv", "location_type": "city", "country_code": "UA", "country_name": "Ukraine", "latitude": 50.45, "longitude": 30.52, "intensity_score": 88, "risk_level": "critical", "trend": "stable", "primary_category": "conflict"},
    {"location_name": "Taipei", "location_type": "city", "country_code": "TW", "country_name": "Taiwan", "latitude": 25.03, "longitude": 121.57, "intensity_score": 82, "risk_level": "critical", "trend": "escalating", "primary_category": "diplomatic"},

    # High risk hotspots
    {"location_name": "South China Sea", "location_type": "region", "country_code": None, "country_name": None, "latitude": 12.0, "longitude": 114.0, "intensity_score": 75, "risk_level": "high", "trend": "escalating", "primary_category": "military"},
    {"location_name": "Tehran", "location_type": "city", "country_code": "IR", "country_name": "Iran", "latitude": 35.69, "longitude": 51.39, "intensity_score": 72, "risk_level": "high", "trend": "stable", "primary_category": "diplomatic"},
    {"location_name": "Beirut", "location_type": "city", "country_code": "LB", "country_name": "Lebanon", "latitude": 33.89, "longitude": 35.50, "intensity_score": 70, "risk_level": "high", "trend": "de-escalating", "primary_category": "economic"},
    {"location_name": "Khartoum", "location_type": "city", "country_code": "SD", "country_name": "Sudan", "latitude": 15.50, "longitude": 32.56, "intensity_score": 78, "risk_level": "high", "trend": "escalating", "primary_category": "conflict"},
    {"location_name": "Port-au-Prince", "location_type": "city", "country_code": "HT", "country_name": "Haiti", "latitude": 18.54, "longitude": -72.34, "intensity_score": 68, "risk_level": "high", "trend": "escalating", "primary_category": "crime"},
    {"location_name": "Caracas", "location_type": "city", "country_code": "VE", "country_name": "Venezuela", "latitude": 10.48, "longitude": -66.90, "intensity_score": 65, "risk_level": "high", "trend": "stable", "primary_category": "economic"},
    {"location_name": "Kharkiv", "location_type": "city", "country_code": "UA", "country_name": "Ukraine", "latitude": 49.99, "longitude": 36.23, "intensity_score": 80, "risk_level": "high", "trend": "stable", "primary_category": "conflict"},

    # Medium risk hotspots
    {"location_name": "Seoul", "location_type": "city", "country_code": "KR", "country_name": "South Korea", "latitude": 37.57, "longitude": 126.98, "intensity_score": 55, "risk_level": "medium", "trend": "stable", "primary_category": "diplomatic"},
    {"location_name": "Mogadishu", "location_type": "city", "country_code": "SO", "country_name": "Somalia", "latitude": 2.04, "longitude": 45.34, "intensity_score": 58, "risk_level": "medium", "trend": "de-escalating", "primary_category": "terrorism"},
    {"location_name": "Yangon", "location_type": "city", "country_code": "MM", "country_name": "Myanmar", "latitude": 16.87, "longitude": 96.20, "intensity_score": 52, "risk_level": "medium", "trend": "stable", "primary_category": "protest"},
    {"location_name": "Kabul", "location_type": "city", "country_code": "AF", "country_name": "Afghanistan", "latitude": 34.53, "longitude": 69.17, "intensity_score": 50, "risk_level": "medium", "trend": "stable", "primary_category": "terrorism"},
    {"location_name": "Lagos", "location_type": "city", "country_code": "NG", "country_name": "Nigeria", "latitude": 6.52, "longitude": 3.38, "intensity_score": 48, "risk_level": "medium", "trend": "escalating", "primary_category": "crime"},
    {"location_name": "Damascus", "location_type": "city", "country_code": "SY", "country_name": "Syria", "latitude": 33.51, "longitude": 36.29, "intensity_score": 45, "risk_level": "medium", "trend": "de-escalating", "primary_category": "conflict"},
    {"location_name": "Islamabad", "location_type": "city", "country_code": "PK", "country_name": "Pakistan", "latitude": 33.69, "longitude": 73.06, "intensity_score": 42, "risk_level": "medium", "trend": "stable", "primary_category": "terrorism"},
    {"location_name": "Nairobi", "location_type": "city", "country_code": "KE", "country_name": "Kenya", "latitude": -1.29, "longitude": 36.82, "intensity_score": 40, "risk_level": "medium", "trend": "stable", "primary_category": "terrorism"},
    {"location_name": "Buenos Aires", "location_type": "city", "country_code": "AR", "country_name": "Argentina", "latitude": -34.60, "longitude": -58.38, "intensity_score": 45, "risk_level": "medium", "trend": "escalating", "primary_category": "economic"},
    {"location_name": "Bogota", "location_type": "city", "country_code": "CO", "country_name": "Colombia", "latitude": 4.71, "longitude": -74.07, "intensity_score": 42, "risk_level": "medium", "trend": "stable", "primary_category": "crime"},

    # Low risk hotspots
    {"location_name": "Brussels", "location_type": "city", "country_code": "BE", "country_name": "Belgium", "latitude": 50.85, "longitude": 4.35, "intensity_score": 30, "risk_level": "low", "trend": "stable", "primary_category": "cyber"},
    {"location_name": "Tokyo", "location_type": "city", "country_code": "JP", "country_name": "Japan", "latitude": 35.68, "longitude": 139.69, "intensity_score": 28, "risk_level": "low", "trend": "stable", "primary_category": "diplomatic"},
    {"location_name": "Canberra", "location_type": "city", "country_code": "AU", "country_name": "Australia", "latitude": -35.28, "longitude": 149.13, "intensity_score": 25, "risk_level": "low", "trend": "stable", "primary_category": "cyber"},
    {"location_name": "Singapore", "location_type": "city", "country_code": "SG", "country_name": "Singapore", "latitude": 1.35, "longitude": 103.82, "intensity_score": 22, "risk_level": "low", "trend": "de-escalating", "primary_category": "economic"},
    {"location_name": "New Delhi", "location_type": "city", "country_code": "IN", "country_name": "India", "latitude": 28.61, "longitude": 77.21, "intensity_score": 35, "risk_level": "low", "trend": "stable", "primary_category": "diplomatic"},
    {"location_name": "Mexico City", "location_type": "city", "country_code": "MX", "country_name": "Mexico", "latitude": 19.43, "longitude": -99.13, "intensity_score": 38, "risk_level": "low", "trend": "stable", "primary_category": "crime"},
    {"location_name": "Lima", "location_type": "city", "country_code": "PE", "country_name": "Peru", "latitude": -12.05, "longitude": -77.04, "intensity_score": 28, "risk_level": "low", "trend": "de-escalating", "primary_category": "protest"},
    {"location_name": "Santiago", "location_type": "city", "country_code": "CL", "country_name": "Chile", "latitude": -33.45, "longitude": -70.67, "intensity_score": 25, "risk_level": "low", "trend": "stable", "primary_category": "economic"},

    # Info level hotspots
    {"location_name": "Ottawa", "location_type": "city", "country_code": "CA", "country_name": "Canada", "latitude": 45.42, "longitude": -75.70, "intensity_score": 15, "risk_level": "info", "trend": "stable", "primary_category": "diplomatic"},
    {"location_name": "Berlin", "location_type": "city", "country_code": "DE", "country_name": "Germany", "latitude": 52.52, "longitude": 13.40, "intensity_score": 18, "risk_level": "info", "trend": "stable", "primary_category": "economic"},
    {"location_name": "London", "location_type": "city", "country_code": "GB", "country_name": "United Kingdom", "latitude": 51.51, "longitude": -0.13, "intensity_score": 20, "risk_level": "info", "trend": "stable", "primary_category": "economic"},
    {"location_name": "Paris", "location_type": "city", "country_code": "FR", "country_name": "France", "latitude": 48.86, "longitude": 2.35, "intensity_score": 22, "risk_level": "info", "trend": "stable", "primary_category": "protest"},
    {"location_name": "Rome", "location_type": "city", "country_code": "IT", "country_name": "Italy", "latitude": 41.90, "longitude": 12.50, "intensity_score": 18, "risk_level": "info", "trend": "stable", "primary_category": "economic"},
    {"location_name": "Madrid", "location_type": "city", "country_code": "ES", "country_name": "Spain", "latitude": 40.42, "longitude": -3.70, "intensity_score": 16, "risk_level": "info", "trend": "stable", "primary_category": "economic"},
]

THREAT_CATEGORIES = [
    'conflict', 'protest', 'disaster', 'diplomatic',
    'economic', 'terrorism', 'cyber', 'health',
    'environmental', 'military', 'crime', 'piracy',
    'infrastructure', 'commodities'
]


def seed_hotspots():
    """Seed the geopolitical_hotspots table."""
    db = get_database_instance()
    conn = db.get_connection()
    cursor = conn.cursor()

    print("Seeding geopolitical_hotspots...")

    import json
    for hotspot in SAMPLE_HOTSPOTS:
        # Generate random article counts
        article_count = random.randint(10, 500)
        recent_article_count = random.randint(1, min(50, article_count))

        # Generate random tags
        tags = random.sample(THREAT_CATEGORIES, random.randint(1, 3))

        cursor.execute("""
            INSERT INTO geopolitical_hotspots
            (location_name, location_type, country_code, country_name, latitude, longitude,
             intensity_score, risk_level, trend, article_count, recent_article_count,
             primary_category, tags, last_article_date)
            VALUES (:location_name, :location_type, :country_code, :country_name, :latitude, :longitude,
             :intensity_score, :risk_level, :trend, :article_count, :recent_article_count,
             :primary_category, :tags, :last_article_date)
            ON CONFLICT DO NOTHING
        """, {
            'location_name': hotspot['location_name'],
            'location_type': hotspot['location_type'],
            'country_code': hotspot['country_code'],
            'country_name': hotspot['country_name'],
            'latitude': hotspot['latitude'],
            'longitude': hotspot['longitude'],
            'intensity_score': hotspot['intensity_score'],
            'risk_level': hotspot['risk_level'],
            'trend': hotspot['trend'],
            'article_count': article_count,
            'recent_article_count': recent_article_count,
            'primary_category': hotspot['primary_category'],
            'tags': json.dumps(tags),
            'last_article_date': datetime.now() - timedelta(hours=random.randint(1, 48))
        })

    conn.commit()
    print(f"Seeded {len(SAMPLE_HOTSPOTS)} hotspots")

    cursor.close()
    conn.close()


def seed_country_stats():
    """Seed the country_hotspot_stats table from existing hotspots."""
    db = get_database_instance()
    conn = db.get_connection()
    cursor = conn.cursor()

    print("Seeding country_hotspot_stats...")

    cursor.execute("""
        INSERT INTO country_hotspot_stats
        (country_code, country_name, total_hotspots, total_articles, heat_value, max_risk_level, primary_category)
        SELECT
            country_code,
            MAX(country_name) as country_name,
            COUNT(*) as total_hotspots,
            SUM(article_count) as total_articles,
            AVG(intensity_score) as heat_value,
            MAX(CASE
                WHEN risk_level = 'critical' THEN 5
                WHEN risk_level = 'high' THEN 4
                WHEN risk_level = 'medium' THEN 3
                WHEN risk_level = 'low' THEN 2
                ELSE 1
            END) as risk_rank,
            MODE() WITHIN GROUP (ORDER BY primary_category) as primary_category
        FROM geopolitical_hotspots
        WHERE country_code IS NOT NULL
        GROUP BY country_code
        ON CONFLICT (country_code) DO UPDATE SET
            total_hotspots = EXCLUDED.total_hotspots,
            total_articles = EXCLUDED.total_articles,
            heat_value = EXCLUDED.heat_value,
            updated_at = NOW()
    """)

    # Update max_risk_level based on rank
    cursor.execute("""
        UPDATE country_hotspot_stats
        SET max_risk_level = CASE
            WHEN heat_value >= 80 THEN 'critical'
            WHEN heat_value >= 60 THEN 'high'
            WHEN heat_value >= 40 THEN 'medium'
            WHEN heat_value >= 20 THEN 'low'
            ELSE 'info'
        END
    """)

    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM country_hotspot_stats")
    count = cursor.fetchone()[0]
    print(f"Seeded {count} country stats")

    cursor.close()
    conn.close()


def seed_daily_stats():
    """Seed the hotspot_daily_stats table with historical data."""
    db = get_database_instance()
    conn = db.get_connection()
    cursor = conn.cursor()

    print("Seeding hotspot_daily_stats...")

    # Get all hotspot IDs
    cursor.execute("SELECT id, intensity_score FROM geopolitical_hotspots")
    hotspots = cursor.fetchall()

    # Generate daily stats for the past 30 days
    today = datetime.now().date()
    count = 0

    for hotspot_id, base_intensity in hotspots:
        for days_ago in range(30):
            date = today - timedelta(days=days_ago)

            # Vary intensity slightly day to day
            daily_intensity = base_intensity + random.uniform(-10, 10)
            daily_intensity = max(0, min(100, daily_intensity))

            # Random article count
            article_count = random.randint(0, 20)

            # Determine trend based on recent intensity changes
            if days_ago < 7:
                trend = random.choice(['escalating', 'stable', 'de-escalating'])
            else:
                trend = 'stable'

            cursor.execute("""
                INSERT INTO hotspot_daily_stats
                (date, hotspot_id, article_count, intensity_score, trend)
                VALUES (:date, :hotspot_id, :article_count, :intensity_score, :trend)
                ON CONFLICT (date, hotspot_id) DO UPDATE SET
                    article_count = EXCLUDED.article_count,
                    intensity_score = EXCLUDED.intensity_score,
                    trend = EXCLUDED.trend,
                    updated_at = NOW()
            """, {
                'date': date,
                'hotspot_id': hotspot_id,
                'article_count': article_count,
                'intensity_score': daily_intensity,
                'trend': trend
            })

            count += 1

    conn.commit()
    print(f"Seeded {count} daily stats records")

    cursor.close()
    conn.close()


def main():
    """Main entry point."""
    print("=" * 50)
    print("Seeding Geopolitical Hotspots Data")
    print("=" * 50)

    try:
        seed_hotspots()
        seed_country_stats()
        seed_daily_stats()

        print("=" * 50)
        print("Seeding complete!")
        print("=" * 50)
    except Exception as e:
        print(f"Error seeding data: {e}")
        raise


if __name__ == "__main__":
    main()

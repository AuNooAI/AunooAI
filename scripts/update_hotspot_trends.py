#!/usr/bin/env python3
"""
Update Geopolitical Hotspot Trends

Recalculates hotspot trends (escalating/de-escalating/stable) based on
recent article sentiment and intensity patterns.

This script should be run:
- After bulk article processing
- Periodically (e.g., daily) to keep trends current
- After seeding initial hotspots

Usage:
    python scripts/update_hotspot_trends.py [--days 7] [--topic "Geopolitical Hotspots"]
"""

import sys
import os
import argparse
from datetime import datetime, timedelta

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_database_instance


def calculate_trend(recent_sentiment_avg: float, older_sentiment_avg: float,
                    recent_count: int, older_count: int) -> str:
    """
    Calculate trend based on sentiment comparison between periods.

    Logic:
    - If recent sentiment is more negative than older → escalating
    - If recent sentiment is more positive than older → de-escalating
    - Otherwise → stable

    Also considers article volume changes.
    """
    if recent_count < 3:
        return "stable"  # Not enough data

    # Sentiment scale: Negative=-1, Neutral=0, Positive=1, Mixed=0
    sentiment_diff = recent_sentiment_avg - older_sentiment_avg
    volume_ratio = recent_count / max(older_count, 1)

    # Escalating: more negative sentiment OR significant volume increase with negative sentiment
    if sentiment_diff < -0.2 or (volume_ratio > 1.5 and recent_sentiment_avg < 0):
        return "escalating"

    # De-escalating: more positive sentiment OR significant volume decrease
    if sentiment_diff > 0.2 or (volume_ratio < 0.5 and recent_sentiment_avg >= 0):
        return "de-escalating"

    return "stable"


def sentiment_to_score(sentiment: str) -> float:
    """Convert sentiment string to numeric score."""
    sentiment_map = {
        'Positive': 1.0,
        'Negative': -1.0,
        'Neutral': 0.0,
        'Mixed': 0.0,
    }
    return sentiment_map.get(sentiment, 0.0)


def update_hotspot_trends(days_recent: int = 7, days_comparison: int = 30, topic: str = None):
    """
    Update trends for all hotspots based on article sentiment analysis.

    Args:
        days_recent: Number of days to consider as "recent" (default: 7)
        days_comparison: Number of days for comparison period (default: 30)
        topic: Optional topic filter
    """
    db = get_database_instance()

    print("=" * 60)
    print("  Updating Geopolitical Hotspot Trends")
    print("=" * 60)
    print(f"\nRecent period: last {days_recent} days")
    print(f"Comparison period: {days_recent}-{days_comparison} days ago")
    if topic:
        print(f"Topic filter: {topic}")
    print()

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Get all hotspots
        cursor.execute("""
            SELECT id, location_name, country_name, trend
            FROM geopolitical_hotspots
            ORDER BY intensity_score DESC
        """)
        hotspots = cursor.fetchall()

        if not hotspots:
            print("No hotspots found. Run seed_geopolitical_hotspots.py first.")
            return

        print(f"Found {len(hotspots)} hotspots to analyze\n")

        updated = 0
        escalating = 0
        de_escalating = 0
        stable = 0

        recent_cutoff = datetime.now() - timedelta(days=days_recent)
        older_cutoff = datetime.now() - timedelta(days=days_comparison)

        for hotspot in hotspots:
            hotspot_id, location_name, country_name, current_trend = hotspot

            # Get recent articles linked to this hotspot
            cursor.execute("""
                SELECT a.sentiment, a.submission_date
                FROM articles a
                JOIN hotspot_articles ha ON ha.article_uri = a.uri
                WHERE ha.hotspot_id = :hotspot_id
                  AND a.submission_date >= :older_cutoff
                  AND a.sentiment IS NOT NULL
                ORDER BY a.submission_date DESC
            """, {
                'hotspot_id': hotspot_id,
                'older_cutoff': older_cutoff
            })
            articles = cursor.fetchall()

            if not articles:
                # No linked articles - try matching by location name in article content
                cursor.execute("""
                    SELECT sentiment, submission_date
                    FROM articles
                    WHERE (title ILIKE :location_pattern
                           OR summary ILIKE :location_pattern)
                      AND submission_date >= :older_cutoff
                      AND sentiment IS NOT NULL
                    ORDER BY submission_date DESC
                    LIMIT 100
                """, {
                    'location_pattern': f'%{location_name}%',
                    'older_cutoff': older_cutoff
                })
                articles = cursor.fetchall()

            if len(articles) < 3:
                stable += 1
                continue

            # Split into recent and older periods
            recent_articles = [a for a in articles if a[1] >= recent_cutoff]
            older_articles = [a for a in articles if a[1] < recent_cutoff]

            # Calculate average sentiment for each period
            recent_scores = [sentiment_to_score(a[0]) for a in recent_articles]
            older_scores = [sentiment_to_score(a[0]) for a in older_articles]

            recent_avg = sum(recent_scores) / len(recent_scores) if recent_scores else 0
            older_avg = sum(older_scores) / len(older_scores) if older_scores else 0

            # Calculate new trend
            new_trend = calculate_trend(
                recent_avg, older_avg,
                len(recent_articles), len(older_articles)
            )

            # Update if changed
            if new_trend != current_trend:
                cursor.execute("""
                    UPDATE geopolitical_hotspots
                    SET trend = :trend, updated_at = NOW()
                    WHERE id = :id
                """, {'trend': new_trend, 'id': hotspot_id})

                print(f"  {location_name} ({country_name}): {current_trend} → {new_trend}")
                print(f"    Recent: {len(recent_articles)} articles, avg sentiment: {recent_avg:.2f}")
                print(f"    Older:  {len(older_articles)} articles, avg sentiment: {older_avg:.2f}")
                updated += 1

            # Count trends
            if new_trend == "escalating":
                escalating += 1
            elif new_trend == "de-escalating":
                de_escalating += 1
            else:
                stable += 1

        conn.commit()

        print()
        print("=" * 60)
        print("  Summary")
        print("=" * 60)
        print(f"\nTotal hotspots: {len(hotspots)}")
        print(f"Updated: {updated}")
        print()
        print(f"Escalating:    {escalating}")
        print(f"De-escalating: {de_escalating}")
        print(f"Stable:        {stable}")
        print()


def main():
    parser = argparse.ArgumentParser(description='Update geopolitical hotspot trends')
    parser.add_argument('--days', type=int, default=7,
                        help='Number of days for recent period (default: 7)')
    parser.add_argument('--comparison', type=int, default=30,
                        help='Number of days for comparison period (default: 30)')
    parser.add_argument('--topic', type=str, default=None,
                        help='Topic filter (optional)')

    args = parser.parse_args()

    update_hotspot_trends(
        days_recent=args.days,
        days_comparison=args.comparison,
        topic=args.topic
    )


if __name__ == '__main__':
    main()

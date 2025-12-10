#!/bin/bash
# Script to export Geopolitical Hotspots topic data from geopolitics.aunoo.bot
# Run this on the server 88.99.149.48 in /home/orochford/tenants/geopolitics.aunoo.bot/

# Database credentials
DB_HOST="localhost"
DB_PORT="6432"
DB_NAME="geopolitics_aunoo_bot"
DB_USER="geopolitics_aunoo_bot_user"
DB_PASSWORD="kWtLact36ij3MSQ5J9TQhDFv41aBQpPk"

EXPORT_DIR="/tmp/geopolitics_export"
mkdir -p "$EXPORT_DIR"

echo "=== Exporting Geopolitical Hotspots Data ==="
echo ""

# First, find the topic
echo "Step 1: Finding Geopolitical Hotspots keyword group..."
PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -p "$DB_PORT" -c \
    "SELECT id, name, topic FROM keyword_groups WHERE topic ILIKE '%geopolitical%' OR topic ILIKE '%hotspot%' OR name ILIKE '%geopolitical%';"

# Get the topic ID (assuming it exists)
TOPIC_ID=$(PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -p "$DB_PORT" -t -A -c \
    "SELECT id FROM keyword_groups WHERE topic ILIKE '%geopolitical%' OR topic ILIKE '%hotspot%' OR name ILIKE '%geopolitical%' LIMIT 1;")

if [ -z "$TOPIC_ID" ]; then
    echo "ERROR: Could not find Geopolitical Hotspots topic. Listing all topics:"
    PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -p "$DB_PORT" -c \
        "SELECT id, name, topic FROM keyword_groups ORDER BY id;"
    echo ""
    echo "Please edit this script and set TOPIC_ID manually, then run again."
    exit 1
fi

echo "Found topic ID: $TOPIC_ID"
echo ""

# Export keyword_groups
echo "Step 2: Exporting keyword_groups..."
PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -p "$DB_PORT" -c \
    "COPY (SELECT * FROM keyword_groups WHERE id = $TOPIC_ID) TO STDOUT WITH CSV HEADER" > "$EXPORT_DIR/keyword_groups.csv"
echo "  -> Exported to $EXPORT_DIR/keyword_groups.csv"

# Export monitored_keywords
echo "Step 3: Exporting monitored_keywords..."
PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -p "$DB_PORT" -c \
    "COPY (SELECT * FROM monitored_keywords WHERE group_id = $TOPIC_ID) TO STDOUT WITH CSV HEADER" > "$EXPORT_DIR/monitored_keywords.csv"
KEYWORD_COUNT=$(wc -l < "$EXPORT_DIR/monitored_keywords.csv")
echo "  -> Exported $((KEYWORD_COUNT - 1)) keywords to $EXPORT_DIR/monitored_keywords.csv"

# Get article URIs for this topic
echo "Step 4: Getting article URIs for this topic..."
PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -p "$DB_PORT" -t -A -c \
    "SELECT DISTINCT article_uri FROM keyword_article_matches WHERE group_id = $TOPIC_ID" > "$EXPORT_DIR/article_uris.txt"
ARTICLE_COUNT=$(wc -l < "$EXPORT_DIR/article_uris.txt")
echo "  -> Found $ARTICLE_COUNT articles"

# Export articles
echo "Step 5: Exporting articles..."
PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -p "$DB_PORT" -c \
    "COPY (SELECT * FROM articles WHERE uri IN (SELECT DISTINCT article_uri FROM keyword_article_matches WHERE group_id = $TOPIC_ID)) TO STDOUT WITH CSV HEADER" > "$EXPORT_DIR/articles.csv"
echo "  -> Exported to $EXPORT_DIR/articles.csv"

# Export raw_articles
echo "Step 6: Exporting raw_articles..."
PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -p "$DB_PORT" -c \
    "COPY (SELECT * FROM raw_articles WHERE uri IN (SELECT DISTINCT article_uri FROM keyword_article_matches WHERE group_id = $TOPIC_ID)) TO STDOUT WITH CSV HEADER" > "$EXPORT_DIR/raw_articles.csv"
RAW_COUNT=$(wc -l < "$EXPORT_DIR/raw_articles.csv")
echo "  -> Exported $((RAW_COUNT - 1)) raw articles to $EXPORT_DIR/raw_articles.csv"

# Export keyword_article_matches
echo "Step 7: Exporting keyword_article_matches..."
PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -p "$DB_PORT" -c \
    "COPY (SELECT * FROM keyword_article_matches WHERE group_id = $TOPIC_ID) TO STDOUT WITH CSV HEADER" > "$EXPORT_DIR/keyword_article_matches.csv"
MATCH_COUNT=$(wc -l < "$EXPORT_DIR/keyword_article_matches.csv")
echo "  -> Exported $((MATCH_COUNT - 1)) matches to $EXPORT_DIR/keyword_article_matches.csv"

# Export config.json topic ontology
echo "Step 8: Copying config.json..."
cp /home/orochford/tenants/geopolitics.aunoo.bot/app/config/config.json "$EXPORT_DIR/config.json" 2>/dev/null || echo "  -> config.json not found"

# Create tarball
echo ""
echo "Step 9: Creating tarball..."
cd /tmp
tar -czvf geopolitics_export.tar.gz geopolitics_export/
echo ""
echo "=== Export Complete ==="
echo "Files exported to: $EXPORT_DIR/"
echo "Tarball created: /tmp/geopolitics_export.tar.gz"
echo ""
echo "File sizes:"
ls -lh "$EXPORT_DIR/"
echo ""
echo "To transfer to the other server, run:"
echo "  scp /tmp/geopolitics_export.tar.gz orochford@<target-server>:/tmp/"

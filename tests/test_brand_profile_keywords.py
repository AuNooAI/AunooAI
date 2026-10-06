"""scripts/brand_profile_keywords.py: proposals against PostgreSQL in a
throwaway schema. Japanese names go to the Japanese group, Latin names to the
English group, multi-word names are quoted, existing terms in another form
and short ambiguous names are not proposed."""
import importlib.util
import json
import os
import uuid

import pytest


@pytest.fixture
def db():
    try:
        from dotenv import load_dotenv
        from sqlalchemy import create_engine, text
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
        schema = f"bktest_{uuid.uuid4().hex[:8]}"
        url = (f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST', 'localhost')}:"
               f"{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME')}")
        eng = create_engine(url, connect_args={"options": f"-csearch_path={schema},public"})
        conn = eng.connect()
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        for t in ("bw_brands", "keyword_groups", "monitored_keywords"):
            conn.execute(text(f"CREATE TABLE {schema}.{t} (LIKE public.{t} INCLUDING ALL)"))
        conn.commit()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no sandbox: {e}")
    yield conn, text
    conn.rollback()
    conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    conn.commit()
    conn.close()


def _script():
    path = os.path.join(os.path.dirname(__file__), "..", "scripts", "brand_profile_keywords.py")
    spec = importlib.util.spec_from_file_location("brand_profile_keywords", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_proposals_route_by_script_and_skip_known_and_ambiguous(db):
    conn, text = db
    conn.execute(text("""INSERT INTO bw_brands (id, name, display_name, enabled, brand_keywords, product_keywords, config)
        VALUES (2, 'lion', 'Lion Corporation', true, :kw, :pk, :cfg)"""),
        {"kw": json.dumps(["Lion Corp", "ライオン株式会社", "LION"]),
         "pk": json.dumps(["Clinica", "クリニカ", "Systema toothbrush", "NONIO"]),
         "cfg": json.dumps({"ambiguous_aliases": ["LION"], "original_names": ["ライオン歯科材"]})})
    en = conn.execute(text("INSERT INTO keyword_groups (name, topic, source, is_active, language) VALUES "
                           "('Lion EN', 'Brand Monitoring Lion Corporation', 'news', true, 'en') RETURNING id")).scalar()
    ja = conn.execute(text("INSERT INTO keyword_groups (name, topic, source, is_active, language) VALUES "
                           "('Lion JP', 'Brand Monitoring Lion Corporation', 'news', true, 'ja') RETURNING id")).scalar()
    for g, k in ((en, '"Systema toothbrush"'), (en, "NONIO"), (ja, "クリニカ")):
        conn.execute(text("INSERT INTO monitored_keywords (group_id, keyword) VALUES (:g, :k)"), {"g": g, "k": k})
    conn.commit()
    plan = _script().propose(conn)
    got = {(p["group_id"], p["keyword"]) for p in plan}
    assert (en, '"Lion Corporation"') in got and (en, '"Lion Corp"') in got and (en, "Clinica") in got
    assert (ja, "ライオン株式会社") in got and (ja, "ライオン歯科材") in got
    keywords = {p["keyword"] for p in plan}
    assert "LION" not in keywords                      # ambiguous
    assert "クリニカ" not in keywords and "NONIO" not in keywords  # already searched
    assert not any("Systema" in k for k in keywords)   # existing, quoted form

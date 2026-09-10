# deberta-encoder.service

The 768-dimension DeBERTa encoder every AunooAI site embeds through, on
`127.0.0.1:8001`. It runs as its own unit with its own user, tree, venv and
model cache so that nothing done to the NewsFirehose stack can take it down
again (2026-09-09: the firehose units were stopped for a migration and every
site saved articles without embeddings for 16 hours).

Install on a host:

```
useradd --system --home /opt/deberta-encoder --shell /usr/sbin/nologin deberta
mkdir -p /opt/deberta-encoder/ml /opt/deberta-encoder/.cache/huggingface
# ml/__init__.py, ml/encoder.py, ml/encoder_service.py from the NewsFirehose repo
# model files: hub/models--microsoft--deberta-base under .cache/huggingface
python3.12 -m venv /opt/deberta-encoder/venv
/opt/deberta-encoder/venv/bin/pip install "torch==2.10.0" --index-url https://download.pytorch.org/whl/cu128
/opt/deberta-encoder/venv/bin/pip install "transformers==5.2.0" "fastapi==0.104.1" "uvicorn==0.24.0" numpy
chown -R deberta:deberta /opt/deberta-encoder
cp deberta-encoder.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now deberta-encoder
curl -s -X POST http://localhost:8001/encode -H 'Content-Type: application/json' -d '{"texts":["smoke"]}'
```

Do not start the old `newsfirehose-encoder.service` alongside it: same port.
After any outage, run `app/tasks/embedding_backfill.backfill_embeddings`
per site by hand; nothing schedules it.

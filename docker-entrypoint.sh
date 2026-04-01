#!/bin/bash
set -e

cat > /app/config.json << EOF
{
  "log_level": "${LOG_LEVEL:-INFO}",
  "telegram_api_id": ${TELEGRAM_API_ID},
  "telegram_api_hash": "${TELEGRAM_API_HASH}",
  "google_api_key": "${GOOGLE_API_KEY}",
  "telegram_output_channels": ["${TELEGRAM_OUTPUT_CHANNEL}"],
  "chats_to_summarize": [
    {
      "id": "${SOURCE_CHAT_ID}",
      "lookback_period_seconds": ${LOOKBACK_PERIOD_SECONDS:-86400},
      "summarization_prompt_path": "prompts/example_summarization_prompt.txt",
      "backfill": ${BACKFILL:-false}
    }
  ]
}
EOF

exec python3 /app/app.py /app/config.json

import argparse
from typing import List, Union
from datetime import datetime, timedelta, timezone
import logging
import os
import re
import schedule
import time
import json
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: F401 — triggers proper imports
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError

from communication import GroupChatScrapper
from summarization import Summarizer

BACKFILL_RPM = 5
BACKFILL_SLEEP = 60 / BACKFILL_RPM  # 12 seconds between requests
BACKFILL_PROGRESS_FILE = "backfill_progress.json"


class SummarizationConfig(BaseModel):
    id: Union[str, int]
    lookback_period_seconds: int
    summarization_prompt_path: str
    backfill: bool = Field(default=False)


class AppConfig(BaseModel):
    log_level: str = Field(default="INFO")
    telegram_api_id: int
    telegram_api_hash: str
    google_api_key: str
    telegram_output_channels: List[str]
    chats_to_summarize: List[SummarizationConfig]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path_to_config")
    args = parser.parse_args()

    with open(args.path_to_config, "r") as f:
        app_config = AppConfig.model_validate_json(f.read())

    # Validate user prompts
    for c in app_config.chats_to_summarize:
        with open(c.summarization_prompt_path, "r") as f:
            Summarizer.validate_summarization_prompt(f.read())

    # Initialize logger
    logger = logging.getLogger("CSB")
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(app_config.log_level)
    logger.info("Started!")

    summarizer = Summarizer(app_config.google_api_key)
    scrapper = GroupChatScrapper(app_config.telegram_api_id, app_config.telegram_api_hash)


    def build_date_range(date_from, date_to):
        if date_from.month == date_to.month:
            return f"{date_from.day} - {date_to.day} {date_to.strftime('%b')}"
        return f"{date_from.strftime('%-d %b')} - {date_to.strftime('%-d %b')}"


    def summarization_job(chat_cfg, summarization_prompt):
        logger.info(f"Running summarization job for: {chat_cfg.id}")

        messages, chat_title, chat_link_base = scrapper.get_message_history(
            chat_cfg.id, chat_cfg.lookback_period_seconds
        )
        logger.debug(f"Scrapped {len(messages)} messages for {chat_cfg.id}")

        if not messages:
            logger.info(f"No messages found for {chat_cfg.id}, skipping")
            return

        date_to = datetime.now(timezone.utc)
        date_from = date_to - timedelta(seconds=chat_cfg.lookback_period_seconds)
        date_range = build_date_range(date_from, date_to)

        serialized_messages = json.dumps({"messages": messages}, ensure_ascii=False)
        summary, _ = summarizer.summarize(
            serialized_messages, summarization_prompt,
            chat_link_base=chat_link_base, date_range=date_range,
        )
        logger.debug(f"Summary for {chat_title}: {summary}")

        for channel in app_config.telegram_output_channels:
            logger.info(f"Posting summary for {chat_cfg.id} to {channel}")
            scrapper.send_to_channel(channel, summary)


    def load_backfill_progress():
        if os.path.exists(BACKFILL_PROGRESS_FILE):
            with open(BACKFILL_PROGRESS_FILE, "r") as f:
                return json.load(f)
        return {}

    def save_backfill_progress(progress):
        with open(BACKFILL_PROGRESS_FILE, "w") as f:
            json.dump(progress, f, indent=2)

    def run_backfill(chat_cfg, summarization_prompt):
        logger.info(f"Starting backfill for: {chat_cfg.id}")
        oldest_date = scrapper.get_oldest_message_date(chat_cfg.id)
        if not oldest_date:
            logger.info(f"No messages found for backfill: {chat_cfg.id}")
            return

        period = timedelta(seconds=chat_cfg.lookback_period_seconds)
        cutoff = datetime.now(timezone.utc) - period

        # Build all windows oldest-first
        windows = []
        win_end = cutoff
        while win_end > oldest_date:
            windows.append(win_end)
            win_end -= period
        windows.reverse()

        # Resume from last completed window if progress exists
        progress = load_backfill_progress()
        chat_key = str(chat_cfg.id)
        last_completed = progress.get(chat_key)
        if last_completed:
            last_completed_dt = datetime.fromisoformat(last_completed)
            windows = [w for w in windows if w > last_completed_dt]
            logger.info(f"Resuming backfill from {last_completed}, {len(windows)} periods remaining")
        else:
            logger.info(f"Backfilling {len(windows)} periods for {chat_cfg.id}")

        for win_end in windows:
            win_start = win_end - period
            messages, chat_title, chat_link_base = scrapper.get_message_history(
                chat_cfg.id, chat_cfg.lookback_period_seconds, date_to=win_end
            )
            if not messages:
                # Save progress even for empty windows so we don't re-check them
                progress[chat_key] = win_end.isoformat()
                save_backfill_progress(progress)
                continue

            date_range = build_date_range(win_start, win_end)
            serialized = json.dumps({"messages": messages}, ensure_ascii=False)
            logger.info(f"Backfilling {chat_cfg.id}: {date_range} ({len(messages)} messages)")

            # Retry on rate limit using the wait time suggested by the API
            for attempt in range(5):
                try:
                    summary, _ = summarizer.summarize(
                        serialized, summarization_prompt,
                        chat_link_base=chat_link_base, date_range=date_range,
                    )
                    break
                except ChatGoogleGenerativeAIError as e:
                    match = re.search(r'retry in (\d+)', str(e))
                    wait = int(match.group(1)) + 5 if match else 60
                    logger.warning(f"Rate limited — waiting {wait}s before retry (attempt {attempt + 1}/5)")
                    time.sleep(wait)
                    if attempt == 4:
                        raise

            for channel in app_config.telegram_output_channels:
                scrapper.send_to_channel(channel, summary)

            # Save progress after each successful window
            progress[chat_key] = win_end.isoformat()
            save_backfill_progress(progress)

            # Stay within RPM limit between backfill requests
            time.sleep(BACKFILL_SLEEP)

        logger.info(f"Backfill complete for: {chat_cfg.id}")


    # Setup recurring summarization jobs
    for chat_config in app_config.chats_to_summarize:
        with open(chat_config.summarization_prompt_path, "r") as f:
            chat_summarization_prompt = f.read()
        schedule.every(chat_config.lookback_period_seconds).seconds.do(
            job_func=summarization_job,
            chat_cfg=chat_config,
            summarization_prompt=chat_summarization_prompt,
        )

    # Run backfill for chats that have it enabled
    for chat_config in app_config.chats_to_summarize:
        if chat_config.backfill:
            with open(chat_config.summarization_prompt_path, "r") as f:
                chat_summarization_prompt = f.read()
            run_backfill(chat_config, chat_summarization_prompt)

    # Run the jobs for the first time then loop
    schedule.run_all()
    while True:
        schedule.run_pending()
        time.sleep(1)

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE")

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is not configured")

if not MONGODB_DATABASE:
    raise RuntimeError("MONGODB_DATABASE is not configured")


client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=5000
)

db = client[MONGODB_DATABASE]

current_state_collection = db["current_state"]
daily_events_collection = db["daily_events"]
tracker_runs_collection = db["tracker_runs"]


def get_current_state(target_username: str):
    """
    Get the latest follower/following state for a target account.
    """

    return current_state_collection.find_one(
        {
            "target_username": target_username
        }
    )


def save_current_state(
    target_username: str,
    followers: list[dict],
    following: list[dict]
):
    """
    Replace the current state for a target account.
    """

    state = {
        "target_username": target_username,
        "followers": followers,
        "following": following,
        "follower_count": len(followers),
        "following_count": len(following),
        "updated_at": datetime.now(timezone.utc)
    }

    current_state_collection.update_one(
        {
            "target_username": target_username
        },
        {
            "$set": state
        },
        upsert=True
    )


def save_daily_events(
    target_username: str,
    followers_new: list[dict],
    followers_lost: list[dict],
    following_new: list[dict],
    following_lost: list[dict]
):
    """
    Save all changes detected during one tracking run.
    """

    now = datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")

    daily_event = {
        "target_username": target_username,
        "date": date,
        "followers": {
            "new": followers_new,
            "lost": followers_lost,
            "new_count": len(followers_new),
            "lost_count": len(followers_lost)
        },
        "following": {
            "new": following_new,
            "lost": following_lost,
            "new_count": len(following_new),
            "lost_count": len(following_lost)
        },
        "created_at": now
    }

    daily_events_collection.update_one(
        {
            "target_username": target_username,
            "date": date
        },
        {
            "$set": daily_event
        },
        upsert=True
    )

def has_successful_run_today(target_username: str) -> bool:
    """
    Check whether this target has already been successfully
    polled today (UTC).
    """

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return tracker_runs_collection.find_one(
        {
            "target_username": target_username,
            "date": today,
            "status": "success"
        }
    ) is not None

def save_successful_run(target_username: str):
    """
    Record a successful tracker execution.
    """

    now = datetime.now(timezone.utc)

    tracker_runs_collection.update_one(
        {
            "target_username": target_username,
            "date": now.strftime("%Y-%m-%d")
        },
        {
            "$set": {
                "target_username": target_username,
                "date": now.strftime("%Y-%m-%d"),
                "status": "success",
                "completed_at": now
            }
        },
        upsert=True
    )

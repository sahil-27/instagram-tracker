import os
import argparse

import instaloader
from instaloader.exceptions import TooManyRequestsException
from dotenv import load_dotenv

from database import (
    get_current_state,
    save_current_state,
    save_daily_events,
    has_successful_run_today,
    save_successful_run,
)


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

load_dotenv()

TARGET_USERNAME = os.getenv("TARGET_USERNAME")
YOUR_IG_USERNAME = os.getenv("YOUR_IG_USERNAME")

INSTAGRAM_SESSION_FILE = os.getenv(
    "INSTAGRAM_SESSION_FILE"
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def compare_users(
    current: list[dict],
    previous: list[dict]
):
    """
    Compare two Instagram user lists using Instagram user IDs.

    Returns:
        added: Users present in current but not previous.
        removed: Users present in previous but not current.
    """

    current_by_id = {
        user["id"]: user
        for user in current
    }

    previous_by_id = {
        user["id"]: user
        for user in previous
    }

    current_ids = set(current_by_id.keys())
    previous_ids = set(previous_by_id.keys())

    added_ids = current_ids - previous_ids
    removed_ids = previous_ids - current_ids

    added = [
        current_by_id[user_id]
        for user_id in added_ids
    ]

    removed = [
        previous_by_id[user_id]
        for user_id in removed_ids
    ]

    added.sort(
        key=lambda user: user["username"]
    )

    removed.sort(
        key=lambda user: user["username"]
    )

    return added, removed


def print_changes(
    label: str,
    added: list[dict],
    removed: list[dict]
):
    """
    Print detected changes to the terminal.
    """

    print(f"\n📈 {label.upper()} CHANGES")

    print(f"➕ Added ({len(added)}):")

    if added:
        for user in added:
            print(f"   @{user['username']}")
    else:
        print("   None")

    print(f"➖ Removed ({len(removed)}):")

    if removed:
        for user in removed:
            print(f"   @{user['username']}")
    else:
        print("   None")


# ---------------------------------------------------------
# Instagram Session
# ---------------------------------------------------------

def load_instagram_session():
    """
    Load the existing Instaloader session from the
    configured session file.

    Local:
        ~/.config/instaloader/session-username

    Render:
        /etc/secrets/session-username
    """

    if not INSTAGRAM_SESSION_FILE:
        raise RuntimeError(
            "INSTAGRAM_SESSION_FILE is not configured"
        )

    if not os.path.isfile(INSTAGRAM_SESSION_FILE):
        raise RuntimeError(
            "Instagram session file not found: "
            f"{INSTAGRAM_SESSION_FILE}"
        )

    loader = instaloader.Instaloader()

    print(
        "🔐 Loading saved Instagram session..."
    )

    try:
        loader.load_session_from_file(
            YOUR_IG_USERNAME,
            INSTAGRAM_SESSION_FILE
        )

        print(
            f"✅ Logged in as @{YOUR_IG_USERNAME}"
        )

    except TooManyRequestsException:
        raise RuntimeError(
            "Instagram rate limit detected while "
            "loading the session. Stopping immediately."
        )

    except Exception as e:
        raise RuntimeError(
            f"Failed to load Instagram session: {e}"
        )

    return loader


# ---------------------------------------------------------
# Instagram Data
# ---------------------------------------------------------

def fetch_instagram_data(loader):
    """
    Fetch the target profile, followers and following.

    If any request fails, the entire tracking run is
    aborted.

    A failed request is NEVER treated as an empty list.
    """

    print(
        f"\n📦 Fetching profile for "
        f"@{TARGET_USERNAME}..."
    )

    try:
        profile = instaloader.Profile.from_username(
            loader.context,
            TARGET_USERNAME
        )

        print(
            f"✅ Profile found: "
            f"{profile.full_name or TARGET_USERNAME}"
        )

    except TooManyRequestsException:
        raise RuntimeError(
            "Instagram rate limit detected while "
            "loading the target profile. "
            "Stopping immediately."
        )

    except Exception as e:
        raise RuntimeError(
            f"Could not load profile: {e}"
        )

    # -----------------------------------------------------
    # Followers
    # -----------------------------------------------------

    print("\n📥 Getting followers...")

    try:
        followers = []

        for follower in profile.get_followers():
            followers.append({
                "id": str(follower.userid),
                "username": follower.username
            })

        print(
            f"✅ Retrieved {len(followers)} followers"
        )

    except TooManyRequestsException:
        raise RuntimeError(
            "Instagram rate limit detected while "
            "fetching followers. "
            "Stopping immediately."
        )

    except Exception as e:
        raise RuntimeError(
            f"Could not fetch followers: {e}"
        )

    # -----------------------------------------------------
    # Following
    # -----------------------------------------------------

    print("\n📥 Getting following...")

    try:
        following = []

        for followee in profile.get_followees():
            following.append({
                "id": str(followee.userid),
                "username": followee.username
            })

        print(
            f"✅ Retrieved {len(following)} following"
        )

    except TooManyRequestsException:
        raise RuntimeError(
            "Instagram rate limit detected while "
            "fetching following. "
            "Stopping immediately."
        )

    except Exception as e:
        raise RuntimeError(
            f"Could not fetch following: {e}"
        )

    return profile, followers, following


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without saving to MongoDB"
    )

    args = parser.parse_args()

    # -----------------------------------------------------
    # Validate configuration
    # -----------------------------------------------------

    if not TARGET_USERNAME:
        raise RuntimeError(
            "TARGET_USERNAME is not configured"
        )

    if not YOUR_IG_USERNAME:
        raise RuntimeError(
            "YOUR_IG_USERNAME is not configured"
        )

    print("==========================================")
    print("          INSTAGRAM TRACKER")
    print("==========================================")

    print(
        f"Target: @{TARGET_USERNAME}"
    )

    print(
        f"Instagram account: @{YOUR_IG_USERNAME}"
    )

    # -----------------------------------------------------
    # Daily safety check
    # -----------------------------------------------------

    if not args.dry_run:

        print(
            "\n🔍 Checking today's tracker status..."
        )

        if has_successful_run_today(
            TARGET_USERNAME
        ):

            print(
                "⏭️ Tracker has already run "
                "successfully today."
            )

            print(
                "🚫 No Instagram requests will be made."
            )

            return

        print(
            "✅ No successful run found for today."
        )

    else:

        print(
            "\n🧪 Dry-run mode: daily safety "
            "check skipped."
        )

    # -----------------------------------------------------
    # Load Instagram session
    # -----------------------------------------------------

    try:

        loader = load_instagram_session()

    except Exception as e:

        print(
            "\n❌ Instagram session error."
        )

        print(
            f"Reason: {e}"
        )

        return

    # -----------------------------------------------------
    # Fetch current Instagram state
    # -----------------------------------------------------

    try:

        (
            profile,
            current_followers,
            current_following
        ) = fetch_instagram_data(loader)

    except Exception as e:

        print(
            "\n❌ Tracking run failed."
        )

        print(
            f"Reason: {e}"
        )

        print(
            "\n🚫 Nothing was saved to MongoDB."
        )

        return

    # -----------------------------------------------------
    # Get previous state
    # -----------------------------------------------------

    print(
        "\n🔍 Loading previous state "
        "from MongoDB..."
    )

    previous_state = get_current_state(
        TARGET_USERNAME
    )

    # -----------------------------------------------------
    # First run
    # -----------------------------------------------------

    if previous_state is None:

        print(
            "\n🆕 No previous state found."
        )

        print(
            "This is the first run, so this "
            "will become the baseline."
        )

        if args.dry_run:

            print(
                "\n🚫 Dry run: baseline "
                "was not saved."
            )

            return

        try:

            save_current_state(
                TARGET_USERNAME,
                current_followers,
                current_following
            )

            save_daily_events(
                TARGET_USERNAME,
                [],
                [],
                [],
                []
            )

            save_successful_run(
                TARGET_USERNAME
            )

            print(
                "\n✅ Initial state "
                "saved to MongoDB."
            )

            print(
                "✅ Tracker run marked "
                "as successful."
            )

        except Exception as e:

            print(
                "\n❌ Failed to save "
                "initial state."
            )

            print(
                f"Reason: {e}"
            )

            print(
                "\n⚠️ Run was NOT marked "
                "as successful."
            )

        return

    # -----------------------------------------------------
    # Compare
    # -----------------------------------------------------

    print(
        "\n🔍 Comparing with "
        "previous state..."
    )

    previous_followers = previous_state.get(
        "followers",
        []
    )

    previous_following = previous_state.get(
        "following",
        []
    )

    (
        new_followers,
        lost_followers
    ) = compare_users(
        current_followers,
        previous_followers
    )

    (
        new_following,
        unfollowed
    ) = compare_users(
        current_following,
        previous_following
    )

    # -----------------------------------------------------
    # Display changes
    # -----------------------------------------------------

    print_changes(
        "Followers",
        new_followers,
        lost_followers
    )

    print_changes(
        "Following",
        new_following,
        unfollowed
    )

    print("\n📊 Daily Summary")

    print(
        f"👥 Followers: "
        f"+{len(new_followers)}, "
        f"-{len(lost_followers)}, "
        f"Net: "
        f"{len(new_followers) - len(lost_followers)}"
    )

    print(
        f"➡️ Following: "
        f"+{len(new_following)}, "
        f"-{len(unfollowed)}, "
        f"Net: "
        f"{len(new_following) - len(unfollowed)}"
    )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    if args.dry_run:

        print(
            "\n🚫 Dry run: nothing saved "
            "to MongoDB."
        )

    else:

        try:

            save_daily_events(
                TARGET_USERNAME,
                new_followers,
                lost_followers,
                new_following,
                unfollowed
            )

            save_current_state(
                TARGET_USERNAME,
                current_followers,
                current_following
            )

            save_successful_run(
                TARGET_USERNAME
            )

            print(
                "\n✅ Daily changes "
                "saved to MongoDB."
            )

            print(
                "✅ Tracker run marked "
                "as successful."
            )

        except Exception as e:

            print(
                "\n❌ Failed to save "
                "tracking data."
            )

            print(
                f"Reason: {e}"
            )

            print(
                "\n⚠️ The run was NOT "
                "marked as successful."
            )

    print(
        "\n=========================================="
    )

    print(
        "              TRACKING DONE"
    )

    print(
        "=========================================="
    )


# ---------------------------------------------------------
# Entry Point
# ---------------------------------------------------------

if __name__ == "__main__":
    main()